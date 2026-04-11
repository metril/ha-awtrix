"""Constants for the AWTRIX 3 integration."""

DOMAIN = "awtrix"

# Config entry data keys
CONF_CONNECTION_TYPE = "connection_type"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_MQTT_PREFIX = "mqtt_prefix"
CONF_DEVICE_HOST = "device_host"
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
SETTING_AUTO_BRIGHTNESS = "ABRI"
SETTING_VOLUME = "VOL"
SETTING_APP_DURATION = "ATIME"
SETTING_TRANSITION_EFFECT = "TEFF"
SETTING_CELSIUS = "CEL"
SETTING_UPPERCASE = "UPPERCASE"

# App template keys
CONF_APPS = "apps"

# Per-template display config keys
CONF_TEXT_COLOR = "text_color"
CONF_DURATION = "display_duration"
CONF_SCROLL_SPEED = "scroll_speed"
CONF_SHOW_CONDITION = "show_condition_text"
CONF_WEATHER_OVERLAY = "weather_overlay"

# Verified LaMetric icon IDs as strings (AWTRIX expects string type for icon field)
ICON_THERMOMETER = "2056"
ICON_HUMIDITY = "51764"
ICON_BATTERY_FULL = "12832"
ICON_CALENDAR = "58153"
ICON_CLOCK = "6966"
ICON_HOURGLASS = "5765"
ICON_TEXT = "9533"

# Weather condition -> LaMetric icon ID mapping (strings for AWTRIX payload)
WEATHER_ICON_MAP: dict[str, str] = {
    "sunny": "11201",
    "clear-night": "53383",
    "cloudy": "2283",
    "partlycloudy": "11202",
    "rainy": "72",
    "pouring": "49299",
    "snowy": "2289",
    "snowy-rainy": "2289",
    "lightning": "630",
    "lightning-rainy": "630",
    "fog": "17056",
    "hail": "2441",
    "windy": "3363",
    "exceptional": "2283",
}

# Weather overlay effects (AWTRIX overlay feature)
WEATHER_OVERLAY_MAP: dict[str, str] = {
    "rainy": "rain",
    "pouring": "storm",
    "snowy": "snow",
    "snowy-rainy": "snow",
    "lightning": "storm",
    "lightning-rainy": "storm",
    "hail": "storm",
    "fog": "frost",
}

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

LAMETRIC_ICON_URL = "https://developer.lametric.com/content/apps/icon_thumbs"
SERVICE_SYNC_ICONS = "sync_icons"


def get_all_icon_ids() -> list[int]:
    """Return all icon IDs as integers (for ensure_icons which downloads by int ID)."""
    str_ids = set(WEATHER_ICON_MAP.values())
    str_ids.update([ICON_THERMOMETER, ICON_HUMIDITY, ICON_BATTERY_FULL, ICON_CALENDAR, ICON_CLOCK, ICON_HOURGLASS, ICON_TEXT])
    return sorted(int(i) for i in str_ids)
