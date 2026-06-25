#!/usr/bin/env python3
"""Light behavioural tests for linkml_lib + dh_schema CLI.

Goal: smoke-test each operation. Uses small inline schema dicts where possible;
falls back to real fixtures for the conversion + DH-data tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from linkml_lib import convert_xml, convert_xsd, dh_data, diagnostics, edit_tables, io, pipeline, schema as schema_mod, transform


REPO = Path(__file__).resolve().parents[1]
ENA_REPO = REPO.parent / "ena-submission-dataharmonizer"
ERC_XML = ENA_REPO / "assets" / "ena_schema" / "ERC000015.xml"
SRA_XSD = ENA_REPO / "assets" / "ena_schema" / "SRA.study.xsd"
DH_DATA = ENA_REPO / "assets" / "test-fixtures" / "ERC000015_example.json"

requires_ena_assets = pytest.mark.skipif(
    not (ERC_XML.exists() and SRA_XSD.exists() and DH_DATA.exists()),
    reason="ENA fixture assets are not available",
)


# ---------------------------------------------------------------------------
# Inline fixtures
# ---------------------------------------------------------------------------

def _schema(slots, enums=None, name="Demo"):
    """Build a minimal LinkML schema dict for tests."""
    slot_names = list(slots.keys())
    s = {
        "id": "https://example.org/Demo",
        "name": name,
        "title": name,
        "classes": {
            "dh_interface": {},
            name: {
                "is_a": "dh_interface",
                "slots": slot_names,
                "slot_usage": {n: {"rank": i + 1} for i, n in enumerate(slot_names)},
            },
        },
        "slots": slots,
    }
    if enums:
        s["enums"] = enums
    return s


@pytest.fixture
def schema_a():
    return _schema({
        "alias": {"title": "Alias", "range": "string", "required": True},
        "status": {"title": "Status", "range": "StatusMenu"},
    }, enums={"StatusMenu": {"permissible_values": {"NEW": {"text": "NEW"}, "OLD": {"text": "OLD"}}}})


@pytest.fixture
def schema_b():
    return _schema({
        "alias": {"title": "Alias (B)", "range": "string"},
        "extra": {"title": "Extra", "range": "string"},
    }, name="Other")


# ---------------------------------------------------------------------------
# Loaders / converters
# ---------------------------------------------------------------------------

@requires_ena_assets
def test_convert_xml_real_checklist():
    s = convert_xml.from_path(ERC_XML, "https://example.org")
    assert s is not None
    assert len(s["slots"]) > 50
    assert "project_name" in s["slots"]
    assert s["slots"]["collection_date"]["annotations"]["id"] == "collection date"
    assert s["slots"]["sample_storage_temperature"]["annotations"]["ena_allowed_units"] == "°C"


@requires_ena_assets
def test_convert_xsd_real_xsd():
    s = convert_xsd.from_path(SRA_XSD, "https://example.org")
    assert s is not None
    assert "STUDY_TITLE" in s["slots"]
    assert s["slots"]["STUDY_TITLE"]["annotations"]["id"] == "STUDY_TITLE"


def test_load_any_dispatch_by_extension(tmp_path):
    yaml_file = tmp_path / "x.yaml"
    yaml_file.write_text("name: t\nslots: {}\nclasses: {}\n")
    assert io.load_any(yaml_file) is not None
    if ERC_XML.exists():
        assert io.load_any(ERC_XML) is not None
    if SRA_XSD.exists():
        assert io.load_any(SRA_XSD) is not None
    assert io.load_any(tmp_path / "unknown.txt") is None


def test_write_yaml_lowercase_bool(tmp_path, schema_a):
    out = tmp_path / "o.yaml"
    io.write_yaml(schema_a, out)
    text = out.read_text()
    assert "required: true" in text
    assert "required: True" not in text


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def test_merge_priority(schema_a, schema_b):
    merged = transform.merge([schema_a, schema_b])
    # alias is in both — first (schema_a) wins → title "Alias", not "Alias (B)"
    assert merged["slots"]["alias"]["title"] == "Alias"
    # extra came from schema_b
    assert "extra" in merged["slots"]


def test_merge_renumbers_ranks(schema_a, schema_b):
    merged = transform.merge([schema_a, schema_b])
    ranks = [u["rank"] for u in merged["classes"][merged["name"]]["slot_usage"].values()]
    assert ranks == list(range(1, len(ranks) + 1))


# ---------------------------------------------------------------------------
# Filter
# ---------------------------------------------------------------------------

def test_filter_include(schema_a):
    out = transform.filter(schema_a, include=["alias"])
    assert list(out["slots"].keys()) == ["alias"]
    # StatusMenu was referenced only by "status" — pruned
    assert "enums" not in out


def test_filter_exclude(schema_a):
    out = transform.filter(schema_a, exclude=["status"])
    assert list(out["slots"].keys()) == ["alias"]


def test_filter_prunes_unused_enums(schema_a):
    out = transform.filter(schema_a, exclude=["status"])
    assert "enums" not in out


def test_filter_keeps_referenced_enums(schema_a):
    out = transform.filter(schema_a, include=["status"])
    assert "StatusMenu" in out["enums"]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def test_merge_writes_top_level_source():
    xml_schema = convert_xml.from_path(ERC_XML, "https://example.org")
    merged = transform.merge([xml_schema], source_names=["ERC000025"])
    slot = merged["slots"]["collection_date"]
    assert slot["source"] == "ERC000025"
    assert "source" not in slot["annotations"]


@requires_ena_assets
def test_pipeline_build_xml_plus_xsd():
    s = pipeline.build([str(SRA_XSD), str(ERC_XML)])
    assert len(s["slots"]) > 80
    assert s.get("enums")


def test_pipeline_build_raises_on_no_valid_inputs(tmp_path):
    bad = tmp_path / "bad.txt"
    bad.write_text("nothing")
    with pytest.raises(ValueError):
        pipeline.build([str(bad)])


# ---------------------------------------------------------------------------
# Schema introspection
# ---------------------------------------------------------------------------

def test_slot_meta_has_expected_columns(schema_a):
    rows = schema_mod.slot_meta(schema_a)
    assert len(rows) == 2
    assert set(rows[0].keys()) == set(schema_mod.SLOT_META_COLUMNS)


def test_summary_totals(schema_a):
    s = schema_mod.summary(schema_a)
    assert s["total_slots"] == 2
    assert s["required_slots"] == 1
    assert s["total_enums"] == 1


def test_annotation_as_list_handles_list_string_and_none():
    assert schema_mod.annotation_as_list(None) == []
    assert schema_mod.annotation_as_list(["a", " b ", ""]) == ["a", "b"]
    assert schema_mod.annotation_as_list("a, b ,, c") == ["a", "b", "c"]


def test_allowed_units_from_comments_parses_convention():
    comments = ["Allowed units: g", "mg", "kg", "a longer comment that is not a unit token."]
    assert schema_mod.allowed_units_from_comments(comments) == ["g", "mg", "kg"]


def test_allowed_units_from_comments_no_marker_returns_empty():
    assert schema_mod.allowed_units_from_comments(["just a regular comment"]) == []


def test_unit_rules_from_annotation_and_comments_and_default():
    s = _schema({
        "temp": {
            "title": "Temperature",
            "range": "string",
            "annotations": {"id": "temperature", "ena_allowed_units": "C, F", "default_unit": "C"},
        },
        "vol": {
            "title": "Volume",
            "range": "string",
            "annotations": {"id": "volume", "mimicc_default_unit": "mL"},
            "comments": ["Allowed units: mL", "L"],
        },
        "plain": {"title": "Plain", "range": "string"},
    })
    rules = schema_mod.unit_rules(s)
    assert rules["temperature"] == schema_mod.UnitRule(("C", "F"), "C")
    assert rules["volume"] == schema_mod.UnitRule(("mL", "L"), "mL")
    assert "plain" not in rules


def test_diff_added_removed_changed(schema_a, schema_b):
    d = schema_mod.diff(schema_a, schema_b)
    assert "extra" in d["added"]
    assert "status" in d["removed"]
    # alias changed title between the two schemas
    assert any(c["name"] == "alias" for c in d["changed"])


# ---------------------------------------------------------------------------
# DataHarmonizer JSON data
# ---------------------------------------------------------------------------

@requires_ena_assets
def test_dh_filter_columns_real():
    with open(DH_DATA) as f:
        data = json.load(f)
    schema = io.load_xml(ERC_XML)
    out = dh_data.filter_columns(data, schema, "required = 1")
    rows = list(out["Container"].values())[0]
    if rows:
        # Only required-slot titles remain (or "alias")
        kept = set(rows[0].keys())
        assert kept  # at least some columns remain


def test_dh_remap_titles_to_names():
    schema = _schema({"alias": {"title": "Sample alias"}, "x": {"title": "X label"}})
    out = dh_data.remap_titles_to_names([{"Sample alias": "a1", "X label": "v"}], schema)
    assert out == [{"alias": "a1", "x": "v"}]


def test_dh_validate_required_missing():
    schema = _schema({"alias": {"name": "alias", "title": "Alias", "required": True}})
    report = dh_data.validate([{}], schema)
    assert dh_data.has_errors(report)
    assert any("alias" in r.message for r in report.results)


def test_dh_validate_passes():
    schema = _schema({"alias": {"name": "alias", "title": "Alias", "required": True}})
    report = dh_data.validate([{"alias": "x"}], schema)
    assert not dh_data.has_errors(report)


def test_dh_validate_enum_violation():
    schema = _schema(
        {"status": {"name": "status", "range": "StatusMenu"}},
        enums={"StatusMenu": {"permissible_values": {"NEW": {"text": "NEW"}}}},
    )
    report = dh_data.validate([{"status": "BOGUS"}], schema)
    assert dh_data.has_errors(report)
    assert any("status" in r.message or "BOGUS" in r.message for r in report.results)


def test_load_yaml_text_and_dump_yaml(schema_a):
    text = io.dump_yaml(schema_a)
    loaded = io.load_yaml_text(text)
    assert loaded["name"] == "Demo"
    assert "required: true" in text


def test_edit_tables_round_trip_preserves_enum(schema_a):
    tables = edit_tables.schema_to_tables(schema_a)
    out, table_diagnostics = edit_tables.tables_to_schema(tables)
    assert table_diagnostics == []
    assert out["slots"]["status"]["range"] == "StatusMenu"
    assert out["enums"]["StatusMenu"]["permissible_values"]["NEW"]["text"] == "NEW"


def test_diagnostics_missing_enum():
    schema = _schema({"status": {"range": "MissingMenu"}})
    messages = [diagnostic.message for diagnostic in diagnostics.validate_schema(schema)]
    assert any("MissingMenu" in message for message in messages)
