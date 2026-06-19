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
