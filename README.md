# Minjet MH7A-48 Home Assistant Integration

Custom Home Assistant integration for Minjet MH7A-48 energy storage systems.

This integration supports:
- Credential login via Minjet cloud API
- Automatic discovery of all devices on the account
- Regular REST polling (configurable interval)
- Optional WebSocket updates for near real-time values
- Derived power and energy sensors
- Home Assistant services for changing rated power, operation mode, and battery discharge limit
- Connection/debug sensors for diagnostics

## Disclaimer

This project is an unofficial community integration and is not affiliated with Minjet.

## Installation

### HACS (Custom repository)

1. Open HACS in Home Assistant.
2. Select the 3-dot menu in the top-right corner.
3. Open `Custom repositories`.
4. Add this repository URL.
5. Select repository type `Integration`.
6. Install `Minjet MH7A-48 Energy Storage`.
7. Restart Home Assistant.

### Manual installation

1. Copy the integration files to:
   `config/custom_components/minjet/`
2. Restart Home Assistant.
3. Add the integration from:
   `Settings -> Devices & Services -> Add Integration`

## Configuration

Configuration is handled via UI (`config_flow`).

Required:
- `username`
- `password`

Optional:
- `enable_websocket` (default: `false`)
- `scan_interval` in seconds (default: `10`, min: `5`, max: `300`)

## Sensors

### Raw sensors
- PV Total Power
- Output Power
- Battery Power Raw
- Battery Percentage
- Operation Mode
- Battery Charge Limit
- Battery Discharge Limit
- Temperature 1
- Temperature 2
- Cell Voltage Max
- Cell Voltage Min
- WiFi RSSI
- EM Feedback Value
- Battery Status
- Grid Import Power
- Grid Export Power

### Derived power sensors
- Battery Charge Power
- Battery Discharge Power
- PV to Inverter Power
- Battery to Inverter Power
- PV to Battery Power
- Cell Voltage Delta

### Derived energy sensors
- Solar Energy
- Battery Charge Energy
- Battery Discharge Energy

### Debug sensors
- Connection Mode
- WebSocket Connected
- Device Offline
- Offline Minutes

## Data behavior

- REST data is used as base data for each device on the account.
- If WebSocket is enabled and connected, incoming values are merged into REST data when a payload can be matched to a device.
- If WebSocket disconnects, the integration falls back to REST-only updates.

## Services

Available services:

```yaml
service: minjet.set_operation_mode
data:
  serial_num: MH7A482403200216
  operation_mode: erst_speichern
```

Accepted values:
- `erst_entladen`
- `erst_speichern`

```yaml
service: minjet.set_battery_discharge_limit
data:
  serial_num: MH7A482403200216
  battery_discharge_limit: 25
```

`battery_discharge_limit` follows the app constraint `20..100` in steps of `5`.
The app only exposes this limit while the device is in mode `erst speichern`.
The same visibility rule applies to the read-only `Battery Charge Limit` sensor.

```yaml
service: minjet.set_rated_power
data:
  serial_num: MH7A482403200216
  rated_power: 123
```

`rated_power` accepts values from `0` to `800`.

## Write Behavior

- `set_rated_power` has been observed to return quickly and consistently.
- `stacking/setProperty` writes can be slow and may occasionally time out at the HTTP layer.
- A timeout does not reliably mean that the device state did not change.
- After writes for operation mode or discharge limit, verify the resulting value via the updated entities or by refreshing state in Home Assistant.

## Troubleshooting

Add debug logging in `configuration.yaml`:

```yaml
logger:
  default: warning
  logs:
    custom_components.minjet: debug
```

Common checks:
- Verify username/password in integration configuration
- Disable WebSocket temporarily if your network blocks WSS traffic
- Increase scan interval if you run into rate-limit/network issues

## Support and issues

- Documentation: https://github.com/snoova/minjet-ha
- Issue tracker: https://github.com/snoova/minjet-ha/issues
