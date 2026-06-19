"""Lightweight diagnostics for generated LinkML schemas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Diagnostic:
    """A user-facing diagnostic produced by schema conversion helpers."""

    level: str
    message: str
    table: str | None = None
    row: int | None = None
    path: str | None = None


def validate_schema(schema: dict[str, Any]) -> list[Diagnostic]:
    """Return structural diagnostics for a generated LinkML schema."""
    diagnostics = []
    if not schema.get("name"):
        diagnostics.append(Diagnostic("error", "Schema has no name.", path="name"))
    if not schema.get("classes"):
        diagnostics.append(Diagnostic("error", "Schema has no classes.", path="classes"))
    if not schema.get("slots"):
        diagnostics.append(Diagnostic("warning", "Schema has no slots.", path="slots"))
    diagnostics.extend(_missing_enum_diagnostics(schema))
    return diagnostics


def _missing_enum_diagnostics(schema: dict[str, Any]) -> list[Diagnostic]:
    enums = schema.get("enums") or {}
    primitive_ranges = {
        "boolean",
        "date",
        "datetime",
        "decimal",
        "double",
        "float",
        "integer",
        "string",
        "time",
        "uri",
        "uriorcurie",
    }
    diagnostics = []
    for slot_name, slot_def in (schema.get("slots") or {}).items():
        slot_range = slot_def.get("range")
        if slot_range and slot_range not in enums and slot_range not in primitive_ranges:
            diagnostics.append(
                Diagnostic(
                    "info",
                    f"{slot_name} range {slot_range} is not a local enum or primitive type.",
                    path=f"slots.{slot_name}.range",
                )
            )
    return diagnostics
