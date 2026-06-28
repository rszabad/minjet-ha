DOMAIN = "minjet"

API_BASE = "https://app.minjet-energy.com/prod-api"
LOGIN_ENDPOINT = f"{API_BASE}/login"
DEVICE_LIST_ENDPOINT = f"{API_BASE}/device/queryUserDeviceList"
DEVICE_PARAM_ENDPOINT = f"{API_BASE}/deviceDashboard/getDeviceParam"
STACKING_QUERY_ENDPOINT = f"{API_BASE}/stacking/queryStacking"
PHOTOVOLTAIC_QUERY_ENDPOINT = f"{API_BASE}/photovoltaic/queryPhotovoltaic"
SET_RATED_POWER_ENDPOINT = f"{API_BASE}/photovoltaic/setRatedPower"
SET_STACKING_PROPERTY_ENDPOINT = f"{API_BASE}/stacking/setProperty"

WSS_BASE = "wss://app.minjet-energy.com"
WSS_ENDPOINT = f"{WSS_BASE}/ws/device?token={{token}}"


CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_ENABLE_WEBSOCKET = "enable_websocket"
CONF_SCAN_INTERVAL = "scan_interval"

SERVICE_SET_RATED_POWER = "set_rated_power"
SERVICE_SET_OPERATION_MODE = "set_operation_mode"
SERVICE_SET_BATTERY_DISCHARGE_LIMIT = "set_battery_discharge_limit"
ATTR_SERIAL_NUM = "serial_num"
ATTR_RATED_POWER = "rated_power"
ATTR_OPERATION_MODE = "operation_mode"
ATTR_BATTERY_DISCHARGE_LIMIT = "battery_discharge_limit"
MODE_FIRST_DISCHARGE = "erst_entladen"
MODE_FIRST_STORE = "erst_speichern"

DEFAULT_SCAN_INTERVAL = 10
MIN_SCAN_INTERVAL = 5
MAX_SCAN_INTERVAL = 300
DEFAULT_ENABLE_WEBSOCKET = False
TOKEN_REFRESH_INTERVAL_SECONDS = 24 * 60 * 60
MIN_RATED_POWER = 0
MAX_RATED_POWER = 800
MIN_BATTERY_DISCHARGE_LIMIT = 20
MAX_BATTERY_DISCHARGE_LIMIT = 100
BATTERY_DISCHARGE_LIMIT_STEP = 5
