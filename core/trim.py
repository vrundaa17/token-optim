from typing import Any

def _get_nested(data: dict, path: str) -> Any:
    """Supports dot-notation paths like 'current.temperature_2m'."""
    keys = path.split(".")
    value = data
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return None
    return value

def trim_response(raw_response: dict, field_map: dict[str, str]) -> dict:
    """
    Generic trimmer for ANY tool's response.

    raw_response: the full raw API/tool output
    field_map: {output_key: source_path}
               e.g. {"temperature_c": "current.temperature_2m"}

    Works for any tool as long as you supply the right field_map —
    no tool-specific code needed here.
    """
    return {
        output_key: _get_nested(raw_response, source_path)
        for output_key, source_path in field_map.items()
    }