"""Typed JSON for the command-line contract tests."""

from pydantic import JsonValue, TypeAdapter

_JSON_OBJECT = TypeAdapter(type=dict[str, JsonValue])


def json_object(*, data: str | bytes) -> dict[str, JsonValue]:
    """Read a JSON object from a request or command output."""
    return _JSON_OBJECT.validate_json(data, strict=True)
