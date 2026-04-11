"""The AWTRIX 3 integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import AwtrixHttpClient, AwtrixMqttClient
from .const import (
    CONF_APPS,
    CONF_CONNECTION_TYPE,
    CONF_DEVICE_HOST,
    CONF_HOST,
    CONF_MQTT_PREFIX,
    CONF_NIGHT_MODE_BRIGHTNESS,
    CONF_NIGHT_MODE_END,
    CONF_NIGHT_MODE_SCHEDULE,
    CONF_NIGHT_MODE_START,
    CONF_PASSWORD,
    CONF_POLL_INTERVAL,
    CONF_PORT,
    CONF_PRESENCE_ENTITY,
    CONF_USERNAME,
    CONNECTION_HTTP,
    CONNECTION_MQTT,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
    SERVICE_SYNC_ICONS,
    get_all_icon_ids,
)
from .coordinator import AwtrixCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

SERVICE_SCHEMAS = {
    "notify": vol.Schema({
        vol.Required("device_id"): str,
        vol.Required("text"): str,
        vol.Optional("icon"): str,
        vol.Optional("color"): vol.All(list, vol.Length(min=3, max=3)),
        vol.Optional("duration"): vol.Coerce(int),
        vol.Optional("sound"): str,
        vol.Optional("rtttl"): str,
        vol.Optional("effect"): str,
        vol.Optional("hold"): bool,
        vol.Optional("rainbow"): bool,
        vol.Optional("repeat"): vol.Coerce(int),
        vol.Optional("bar"): list,
        vol.Optional("line"): list,
        vol.Optional("gradient"): list,
    }),
    "app_update": vol.Schema({
        vol.Required("device_id"): str,
        vol.Required("name"): str,
        vol.Required("payload"): dict,
    }),
    "app_remove": vol.Schema({
        vol.Required("device_id"): str,
        vol.Required("name"): str,
    }),
    "play_rtttl": vol.Schema({
        vol.Required("device_id"): str,
        vol.Required("melody"): str,
    }),
    "update_settings": vol.Schema({
        vol.Required("device_id"): str,
        vol.Required("settings"): dict,
    }),
    "switch_app": vol.Schema({
        vol.Required("device_id"): str,
        vol.Required("name"): str,
    }),
    "sleep": vol.Schema({
        vol.Required("device_id"): str,
        vol.Required("seconds"): vol.Coerce(int),
    }),
    SERVICE_SYNC_ICONS: vol.Schema({vol.Required("device_id"): str}),
}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AWTRIX 3 from a config entry."""
    connection_type = entry.data[CONF_CONNECTION_TYPE]

    if connection_type == CONNECTION_HTTP:
        session = async_get_clientsession(hass)
        client = AwtrixHttpClient(
            session=session,
            host=entry.data[CONF_HOST],
            port=entry.data.get(CONF_PORT, DEFAULT_PORT),
            timeout=DEFAULT_HTTP_TIMEOUT,
            username=entry.data.get(CONF_USERNAME) or None,
            password=entry.data.get(CONF_PASSWORD) or None,
        )
    else:
        client = AwtrixMqttClient(
            hass=hass,
            prefix=entry.data[CONF_MQTT_PREFIX],
        )

    icon_client = None
    device_host = entry.data.get(CONF_DEVICE_HOST)
    if connection_type == CONNECTION_MQTT and device_host:
        session = async_get_clientsession(hass)
        icon_client = AwtrixHttpClient(
            session=session, host=device_host, port=80,
            username=entry.data.get(CONF_USERNAME) or None,
            password=entry.data.get(CONF_PASSWORD) or None,
        )

    poll_interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)
    coordinator = AwtrixCoordinator(
        hass, entry, client,
        poll_interval=poll_interval,
        connection_type=connection_type,
    )

    await coordinator.async_config_entry_first_refresh()

    if connection_type == CONNECTION_MQTT:
        await coordinator.async_start()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "icon_client": icon_client,
    }

    apps_config = entry.options.get(CONF_APPS, {})
    if any(cfg.get("enabled") for cfg in apps_config.values()):
        from .app_manager import AwtrixAppManager
        app_manager = AwtrixAppManager(hass, client, apps_config, icon_client=icon_client)
        hass.data[DOMAIN][entry.entry_id]["app_manager"] = app_manager
        await app_manager.async_start()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Night mode schedule and presence sensor listeners
    schedule_enabled = entry.options.get(CONF_NIGHT_MODE_SCHEDULE, False)
    night_start = entry.options.get(CONF_NIGHT_MODE_START, "")
    night_end = entry.options.get(CONF_NIGHT_MODE_END, "")
    unsub_listeners = []

    if schedule_enabled and night_start and night_end:
        from homeassistant.helpers.event import async_track_time_change

        start_parts = night_start.split(":")
        end_parts = night_end.split(":")

        @callback
        def _night_start_cb(_now):
            night_bri = entry.options.get(CONF_NIGHT_MODE_BRIGHTNESS, 0)

            async def _activate():
                if night_bri == 0:
                    await client.update_settings({"MATP": False})
                else:
                    await client.update_settings({"BRI": night_bri})
                await client.update_settings({"ATRANS": False})
                await client.switch_app("Time")

            hass.async_create_task(_activate())

        @callback
        def _night_end_cb(_now):
            async def _deactivate():
                await client.update_settings({"MATP": True, "ATRANS": True, "BRI": 128})

            hass.async_create_task(_deactivate())

        unsub_listeners.append(async_track_time_change(
            hass, _night_start_cb,
            hour=int(start_parts[0]), minute=int(start_parts[1]), second=0,
        ))
        unsub_listeners.append(async_track_time_change(
            hass, _night_end_cb,
            hour=int(end_parts[0]), minute=int(end_parts[1]), second=0,
        ))

    presence_entity = entry.options.get(CONF_PRESENCE_ENTITY, "")
    if presence_entity:
        from homeassistant.helpers.event import async_track_state_change_event

        @callback
        def _presence_cb(event):
            new_state = event.data.get("new_state")
            if new_state is None:
                return
            if new_state.state == "on":
                hass.async_create_task(client.update_settings({"MATP": True}))
            else:
                hass.async_create_task(client.update_settings({"MATP": False}))

        unsub_listeners.append(async_track_state_change_event(
            hass, presence_entity, _presence_cb
        ))

    hass.data[DOMAIN][entry.entry_id]["unsub_listeners"] = unsub_listeners

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    # Register services (once, not per entry)
    if not hass.services.has_service(DOMAIN, "notify"):
        _register_services(hass)

    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload the entry."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    data = hass.data[DOMAIN].get(entry.entry_id, {})

    for unsub in data.get("unsub_listeners", []):
        unsub()

    app_manager = data.get("app_manager")
    if app_manager:
        await app_manager.async_stop()

    coordinator = data.get("coordinator")
    if coordinator is not None and hasattr(coordinator, "async_stop"):
        await coordinator.async_stop()

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    # Unregister services if no entries left
    if not hass.data.get(DOMAIN):
        for service_name in SERVICE_SCHEMAS:
            hass.services.async_remove(DOMAIN, service_name)
    return unload_ok


