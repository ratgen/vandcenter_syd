"""Config flow for VandCenter Syd."""

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_BASE,
    CONF_TOKEN,
    DOMAIN,
    CONF_EMAIL,
    CONF_PASSWORD,
    CONF_PRICE,
    CONF_TOKEN_EXPIRES,
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler()

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            email = user_input[CONF_EMAIL]
            password = user_input[CONF_PASSWORD]
            session = async_get_clientsession(self.hass)

            # Test login
            try:
                resp = await session.post(
                    f"{API_BASE}/Customer/login",
                    json={"MatchTag": None, "Email": email, "Password": password},
                )
                if resp.status == 200:
                    data = await resp.json()
                    return self.async_create_entry(
                        title="VandCenter Syd",
                        data={
                            CONF_EMAIL: email,
                            CONF_PASSWORD: password,
                            CONF_TOKEN: data["AuthToken"],
                            CONF_TOKEN_EXPIRES: data["ExpiresIn"],
                        },
                    )
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            description_placeholders={"url": "https://vandcenter.smartforsyning.dk"},
            errors=errors,
        )


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    async def async_step_init(self, user_input=None):
        """Manage the fixed price per m³."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        price = self.config_entry.options.get(CONF_PRICE)
        if price is None:
            # Suggest the price scraped from vandcenter.dk
            coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id][
                "coordinator"
            ]
            price = coordinator.data.get("price") or None

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_PRICE,
                        description={"suggested_value": price},
                    ): vol.All(vol.Coerce(float), vol.Range(min=0)),
                }
            ),
        )
