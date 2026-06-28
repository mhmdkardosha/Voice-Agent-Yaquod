from config.constants import VALID_AIRFLOW_MODES, VALID_FAN_SPEEDS, VALID_WINDOWS, VALID_ZONES

EXPECTED_PARAMETERS = {
    "ac_on": set(),
    "ac_off": set(),
    "set_temperature": {"zone", "temperature"},
    "set_fan_speed": {"speed"},
    "set_airflow_mode": {"mode"},
    "climate_auto": {"enabled"},
    "climate_sync": {"enabled"},
    "window_open": {"window", "percentage"},
    "window_close": {"window", "percentage"},
    "music_play": set(),
    "music_pause": set(),
    "set_volume": {"change"},
}


def validate_vehicle_action(action: str, parameters: dict | None) -> str | None:
    """
    Returns:
        None -> validation passed.
        str  -> validation error message.
    """

    parameters = parameters or {}

    # Reject missing or unexpected parameters
    expected = EXPECTED_PARAMETERS.get(action)
    if expected is not None and set(parameters.keys()) != expected:
        return "Invalid parameters."

    # Climate action validation
    if action == "set_temperature":
        zone = parameters["zone"]
        temperature = parameters["temperature"]

        if zone not in VALID_ZONES:
            return "Invalid climate zone."

        if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
            return "Invalid temperature."

        if not (16 <= temperature <= 30):
            return "Temperature must be between 16 and 30."

    elif action == "set_fan_speed":
        speed = parameters["speed"]

        if speed not in VALID_FAN_SPEEDS:
            return "Invalid fan speed."

    elif action == "set_airflow_mode":
        mode = parameters["mode"]

        if mode not in VALID_AIRFLOW_MODES:
            return "Invalid airflow mode."

    elif action == "climate_auto":
        enabled = parameters["enabled"]

        if not isinstance(enabled, bool):
            return "Invalid auto mode."

    elif action == "climate_sync":
        enabled = parameters["enabled"]

        if not isinstance(enabled, bool):
            return "Invalid sync mode."

    # Window action validation
    elif action in {"window_open", "window_close"}:
        window = parameters["window"]
        percentage = parameters["percentage"]

        if window not in VALID_WINDOWS:
            return "Invalid window."

        if type(percentage) is not int:
            return "Invalid percentage."

        if not (0 <= percentage <= 100):
            return "Percentage must be between 0 and 100."

    # Media action validation
    elif action == "set_volume":
        change = parameters["change"]

        if type(change) is not int:
            return "Invalid volume change."

        if not (-100 <= change <= 100):
            return "Volume change must be between -100 and 100."

    return None