def _get_data_for_device(hass: HomeAssistant, device_id: str) -> dict:
    """Resolve device_id to its hass.data dict (client, icon_client, coordinator)."""
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get(device_id)
    if device is None:
        raise HomeAssistantError(f"Device {device_id} not found")
    for entry_id in device.config_entries:
        if entry_id in hass.data.get(DOMAIN, {}):
            return hass.data[DOMAIN][entry_id]
    raise HomeAssistantError(f"No AWTRIX integration found for device {device_id}")


def _get_client_for_device(hass: HomeAssistant, device_id: str):
    """Resolve device_id to its AwtrixClient."""
    return _get_data_for_device(hass, device_id)["client"]


def _register_services(hass: HomeAssistant) -> None:
    """Register all AWTRIX services."""

    async def _provision_icon(device_id: str, icon_value) -> str:
        """Ensure icon is on the device. Icon must be a string for AWTRIX."""
        icon_str = str(icon_value) if icon_value is not None else ""
        if icon_str and icon_str.isdigit():
            data = _get_data_for_device(hass, device_id)
            ic = data.get("icon_client") or data["client"]
            _LOGGER.debug("Provisioning icon %s via %s", icon_str, type(ic).__name__)
            try:
                await ic.ensure_icons([int(icon_str)])
            except Exception:
                _LOGGER.warning("Failed to provision icon %s", icon_str, exc_info=True)
        return icon_str

    async def handle_notify(call: ServiceCall) -> None:
        client = _get_client_for_device(hass, call.data["device_id"])
        payload = {k: v for k, v in call.data.items() if k != "device_id"}
        if "icon" in payload:
            payload["icon"] = await _provision_icon(call.data["device_id"], payload["icon"])
        try:
            await client.send_notification(payload)
        except Exception as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_app_update(call: ServiceCall) -> None:
        client = _get_client_for_device(hass, call.data["device_id"])
        app_payload = call.data["payload"]
        if "icon" in app_payload:
            app_payload["icon"] = await _provision_icon(call.data["device_id"], app_payload["icon"])
        try:
            await client.send_app(call.data["name"], app_payload)
        except Exception as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_app_remove(call: ServiceCall) -> None:
        client = _get_client_for_device(hass, call.data["device_id"])
        try:
            await client.remove_app(call.data["name"])
        except Exception as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_play_rtttl(call: ServiceCall) -> None:
        client = _get_client_for_device(hass, call.data["device_id"])
        try:
            await client.play_rtttl(call.data["melody"])
        except Exception as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_update_settings(call: ServiceCall) -> None:
        client = _get_client_for_device(hass, call.data["device_id"])
        try:
            await client.update_settings(call.data["settings"])
        except Exception as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_switch_app(call: ServiceCall) -> None:
        client = _get_client_for_device(hass, call.data["device_id"])
        try:
            await client.switch_app(call.data["name"])
        except Exception as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_sleep(call: ServiceCall) -> None:
        client = _get_client_for_device(hass, call.data["device_id"])
        try:
            await client.sleep(call.data["seconds"])
        except Exception as err:
            raise HomeAssistantError(str(err)) from err

    async def handle_sync_icons(call: ServiceCall) -> None:
        device_id = call.data["device_id"]
        dev_reg = dr.async_get(hass)
        device = dev_reg.async_get(device_id)
        if device is None:
            raise HomeAssistantError(f"Device {device_id} not found")
        for entry_id in device.config_entries:
            if entry_id in hass.data.get(DOMAIN, {}):
                data = hass.data[DOMAIN][entry_id]
                c = data.get("icon_client")
                _LOGGER.info(
                    "sync_icons: entry=%s icon_client=%s client_type=%s",
                    entry_id, type(c).__name__ if c else None,
                    type(data["client"]).__name__,
                )
                if c is None:
                    main_client = data["client"]
                    if isinstance(main_client, AwtrixHttpClient):
                        c = main_client
                    else:
                        raise HomeAssistantError(
                            "No HTTP connection available for icon sync. "
                            "Set the Device IP Address in Configure and restart."
                        )
                icon_ids = get_all_icon_ids()
                _LOGGER.info("sync_icons: provisioning %d icons via %s", len(icon_ids), type(c).__name__)
                try:
                    await c.ensure_icons(icon_ids)
                except Exception as err:
                    raise HomeAssistantError(str(err)) from err
                return
        raise HomeAssistantError(f"No AWTRIX integration found for device {device_id}")

    handlers = {
        "notify": handle_notify,
        "app_update": handle_app_update,
        "app_remove": handle_app_remove,
        "play_rtttl": handle_play_rtttl,
        "update_settings": handle_update_settings,
        "switch_app": handle_switch_app,
        "sleep": handle_sleep,
        SERVICE_SYNC_ICONS: handle_sync_icons,
    }

    for service_name, handler in handlers.items():
        hass.services.async_register(
            DOMAIN, service_name, handler, schema=SERVICE_SCHEMAS[service_name]
        )
