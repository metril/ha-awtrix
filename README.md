# AWTRIX 3 for Home Assistant

A full-featured Home Assistant custom integration for [AWTRIX 3](https://github.com/Blueforcer/awtrix3) LED matrix displays (e.g., Ulanzi TC001).

## Features

- **Dual transport** — connect via HTTP or MQTT
- **Multi-device** — manage multiple AWTRIX displays
- **20+ entities** — sensors, lights, switches, buttons, and more
- **7 services** — notifications, custom apps, sounds, settings control
- **Built-in app templates** — weather, temperature, humidity, battery, date, time, countdown, text — automatically pushed from your HA entities

## Installation

### HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=metril&repository=ha-awtrix&category=integration)

Or manually:

1. Open HACS in your Home Assistant instance
2. Click the three-dot menu and select **Custom repositories**
3. Add `https://github.com/metril/ha-awtrix` with category **Integration**
4. Click **Download**
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/awtrix` folder to your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Setup

1. Go to **Settings > Devices & Services > Add Integration**
2. Search for **AWTRIX 3**
3. Choose your connection method:
   - **HTTP** — enter your device's IP address
   - **MQTT** — enter your device's MQTT topic prefix (requires MQTT integration)

## Entities

| Platform | Entities |
|---|---|
| **Sensor** | Temperature, Humidity, Battery, Illuminance, WiFi Signal, Free RAM, Uptime, Firmware, Current App, IP Address |
| **Binary Sensor** | Online status |
| **Switch** | Power on/off, Auto Brightness, Night Mode |
| **Number** | Brightness (0-255, tracks actual device brightness), Volume (0-30), App Duration (1-300s) |
| **Select** | Transition Effect |
| **Button** | Reboot, Next App, Previous App, Dismiss Notification |
| **Light** | Moodlight (RGB + color temperature), Indicator 1, Indicator 2, Indicator 3 |

## Services

| Service | Description |
|---|---|
| `awtrix.notify` | Send a temporary notification with text, icon, color, sound, effects |
| `awtrix.app_update` | Create or update a persistent custom app in the display rotation |
| `awtrix.app_remove` | Remove a custom app |
| `awtrix.play_rtttl` | Play an RTTTL melody on the buzzer |
| `awtrix.update_settings` | Send arbitrary settings to the device |
| `awtrix.switch_app` | Switch to a specific named app |
| `awtrix.sleep` | Put the device to sleep for a duration |
| `awtrix.sync_icons` | Download and upload all built-in icons to the device |

## Night Mode

Night mode dims or turns off the display on a schedule or manually via the Night Mode switch. Configure in the options flow:

- **Night brightness** — set to 0 to turn off the display entirely, or a low value (1-30) to dim
- **Schedule** — optional start/end times (e.g., 22:00 to 07:00) to automatically toggle night mode
- **Presence sensor** — optional binary sensor that disables the display when no one is present (works at all hours, independent of the schedule)

When night mode activates, it saves the current brightness and auto-transition state, dims the display, disables app rotation, and switches to the Time app. When it deactivates, it restores the previous settings.

## Auto Brightness

The Ulanzi TC001 has a built-in light sensor. Enable the Auto Brightness switch to let the device adjust display brightness based on ambient light. The Brightness entity tracks the actual device brightness in real time, updating with every stats message from the device.

## MQTT Setup

When using MQTT, the integration auto-discovers AWTRIX devices via Home Assistant's MQTT discovery protocol. It detects devices using ArduinoHA's abbreviated discovery keys.

For icon provisioning and initial settings fetch, provide the device's IP address in the MQTT config flow (optional but recommended). Without it, icons cannot be uploaded and settings rely on optimistic updates only.

## Built-in App Templates

Configure in **Settings > Devices & Services > AWTRIX 3 > Configure**:

| Template | Description |
|---|---|
| **Weather** | Current conditions, today's forecast, hourly forecast, daily/weekly forecast — with weather icons |
| **Temperature** | Display any HA temperature sensor |
| **Humidity** | Display any HA humidity sensor |
| **Battery** | Battery level with color coding (green/yellow/red) |
| **Date** | Current date in configurable format (US, European, ISO, etc.); long formats scroll automatically so the full date is never clipped |
| **Time** | Current time in configurable format (12h, 24h) |
| **Countdown** | Countdown from timer or input_datetime entity |
| **Text** | Display any input_text entity value |

Each template automatically updates the AWTRIX display when the source entity changes state.

## Weather Display Modes

The weather template supports 4 display modes (each creates a separate app in the rotation):

- **Current** — condition icon + temperature + condition text
- **Today's Forecast** — high/low temperatures + condition
- **Hourly** — scrolling next 3-6 hours with temperatures
- **Daily/Weekly** — scrolling next 3-7 days with high/low temperatures

Weather icons use the [LaMetric icon database](https://developer.lametric.com/icons) and can be overridden per condition. Temperature-based color coding automatically adapts to Fahrenheit or Celsius based on the weather entity's unit.

## Example Automations

### Send a notification when someone arrives home

```yaml
automation:
  - trigger:
      - platform: state
        entity_id: person.john
        to: "home"
    action:
      - service: awtrix.notify
        data:
          device_id: <your_awtrix_device_id>
          text: "John is home!"
          icon: "10514"
          duration: 10
          sound: "notification"
```

### Display a custom app with live data

```yaml
automation:
  - trigger:
      - platform: state
        entity_id: sensor.electricity_price
    action:
      - service: awtrix.app_update
        data:
          device_id: <your_awtrix_device_id>
          name: electricity
          payload:
            text: "{{ states('sensor.electricity_price') }} ct/kWh"
            icon: "4834"
            color: [0, 255, 0]
```

## License

Proprietary — Copyright (c) 2026 metril. All rights reserved.

This software is **not** open source. It may not be used, copied, modified, or
distributed in any way without the express written permission of the owner and a
valid subscription. See [LICENSE](LICENSE) for the full terms.
