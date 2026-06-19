"""Convert between LinkML dictionaries and editable Schemasheets-like tables."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import yaml

from .diagnostics import Diagnostic

JsonDict = dict[str, Any]
TableRows = dict[str, list[JsonDict]]

SCHEMA_TABLE = "schema"
PREFIX_TABLE = "prefixes"
CLASS_TABLE = "classes"
SLOT_TABLE = "slots"
ENUM_TABLE = "enums"
PERMISSIBLE_VALUE_TABLE = "permissible_values"
ANNOTATION_TABLE = "annotations"


def schema_to_tables(schema: Mapping[str, Any]) -> TableRows:
    """Return editable tables for a LinkML schema."""
    return {
        SCHEMA_TABLE: [_schema_row(schema)],
        PREFIX_TABLE: _prefix_rows(schema),
        CLASS_TABLE: _class_rows(schema),
        SLOT_TABLE: _slot_rows(schema),
        ENUM_TABLE: _enum_rows(schema),
        PERMISSIBLE_VALUE_TABLE: _permissible_value_rows(schema),
        ANNOTATION_TABLE: _annotation_rows(schema),
    }


def tables_to_schema(tables: Mapping[str, list[JsonDict]]) -> tuple[dict[str, Any], list[Diagnostic]]:
    """Build a LinkML schema dictionary from editable tables."""
    diagnostics: list[Diagnostic] = []
    schema_row = _first_row(tables.get(SCHEMA_TABLE, []))
    schema = _schema_from_row(schema_row)
    _apply_prefixes(schema, tables.get(PREFIX_TABLE, []))
    _apply_classes(schema, tables.get(CLASS_TABLE, []), diagnostics)
    _apply_slots(schema, tables.get(SLOT_TABLE, []), diagnostics)
    _apply_slot_usage(schema, tables.get(SLOT_TABLE, []))
    _apply_enums(schema, tables.get(ENUM_TABLE, []), tables.get(PERMISSIBLE_VALUE_TABLE, []))
    _apply_annotations(schema, tables.get(ANNOTATION_TABLE, []), diagnostics)
    return schema, diagnostics


def table_specs() -> dict[str, list[list[str]]]:
    """Return Schemasheets-style header and descriptor rows for each table."""
    return {
        SCHEMA_TABLE: [
            ["schema", "id", "name", "title", "description", "version", "default_range", "imports"],
            ["> schema", "> id", "> name", "> title", "> description", "> version", "> default_range", "> imports"],
        ],
        PREFIX_TABLE: [["prefix", "reference"], ["> prefix", "> prefix_reference"]],
        CLASS_TABLE: [
            ["class", "title", "description", "is_a", "slots", "from_schema"],
            ["> class", "> title", "> description", "> is_a", "> slots", "> from_schema"],
        ],
        SLOT_TABLE: [
            [
                "class",
                "slot",
                "rank",
                "slot_group",
                "title",
                "description",
                "range",
                "required",
                "recommended",
                "ifabsent",
                "pattern",
                "comments",
            ],
            [
                "> class",
                "> slot",
                "> rank",
                "> slot_group",
                "> title",
                "> description",
                "> range",
                "> required",
                "> recommended",
                "> ifabsent",
                "> pattern",
                "> comments",
            ],
        ],
        ENUM_TABLE: [
            ["enum", "description", "annotations"],
            ["> enum", "> description", "> annotations"],
        ],
        PERMISSIBLE_VALUE_TABLE: [
            ["enum", "permissible_value", "text", "description", "meaning", "comments"],
            ["> enum", "> permissible_value", "> text", "> description", "> meaning", "> comments"],
        ],
    }


def _schema_row(schema: Mapping[str, Any]) -> JsonDict:
    return {
        "schema": schema.get("name", ""),
        "id": schema.get("id", ""),
        "name": schema.get("name", ""),
        "title": schema.get("title", ""),
        "description": schema.get("description", ""),
        "version": schema.get("version", ""),
        "default_range": schema.get("default_range", ""),
        "imports": _join_list(schema.get("imports")),
    }


def _prefix_rows(schema: Mapping[str, Any]) -> list[JsonDict]:
    prefixes = schema.get("prefixes") or {}
    return [{"prefix": name, "reference": _prefix_reference(value)} for name, value in prefixes.items()]


def _class_rows(schema: Mapping[str, Any]) -> list[JsonDict]:
    rows = []
    for class_name, class_def in (schema.get("classes") or {}).items():
        rows.append(
            {
                "class": class_name,
                "title": class_def.get("title", ""),
                "description": class_def.get("description", ""),
                "is_a": class_def.get("is_a", ""),
                "slots": _join_list(class_def.get("slots")),
                "from_schema": class_def.get("from_schema", ""),
            }
        )
    return rows


def _slot_rows(schema: Mapping[str, Any]) -> list[JsonDict]:
    slots = schema.get("slots") or {}
    rows: list[JsonDict] = []
    for class_name, class_def in (schema.get("classes") or {}).items():
        if class_name == "dh_interface":
            continue
        slot_usage = class_def.get("slot_usage") or {}
        for slot_name in class_def.get("slots") or []:
            slot_def = slots.get(slot_name, {})
            usage = slot_usage.get(slot_name, {})
            rows.append(_slot_row(class_name, slot_name, slot_def, usage))
    known = {row["slot"] for row in rows}
    for slot_name, slot_def in slots.items():
        if slot_name not in known:
            rows.append(_slot_row("", slot_name, slot_def, {}))
    return rows


def _slot_row(
    class_name: str,
    slot_name: str,
    slot_def: Mapping[str, Any],
    usage: Mapping[str, Any],
) -> JsonDict:
    annotations = slot_def.get("annotations") or {}
    return {
        "class": class_name,
        "slot": slot_name,
        "rank": usage.get("rank", slot_def.get("rank", "")),
        "slot_group": usage.get("slot_group", slot_def.get("slot_group", "")),
        "title": slot_def.get("title", ""),
        "description": slot_def.get("description", ""),
        "range": slot_def.get("range", ""),
        "required": _bool_to_cell(slot_def.get("required")),
        "recommended": _bool_to_cell(slot_def.get("recommended")),
        "ifabsent": slot_def.get("ifabsent", ""),
        "pattern": slot_def.get("pattern", ""),
        "comments": _join_list(slot_def.get("comments")),
        "annotation_id": annotations.get("id", ""),
        "annotation_source": annotations.get("source", ""),
        "annotation_mimicc_default_unit": annotations.get("mimicc_default_unit", ""),
    }


def _enum_rows(schema: Mapping[str, Any]) -> list[JsonDict]:
    rows = []
    for enum_name, enum_def in (schema.get("enums") or {}).items():
        rows.append(
            {
                "enum": enum_name,
                "permissible_value": "",
                "description": enum_def.get("description", ""),
                "annotations": _compact_mapping(enum_def.get("annotations") or {}),
            }
        )
    return rows


def _permissible_value_rows(schema: Mapping[str, Any]) -> list[JsonDict]:
    rows = []
    for enum_name, enum_def in (schema.get("enums") or {}).items():
        for value, value_def in (enum_def.get("permissible_values") or {}).items():
            value_def = value_def or {}
            rows.append(
                {
                    "enum": enum_name,
                    "permissible_value": value,
                    "text": value_def.get("text", value),
                    "description": value_def.get("description", ""),
                    "meaning": value_def.get("meaning", ""),
                    "comments": _join_list(value_def.get("comments")),
                }
            )
    return rows


def _annotation_rows(schema: Mapping[str, Any]) -> list[JsonDict]:
    rows = []
    for slot_name, slot_def in (schema.get("slots") or {}).items():
        for key, value in (slot_def.get("annotations") or {}).items():
            rows.append({"element_type": "slot", "element": slot_name, "key": key, "value": value})
    for class_name, class_def in (schema.get("classes") or {}).items():
        for key, value in (class_def.get("annotations") or {}).items():
            rows.append({"element_type": "class", "element": class_name, "key": key, "value": value})
    return rows


def _schema_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    schema = {
        "id": row.get("id") or f"https://example.org/{row.get('name') or 'schema'}",
        "name": row.get("name") or row.get("schema") or "schema",
    }
    for key in ("title", "description", "version", "default_range"):
        if row.get(key):
            schema[key] = row[key]
    imports = _split_list(row.get("imports"))
    if imports:
        schema["imports"] = imports
    return schema


def _apply_prefixes(schema: dict[str, Any], rows: list[JsonDict]) -> None:
    prefixes = {}
    for row in rows:
        name = _clean(row.get("prefix"))
        if name:
            prefixes[name] = _clean(row.get("reference"))
    if prefixes:
        schema["prefixes"] = prefixes


def _apply_classes(
    schema: dict[str, Any],
    rows: list[JsonDict],
    diagnostics: list[Diagnostic],
) -> None:
    classes = {}
    for index, row in enumerate(rows, start=1):
        class_name = _clean(row.get("class"))
        if not class_name:
            diagnostics.append(Diagnostic("warning", "Class row has no class name.", CLASS_TABLE, index))
            continue
        class_def = {}
        for key in ("title", "description", "is_a", "from_schema"):
            if row.get(key):
                class_def[key] = row[key]
        slots = _split_list(row.get("slots"))
        if slots:
            class_def["slots"] = slots
        classes[class_name] = class_def
    if classes:
        schema["classes"] = classes


def _apply_slots(
    schema: dict[str, Any],
    rows: list[JsonDict],
    diagnostics: list[Diagnostic],
) -> None:
    slots = {}
    for index, row in enumerate(rows, start=1):
        slot_name = _clean(row.get("slot"))
        if not slot_name:
            diagnostics.append(Diagnostic("warning", "Slot row has no slot name.", SLOT_TABLE, index))
            continue
        slot_def = slots.setdefault(slot_name, {})
        for key in ("title", "description", "range", "ifabsent", "pattern"):
            if row.get(key):
                slot_def[key] = row[key]
        for key in ("required", "recommended"):
            value = _cell_to_bool(row.get(key))
            if value is not None:
                slot_def[key] = value
        comments = _split_list(row.get("comments"))
        if comments:
            slot_def["comments"] = comments
        annotations = _slot_annotations(row)
        if annotations:
            slot_def["annotations"] = annotations
    if slots:
        schema["slots"] = slots


def _apply_slot_usage(schema: dict[str, Any], rows: list[JsonDict]) -> None:
    classes = schema.setdefault("classes", {})
    by_class: dict[str, list[JsonDict]] = {}
    for row in rows:
        class_name = _clean(row.get("class"))
        slot_name = _clean(row.get("slot"))
        if not class_name or not slot_name:
            continue
        by_class.setdefault(class_name, []).append(row)

    for class_name, class_rows in by_class.items():
        class_def = classes.setdefault(class_name, {})
        class_def["slots"] = [_clean(row.get("slot")) for row in class_rows]
        slot_usage = {}
        for index, row in enumerate(class_rows, start=1):
            slot_name = _clean(row.get("slot"))
            usage = {"rank": _rank_value(row.get("rank"), index)}
            if row.get("slot_group"):
                usage["slot_group"] = row["slot_group"]
            slot_usage[slot_name] = usage
        if slot_usage:
            class_def["slot_usage"] = slot_usage


def _apply_enums(
    schema: dict[str, Any],
    enum_rows: list[JsonDict],
    value_rows: list[JsonDict],
) -> None:
    enums = {}
    for row in enum_rows:
        enum_name = _clean(row.get("enum"))
        if not enum_name:
            continue
        enum_def = enums.setdefault(enum_name, {"permissible_values": {}})
        if row.get("description"):
            enum_def["description"] = row["description"]
        annotations = _parse_mapping_cell(row.get("annotations"))
        if annotations:
            enum_def["annotations"] = annotations
    for row in value_rows:
        enum_name = _clean(row.get("enum"))
        value = _clean(row.get("permissible_value"))
        if not enum_name or not value:
            continue
        enum_def = enums.setdefault(enum_name, {"permissible_values": {}})
        value_def = {}
        for key in ("text", "description", "meaning"):
            if row.get(key):
                value_def[key] = row[key]
        comments = _split_list(row.get("comments"))
        if comments:
            value_def["comments"] = comments
        enum_def["permissible_values"][value] = value_def or {"text": value}
    if enums:
        schema["enums"] = enums


def _apply_annotations(
    schema: dict[str, Any],
    rows: list[JsonDict],
    diagnostics: list[Diagnostic],
) -> None:
    for index, row in enumerate(rows, start=1):
        element_type = _clean(row.get("element_type"))
        element = _clean(row.get("element"))
        key = _clean(row.get("key"))
        if not element_type or not element or not key:
            continue
        container = schema.get(_element_container_key(element_type))
        if not isinstance(container, dict) or element not in container:
            diagnostics.append(Diagnostic("warning", "Annotation target was not found.", ANNOTATION_TABLE, index))
            continue
        container[element].setdefault("annotations", {})[key] = row.get("value", "")


def _first_row(rows: list[JsonDict]) -> JsonDict:
    return rows[0] if rows else {}


def _slot_annotations(row: Mapping[str, Any]) -> dict[str, Any]:
    annotations = {}
    for row_key, annotation_key in (
        ("annotation_id", "id"),
        ("annotation_source", "source"),
        ("annotation_mimicc_default_unit", "mimicc_default_unit"),
    ):
        if row.get(row_key):
            annotations[annotation_key] = row[row_key]
    return annotations


def _prefix_reference(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(value.get("prefix_reference", ""))
    return "" if value is None else str(value)


def _join_list(value: Any) -> str:
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return "" if value is None else str(value)


def _split_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    return [part.strip() for part in str(value).split(";") if part.strip()]


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _bool_to_cell(value: Any) -> str:
    if value is None:
        return ""
    return "true" if bool(value) else "false"


def _cell_to_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _compact_mapping(value: Mapping[str, Any]) -> str:
    if not value:
        return ""
    return json.dumps(value, ensure_ascii=False)


def _parse_mapping_cell(value: Any) -> dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    try:
        parsed = yaml.safe_load(str(value))
    except yaml.YAMLError:
        return {}
    return dict(parsed) if isinstance(parsed, Mapping) else {}


def _element_container_key(element_type: str) -> str:
    if element_type == "class":
        return "classes"
    if element_type == "enum":
        return "enums"
    return f"{element_type}s"


def _rank_value(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
