"""Constants for the VandCenter Syd integration."""

DOMAIN = "vandcenter_syd"
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_TOKEN = "token"
CONF_TOKEN_EXPIRES = "token_expires"

API_BASE = "https://vandcenter.smartforsyning.dk/api"

# Hourly statistics import
HOURLY_BACKFILL_DAYS = 30  # How far back to import on first run
# Hours re-imported on each refresh, as meter data arrives delayed
HOURLY_REFRESH_HOURS = 72
