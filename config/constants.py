ALLOWED_ACTIONS = {
    "ac_on",
    "ac_off",
    "set_temperature",
    "set_fan_speed",
    "set_airflow_mode",
    "climate_auto",
    "climate_sync",
    "window_open",
    "window_close",
    "window_lock",
    "window_unlock",
    "music_play",
    "music_pause",
    "set_volume",
    "reading_light_on",
    "reading_light_off",
    "change_destination",
    "cancel_destination",
    "safe_stop",
    "seat_position",
    "seat_recline",
    "seat_height",
}

VALID_ZONES = {"left", "right", "both"}

VALID_WINDOWS = {
    "all",
    "front_left",
    "front_right",
    "rear_left",
    "rear_right",
}

VALID_FAN_SPEEDS = {0, 1, 2, 3, 4, 5}

VALID_AIRFLOW_MODES = {"face", "feet", "face_feet"}

VALID_SEAT_TYPE = {"driver", "passenger"}

VALID_LIGHT_TYPES = {"front", "rear", "both"}
