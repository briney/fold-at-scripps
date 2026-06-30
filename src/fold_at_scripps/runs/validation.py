"""Validation of submitted run parameters against a tool's JSON Schema."""

from __future__ import annotations

from typing import Any

import jsonschema


class InvalidParams(Exception):
    """Raised when submitted params do not satisfy the tool's input schema."""


def validate_params(params: dict[str, Any], schema: dict[str, Any]) -> None:
    """Validate ``params`` against the tool's JSON Schema; raise InvalidParams if invalid."""
    try:
        jsonschema.validate(instance=params, schema=schema)
    except jsonschema.ValidationError as exc:
        raise InvalidParams(exc.message) from exc
