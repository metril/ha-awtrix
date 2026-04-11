"""Constants for the AWTRIX 3 integration."""

DOMAIN = "awtrix"

# Config entry data keys
CONF_CONNECTION_TYPE = "connection_type"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_MQTT_PREFIX = "mqtt_prefix"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

# Connection types
CONNECTION_HTTP = "http"
CONNECTION_MQTT = "mqtt"

# Options keys and defaults
CONF_POLL_INTERVAL = "poll_interval"
DEFAULT_POLL_INTERVAL = 30  # seconds
DEFAULT_PORT = 80
DEFAULT_HTTP_TIMEOUT = 10  # seconds

# AWTRIX setting keys
SETTING_BRIGHTNESS = "BRI"
SETTING_VOLUME = "VOL"
SETTING_APP_DURATION = "ATIME"
SETTING_TRANSITION_EFFECT = "TEFF"
SETTING_CELSIUS = "CEL"
SETTING_UPPERCASE = "UPPERCASE"

# App template keys
CONF_APPS = "apps"

# Default LaMetric weather icon mapping
WEATHER_ICON_MAP: dict[str, str] = {
    "sunny": "2283",
    "clear-night": "2285",
    "cloudy": "2283",
    "partlycloudy": "2286",
    "rainy": "2284",
    "pouring": "2284",
    "snowy": "2289",
    "snowy-rainy": "2289",
    "lightning": "2287",
    "lightning-rainy": "2287",
    "fog": "17056",
    "hail": "2441",
    "windy": "3363",
    "exceptional": "2283",
}

# Default LaMetric icons for non-weather templates
ICON_THERMOMETER = "2056"
ICON_HUMIDITY = "51764"
ICON_BATTERY = "12832"
ICON_CALENDAR = "58153"
ICON_CLOCK = "6966"
ICON_HOURGLASS = "5765"
ICON_TEXT = "9533"

# Service names
SERVICE_NOTIFY = "notify"
SERVICE_APP_UPDATE = "app_update"
SERVICE_APP_REMOVE = "app_remove"
SERVICE_PLAY_RTTTL = "play_rtttl"
SERVICE_UPDATE_SETTINGS = "update_settings"
SERVICE_SWITCH_APP = "switch_app"
SERVICE_SLEEP = "sleep"

# Date/time format options
TIME_FORMATS = {
    "%H:%M": "24-hour (14:30)",
    "%I:%M %p": "12-hour (2:30 PM)",
    "%H:%M:%S": "24-hour with seconds (14:30:45)",
}

DATE_FORMATS = {
    "%m/%d/%Y": "US (04/10/2026)",
    "%d/%m/%Y": "European (10/04/2026)",
    "%Y-%m-%d": "ISO (2026-04-10)",
    "%b %d": "Short (Apr 10)",
    "%a %b %d": "Weekday (Fri Apr 10)",
}
