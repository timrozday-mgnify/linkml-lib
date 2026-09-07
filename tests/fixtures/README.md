# Test fixtures

Inputs for the conversion tests: an ENA sample checklist (`ERC000015.xml`), an
ENA/SRA schema (`SRA.study.xsd`), and a DataHarmonizer export of the former
(`ERC000015_example.json`). Both ENA files are published by EMBL-EBI.

They live here so the suite runs anywhere. It previously read them from a
sibling `ena-submission-dataharmonizer` checkout, which meant the conversion
tests silently skipped everywhere that repo was absent — CI included.
