![Header](header.png)

---

# VandCenter Syd x Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![Home Assistant](https://img.shields.io/badge/home%20assistant-%3E%3D2026.3.4-blue.svg?style=for-the-badge)](https://www.home-assistant.io)

[![Open Home Assistant Community Store](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=LovelessCodes&repository=vandcenter_syd&category=integration)

Unofficial integration for **VandCenter Syd** water meters in Home Assistant. Monitor your household water consumption directly from the Smart Forsyning portal.

> **Note:** This integration is for customers of [VandCenter Syd](https://www.vandcentersyd.dk/) (Denmark). If you're not a customer, this integration won't work for you.

## Features

- **Real-time consumption** – Current total meter reading and daily usage statistics
- **Hourly history** – Imports hour-by-hour consumption into Home Assistant's long-term statistics, placed at the hour it was actually used (backfills 30 days on first run)
- **Energy Dashboard support** – Track water usage alongside electricity and gas in the Home Assistant Energy Dashboard
- **Automatic authentication** – Handles token refresh automatically (tokens expire after 1 hour)
- **Multi-device support** – Automatically discovers all water meters associated with your account
- **Leak detection** – Access to alarm states (if available from your meter)

## Installation

### Via HACS (Recommended)

1. Add this repository to HACS as a [custom repository](https://hacs.xyz/docs/faq/custom_repositories):
   - Repository: `https://github.com/LovelessCodes/vandcenter_syd`
   - Category: Integration
2. Click **Download** in the HACS interface
3. Restart Home Assistant
4. Go to **Settings > Devices & Services > Add Integration** and search for "VandCenter Syd"

### Manual Installation

1. Copy the `vandcenter_syd` folder from this repository into your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Add the integration via the UI

## Configuration

The integration requires your Smart Forsyning login credentials (email and password).    
These are used to authenticate with the API and are stored securely in Home Assistant.

### Finding Your Credentials

1. Visit [https://vandcenter.smartforsyning.dk](https://vandcenter.smartforsyning.dk)
2. Use the same email and password you use to log into the Smart Forsyning portal
3. The integration will automatically handle API authentication and token refresh

## Available Sensors

For each water meter discovered, the following sensors are created:

| Sensor | Description | State Class |
|--------|-------------|-------------|
| **Daily Usage** | Yesterday's water consumption in m³ | `total` |
| **Total Reading** | Current cumulative meter reading (for Energy Dashboard) | `total_increasing` |
| **Average Daily** | Average consumption over the reporting period (last 14 days) | `total` |
| **Period Max** | Highest single-day consumption in the period (last 14 days) | `total` |

## Hourly Consumption Statistics

Meter readings reach the Smart Forsyning API with a delay, so the **Total** sensor only increases when a batch of readings arrives. On its own, that makes all the consumption show up at the moment of the update.

To fix this, the integration also fetches hourly consumption and imports it as an external statistic per meter:

| Statistic ID | Name |
|--------------|------|
| `vandcenter_syd:<device_id>_water_consumption` | `<Meter> Water Consumption` |
| `vandcenter_syd:<device_id>_water_cost` | `<Meter> Water Cost` (only when a price is set) |

Each hour is recorded at the time the water was used. Every refresh re-imports the last 72 hours, so late or corrected readings get picked up. To see the data hour by hour, use a **Statistics Graph** card with this statistic, or the Energy Dashboard.

## Energy Dashboard Setup

To track water consumption in the Home Assistant Energy Dashboard:

1. Go to **Settings > Dashboards > Energy**
2. Click **Add Water Source**
3. Select the **`<Meter> Water Consumption`** statistic (`vandcenter_syd:<device_id>_water_consumption`)

### Tracking cost

Home Assistant's "Use a static price" option is only available for sensor entities, not for imported statistics. Instead, set a fixed price in the integration:

1. Go to **Settings > Devices & Services > VandCenter Syd > Configure**
2. Enter the **Price per m³** (pre-filled with the current price from vandcenter.dk)
3. In the water source dialog, choose **Use an entity tracking the total costs** and select the **`<Meter> Water Cost`** statistic

The cost statistic is backfilled 30 days the first time a price is set. A price change applies from the last 72 hours onward. Clear the field to stop tracking cost.

**Note:** Hourly data appears after the first refresh. If you previously used the **Total** sensor as the water source, replace it with the statistic above to get correct hourly placement.

## API Limitations

- **Update frequency**: Data is fetched at the start of every hour
- **Resolution**: Hourly consumption buckets, delivered by the meter with a delay
- **Geographic restriction**: Only works for VandCenter Syd customers in Denmark

## Troubleshooting

### "Invalid authentication" error
- Verify you're using the same email/password as the Smart Forsyning web portal
- Ensure your account has active water meters registered

### Sensors show "unavailable"
- Check Home Assistant logs for API connection errors
- The integration will automatically retry on token expiration

### No historical data in Energy Dashboard
- Historical import runs after the first refresh; wait a few minutes
- Verify the **Water Consumption** statistic is added to the Energy Dashboard

### Missing meters
- Ensure your meters are visible in the Smart Forsyning web portal
- The integration only fetches meters associated with your primary location

## Technical Details

This integration uses the unofficial Smart Forsyning REST API:
- `GET /api/Customer/details` – Location and account information
- `GET /api/Customer/devices` – Device enumeration
- `POST /api/Stats/usage/{locationId}/devices` – Daily and hourly consumption statistics
- `POST /api/Stats/readings/devices` – Current meter readings
- `POST /api/Customer/login` – Authentication (automatic token refresh)

## Disclaimer

This is an unofficial integration and is not affiliated with or endorsed by [VandCenter Syd](https://www.vandcentersyd.dk/).    
Use at your own risk.    
Your credentials are stored locally in your Home Assistant instance and are only used to authenticate with the official Smart Forsyning API.

## License

MIT License - see [LICENSE](LICENSE) file for details.

---

**Enjoy monitoring your water consumption! 💧**
