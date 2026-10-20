"""DataUpdateCoordinator for VandCenter Syd."""

import logging
import re
from datetime import datetime, timedelta, timezone

import async_timeout
from aiohttp import ClientResponseError
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify
from homeassistant.util.unit_conversion import VolumeConverter

from .const import (
    API_BASE,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_PRICE,
    CONF_TOKEN,
    CONF_TOKEN_EXPIRES,
    DOMAIN,
    HOURLY_BACKFILL_DAYS,
    HOURLY_REFRESH_HOURS,
)

API_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S.000Z"

_LOGGER = logging.getLogger(__name__)


class VandCenterCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch data from VandCenter API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=None,  # Disable automatic polling - we use time-based tracking
        )
        self.entry = entry
        self.session = async_get_clientsession(hass)

    async def async_hourly_refresh(self, now: datetime | None = None) -> None:
        """Refresh data at the start of each hour."""
        _LOGGER.info("Hourly refresh triggered at %s", now)
        await self.async_request_refresh()
        _LOGGER.info("Hourly refresh completed")

    @property
    def token(self):
        return self.entry.data[CONF_TOKEN]

    async def _async_update_data(self):
        headers = {"Authorization": f"Bearer {self.token}"}

        try:
            data = await self._fetch_data(headers)
        except ClientResponseError as err:
            if err.status != 401:
                raise UpdateFailed(f"API error: {err}")
            # Token expired, refresh and retry
            await self._refresh_token()
            headers = {"Authorization": f"Bearer {self.token}"}
            data = await self._fetch_data(headers)

        for device_id, device_data in data["devices"].items():
            try:
                await self._async_import_hourly_statistics(
                    headers, device_id, device_data
                )
            except Exception as err:
                _LOGGER.warning(
                    "Failed to import hourly statistics for %s: %s", device_id, err
                )

        return data

    async def _refresh_token(self):
        """Login to get new token."""
        try:
            resp = await self.session.post(
                f"{API_BASE}/Customer/login",
                json={
                    "MatchTag": None,
                    "Email": self.entry.data[CONF_EMAIL],
                    "Password": self.entry.data[CONF_PASSWORD],
                },
            )
            resp.raise_for_status()
            data = await resp.json()

            # Update config entry with new token
            self.hass.config_entries.async_update_entry(
                self.entry,
                data={
                    **self.entry.data,
                    CONF_TOKEN: data["AuthToken"],
                    CONF_TOKEN_EXPIRES: data["ExpiresIn"],
                },
            )
            _LOGGER.debug("Token refreshed successfully")

        except Exception as err:
            _LOGGER.error("Failed to refresh token: %s", err)
            raise UpdateFailed("Authentication failed, please reconfigure integration")

    async def _fetch_data(self, headers) -> dict:
        """Actual data fetching logic."""
        async with async_timeout.timeout(30):
            resp = await self.session.get(
                f"{API_BASE}/Customer/details", headers=headers
            )
            resp.raise_for_status()
            customer = await resp.json()

            all_device_data = {}

            for location in customer.get("Locations", []):
                loc_id = location["LocationId"]

                resp = await self.session.get(
                    f"{API_BASE}/Customer/devices",
                    headers=headers,
                    params={
                        "LocationId": loc_id,
                        "IncludeDisabledDevices": "true",
                    },
                )
                resp.raise_for_status()
                devices_resp = await resp.json()

                for device in devices_resp.get("Devices", []):
                    device_id = device["Id"]

                    # Get usage stats (last 14 days)
                    to_date = datetime.now(timezone.utc)
                    from_date = to_date - timedelta(days=14)

                    payload = {
                        "DeviceIds": [device_id],
                        "From": from_date.strftime(API_DATE_FORMAT),
                        "To": to_date.strftime(API_DATE_FORMAT),
                        "Interval": "Daily",
                        "QuantityType": "WaterVolume",
                        "Unit": "KubicMeter",
                    }

                    resp = await self.session.post(
                        f"{API_BASE}/Stats/usage/{loc_id}/devices",
                        headers=headers,
                        json=payload,
                    )
                    resp.raise_for_status()
                    usage = await resp.json()

                    total_payload = {
                        "DeviceContainerIds": [device_id],
                        "QuantityTypes": ["WaterVolume"],
                        "Size": 1,
                    }

                    try:
                        resp = await self.session.post(
                            f"{API_BASE}/Stats/readings/devices",
                            headers=headers,
                            json=total_payload,
                        )
                        resp.raise_for_status()
                        readings_data = await resp.json()

                        total_reading = None
                        if readings_data and len(readings_data) > 0:
                            readings = readings_data[0].get("Readings", [])
                            if readings:
                                total_reading = readings[0].get("Value")
                                reading_timestamp = readings[0].get("Timestamp")
                    except Exception as err:
                        _LOGGER.warning(
                            "Failed to fetch total reading for %s: %s", device_id, err
                        )
                        total_reading = None
                        reading_timestamp = None

                    all_device_data[device_id] = {
                        "device": device,
                        "location": location,
                        "usage": usage,
                        "total_reading": total_reading,
                        "reading_timestamp": reading_timestamp,
                    }

            price = 0

            try:
                resp = await self.session.get("https://vandcenter.dk/pris-forbrug")
                resp.raise_for_status()
                text = await resp.text()
                PRICE_REGEX = r">([0-9,]+)\s+.*?kr.\/m3"
                m = re.search(PRICE_REGEX, text, re.S)
                if m:
                    price = float(m.group(1).replace(",", "."))
                else:
                    _LOGGER.warning("Failed to parse price from vandcenter.dk")
            except Exception as err:
                _LOGGER.warning("Failed to fetch price from vandcenter.dk: %s", err)

            return {"devices": all_device_data, "price": price}

    async def _async_import_hourly_statistics(
        self, headers: dict, device_id, device_data: dict
    ) -> None:
        """Import hourly consumption, and cost if a price is set, into statistics.

        Meter data reaches the API with a delay, so the last HOURLY_REFRESH_HOURS
        are fetched again on every refresh and re-imported. Statistics are keyed
        by their start hour, so re-importing an hour overwrites it.
        """
        stat_prefix = f"{DOMAIN}:{slugify(str(device_id))}"
        name_prefix = device_data["device"]["BrandName"]
        consumption = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=f"{name_prefix} Water Consumption",
            source=DOMAIN,
            statistic_id=f"{stat_prefix}_water_consumption",
            unit_class=VolumeConverter.UNIT_CLASS,
            unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        )
        targets: list[tuple[StatisticMetaData, float]] = [(consumption, 1.0)]

        price = self.entry.options.get(CONF_PRICE)
        if price is not None:
            cost = StatisticMetaData(
                mean_type=StatisticMeanType.NONE,
                has_sum=True,
                name=f"{name_prefix} Water Cost",
                source=DOMAIN,
                statistic_id=f"{stat_prefix}_water_cost",
                unit_class=None,
                unit_of_measurement=self.hass.config.currency,
            )
            targets.append((cost, price))

        recorder = get_instance(self.hass)
        now_hour = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)

        # Start at the earliest hour any of the statistics needs
        start = now_hour - timedelta(hours=HOURLY_REFRESH_HOURS)
        last_rows = {}
        for metadata, _ in targets:
            statistic_id = metadata["statistic_id"]
            last_stats = await recorder.async_add_executor_job(
                get_last_statistics, self.hass, 1, statistic_id, True, {"sum"}
            )
            if last_stats.get(statistic_id):
                last = last_stats[statistic_id][0]
                last_rows[statistic_id] = last
                last_start = dt_util.utc_from_timestamp(last["start"])
                start = min(start, last_start + timedelta(hours=1))
            else:
                start = min(start, now_hour - timedelta(days=HOURLY_BACKFILL_DAYS))

        buckets = await self._fetch_hourly_buckets(
            headers, device_data["location"]["LocationId"], device_id, start, now_hour
        )
        if not buckets:
            return

        # Continue the sum from the hour before the first bucket, not before
        # start: if the API leaves out the first hours of the window, the rows
        # already stored for them would otherwise sit above the new sums and
        # show up as negative consumption
        first_hour = buckets[0][0]
        for metadata, factor in targets:
            statistic_id = metadata["statistic_id"]
            running_sum = await self._async_get_sum_before(
                statistic_id, first_hour, last_rows.get(statistic_id)
            )
            statistics: list[StatisticData] = []
            for hour_start, value in buckets:
                running_sum += value * factor
                statistics.append(StatisticData(start=hour_start, sum=running_sum))

            async_add_external_statistics(self.hass, metadata, statistics)
            _LOGGER.debug(
                "Imported %s hourly statistics for %s from %s",
                len(statistics),
                statistic_id,
                statistics[0]["start"],
            )

    async def _async_get_sum_before(
        self, statistic_id: str, start: datetime, last: dict | None
    ) -> float:
        """Return the sum of the latest statistic before start, or 0 if none."""
        if last is None:
            return 0.0
        if dt_util.utc_from_timestamp(last["start"]) < start:
            return last["sum"] or 0.0

        rows = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass,
            start - timedelta(days=HOURLY_BACKFILL_DAYS),
            start,
            {statistic_id},
            "hour",
            None,
            {"sum"},
        )
        if not rows.get(statistic_id):
            return 0.0
        return rows[statistic_id][-1]["sum"] or 0.0

    async def _fetch_hourly_buckets(
        self, headers: dict, loc_id, device_id, start: datetime, end: datetime
    ) -> list[tuple[datetime, float]]:
        """Return (hour start, m³) for each complete hour between start and end.

        The API labels hourly buckets by the end of the hour, and From/To filter
        on those labels. Requests are made one day at a time, like the portal.
        """
        by_end: dict[datetime, dict] = {}
        chunk_start = start
        while chunk_start < end:
            chunk_end = min(chunk_start + timedelta(days=1), end)
            payload = {
                "DeviceIds": [device_id],
                "From": (chunk_start + timedelta(hours=1)).strftime(API_DATE_FORMAT),
                "To": chunk_end.strftime(API_DATE_FORMAT),
                "Interval": "Hourly",
                "QuantityType": "WaterVolume",
                "Unit": "KubicMeter",
            }
            async with async_timeout.timeout(30):
                resp = await self.session.post(
                    f"{API_BASE}/Stats/usage/{loc_id}/devices",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                usage = await resp.json()

            for bucket in (usage or {}).get("Buckets") or []:
                bucket_end = dt_util.parse_datetime(bucket.get("Timestamp") or "")
                if bucket_end is None or bucket.get("Value") is None:
                    continue
                if bucket_end.tzinfo is None:
                    bucket_end = bucket_end.replace(tzinfo=timezone.utc)
                bucket_end = dt_util.as_utc(bucket_end)
                if start < bucket_end <= end:
                    by_end[bucket_end] = bucket

            chunk_start = chunk_end

        ordered = sorted(by_end.items())
        # Trailing hours without readings have not been delivered by the meter
        # yet; leave them out so they are not recorded as zero consumption
        while ordered and ordered[-1][1].get("Count", 1) == 0:
            ordered.pop()

        return [
            (bucket_end - timedelta(hours=1), float(bucket["Value"]))
            for bucket_end, bucket in ordered
        ]
