import os

def get_env_string(key: str, default: str) -> str:
    """Gets an environment variable, stripping inline comments like 'val # comment'."""
    val = os.getenv(key, default)
    if not val:
        return default
    return val.split("#")[0].strip()

def get_env_int(key: str, default: int) -> int:
    """Gets an environment variable as an integer, handling inline comments."""
    try:
        return int(get_env_string(key, str(default)))
    except ValueError:
        return default

def get_env_float(key: str, default: float) -> float:
    """Gets an environment variable as a float, handling inline comments."""
    try:
        return float(get_env_string(key, str(default)))
    except ValueError:
        return default
