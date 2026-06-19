"""Compile LinkML schema dictionaries into DataHarmonizer schema JSON."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import yaml


def compile_schema_json(schema: dict[str, Any]) -> dict[str, Any]:
    """Return the DataHarmonizer schema JSON representation for a LinkML schema.

    This mirrors the core behavior of DataHarmonizer's ``script/linkml.py``:
    imports are merged, induced classes are expanded, and the result is emitted
    with LinkML Runtime's JSON dumper.
    """
    from linkml_runtime.dumpers import json_dumper
    from linkml_runtime.utils.schemaview import SchemaView

    schema_copy = copy.deepcopy(schema)
    in_language = schema_copy.get("in_language")
    schema_view = SchemaView(yaml.dump(schema_copy, sort_keys=False))
    schema_view.merge_imports()

    for class_name, class_def in schema_view.all_classes().items():
        if not class_def.slots:
            continue
        induced = schema_view.induced_class(class_name)
        induced.name = class_name
        schema_view.add_class(induced)

    if in_language is not None:
        schema_view.schema.in_language = in_language

    return json.loads(json_dumper.dumps(schema_view.schema))


def compile_yaml_text(yaml_text: str) -> dict[str, Any]:
    """Return DataHarmonizer schema JSON for LinkML YAML text."""
    loaded = yaml.safe_load(yaml_text)
    if not isinstance(loaded, dict):
        raise ValueError("Expected a LinkML YAML mapping at the document root.")
    return compile_schema_json(loaded)


def compile_yaml_file(path: str | Path) -> dict[str, Any]:
    """Return DataHarmonizer schema JSON for a LinkML YAML file."""
    return compile_yaml_text(Path(path).read_text(encoding="utf-8"))
