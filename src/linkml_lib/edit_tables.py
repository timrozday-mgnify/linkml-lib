"""Convert between LinkML dictionaries and editable tables.

This module reimplements the Schemasheets-inspired subset needed by
DataHarmonizer editor applications. It keeps conversion in memory over
JSON-like rows, preserves MIMICC/DataHarmonizer editing conventions, and avoids
runtime dependence on the upstream Schemasheets package or CLI tools. It is not
a full Schemasheets replacement.
"""

from __future__ import annotations

import copy
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

SLOT_ANNOTATION_COLUMN_PREFIX = "Annotation: "
LEGACY_ANNOTATION_COLUMN_PREFIX = "annotation_"
LEGACY_SLOT_ANNOTATION_KEYS = {"mimicc_default_unit": "default_unit"}
DEFAULT_SLOT_ANNOTATION_COLUMNS = ("Annotation: id", "Annotation: default_unit")


def schema_to_tables(schema: Mapping[str, Any]) -> TableRows:
    """Return editable tables for a LinkML schema.

    Each slot's annotations are projected as ``"Annotation: <key>"`` columns on
    its slot row; every slot row carries at least the default annotation columns.
    """
    slot_rows = _slot_rows(schema)
    _ensure_slot_annotation_columns(slot_rows)
    return {
        SCHEMA_TABLE: [_schema_row(schema)],
        PREFIX_TABLE: _prefix_rows(schema),
        CLASS_TABLE: _class_rows(schema),
        SLOT_TABLE: slot_rows,
        ENUM_TABLE: _enum_rows(schema),
        PERMISSIBLE_VALUE_TABLE: _permissible_value_rows(schema),
        ANNOTATION_TABLE: _annotation_rows(schema),
    }


def tables_to_schema(tables: Mapping[str, list[JsonDict]]) -> tuple[dict[str, Any], list[Diagnostic]]:
    """Build a LinkML schema dictionary from editable tables.

    ``"Annotation: <key>"`` slot-row columns (and legacy ``annotation_<key>``
    columns) are folded back into each slot's annotations.
    """
    tables = _tables_with_slot_annotation_rows(tables)
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
    """Return Schemasheets-inspired header and descriptor rows for each table."""
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
                "Annotation: id",
                "Annotation: default_unit",
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
                '> annotations: {inner_key: "id"}',
                '> annotations: {inner_key: "default_unit"}',
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
    row = {
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
    }
    for key, value in (slot_def.get("annotations") or {}).items():
        row[_annotation_column_for_key(_normalized_annotation_key(key))] = "" if value is None else value
    return row


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
        if element_type == "slot" and key == "mimicc_default_unit":
            key = "default_unit"
        container = schema.get(_element_container_key(element_type))
        if not isinstance(container, dict) or element not in container:
            diagnostics.append(Diagnostic("warning", "Annotation target was not found.", ANNOTATION_TABLE, index))
            continue
        container[element].setdefault("annotations", {})[key] = row.get("value", "")


def _first_row(rows: list[JsonDict]) -> JsonDict:
    return rows[0] if rows else {}


def _ensure_slot_annotation_columns(slot_rows: list[JsonDict]) -> None:
    """Make every slot row carry the same set of ``"Annotation: <key>"`` columns."""
    columns: list[str] = list(DEFAULT_SLOT_ANNOTATION_COLUMNS)
    for row in slot_rows:
        columns.extend(column for column in row if _is_slot_annotation_column(column))
    columns = list(dict.fromkeys(columns))
    for row in slot_rows:
        for column in columns:
            row.setdefault(column, "")


def _tables_with_slot_annotation_rows(tables: Mapping[str, list[JsonDict]]) -> TableRows:
    """Fold ``"Annotation: <key>"`` slot columns back into ``ANNOTATION_TABLE`` rows."""
    prepared = copy.deepcopy(dict(tables))
    annotation_rows = prepared.setdefault(ANNOTATION_TABLE, [])
    for slot_row in prepared.get(SLOT_TABLE, []):
        _migrate_legacy_slot_annotation_columns(slot_row)
        slot_name = _clean(slot_row.get("slot"))
        if not slot_name:
            continue
        slot_columns = _slot_annotation_columns_for_row(slot_row)
        annotation_rows[:] = [
            row
            for row in annotation_rows
            if not (
                _clean(row.get("element_type")) == "slot"
                and _clean(row.get("element")) == slot_name
                and _annotation_column_for_key(_normalized_annotation_key(_clean(row.get("key"))))
                in slot_columns
            )
        ]
        for column in slot_columns:
            value = slot_row.get(column)
            if value in (None, ""):
                continue
            annotation_rows.append(
                {
                    "element_type": "slot",
                    "element": slot_name,
                    "key": _annotation_key_for_column(column),
                    "value": value,
                }
            )
    return prepared


def _slot_annotation_columns_for_row(row: Mapping[str, Any]) -> list[str]:
    return [
        _annotation_column_for_key(_annotation_key_for_column(column))
        for column in row
        if _is_slot_annotation_column(column)
    ]


def _annotation_column_for_key(key: str) -> str:
    return f"{SLOT_ANNOTATION_COLUMN_PREFIX}{key}"


def _annotation_key_for_column(column: str) -> str:
    if column.startswith(SLOT_ANNOTATION_COLUMN_PREFIX):
        key = column.removeprefix(SLOT_ANNOTATION_COLUMN_PREFIX)
    else:
        key = column.removeprefix(LEGACY_ANNOTATION_COLUMN_PREFIX)
    return _normalized_annotation_key(key)


def _normalized_annotation_key(key: str) -> str:
    return LEGACY_SLOT_ANNOTATION_KEYS.get(key, key)


def _migrate_legacy_slot_annotation_columns(row: JsonDict) -> None:
    for column in list(row):
        if not _is_legacy_slot_annotation_column(column):
            continue
        canonical_column = _annotation_column_for_key(_annotation_key_for_column(column))
        if not _clean(row.get(canonical_column)) and _clean(row.get(column)):
            row[canonical_column] = row[column]
        row.pop(column, None)


def _is_slot_annotation_column(column: str) -> bool:
    return (
        column.startswith(SLOT_ANNOTATION_COLUMN_PREFIX)
        and column != SLOT_ANNOTATION_COLUMN_PREFIX
    ) or _is_legacy_slot_annotation_column(column)


def _is_legacy_slot_annotation_column(column: str) -> bool:
    return (
        column.startswith(LEGACY_ANNOTATION_COLUMN_PREFIX)
        and column != LEGACY_ANNOTATION_COLUMN_PREFIX
    )


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
