# linkml-lib

Reusable Python utilities for LinkML schemas used with DataHarmonizer and ENA submission tooling.

The distribution package is `linkml-lib`; the Python import package is `linkml_lib`.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Public API

The package preserves the existing ENA helper API:

```python
from linkml_lib import io, schema, transform, pipeline, dh_data
```

It also includes editable table conversion utilities for schema editor applications:

```python
from linkml_lib import edit_tables

tables = edit_tables.schema_to_tables(schema_dict)
schema, diagnostics = edit_tables.tables_to_schema(tables)
```

## Editable table conversion

`linkml_lib.edit_tables` is based on Schemasheets concepts, but it is a
purpose-built reimplementation rather than a wrapper around the upstream
`schemasheets` package or `linkml2sheets`/`sheets2linkml` CLI tools.

The reimplementation exists because DataHarmonizer editor applications need
in-memory `LinkML dict -> editable rows -> LinkML dict` conversion over
JSON-like row data, not spreadsheet files. It also keeps the supported editing
surface deliberately constrained for the MIMICC/DataHarmonizer workflow:
stable table names, separate enum and permissible-value tables, slot
usage/order preservation, annotation columns, and compatibility migrations.
Avoiding CLI subprocesses and temporary spreadsheet files makes the editor path
easier to test, embed, and reuse from local web applications.

This module is not intended to be a full Schemasheets replacement. Use
Schemasheets directly when full spreadsheet-driven LinkML authoring is needed.
