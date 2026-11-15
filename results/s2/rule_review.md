# Second small-run audit

All 75 MEANS relations were inspected: 27 financial relations after that database finished, then all 48 California relations. The financial snapshot was compared field by field with the final export and was unchanged.

The run finished with floor 34/95 (35.79%) and Lore 50/95 (52.63%). The paired difference is 16.84 percentage points, with a 95% interval [4.21, 29.47]. This is exploratory two-database validation, not the final full benchmark.

## Improvements and remaining findings

The broken SELECT/alias and placeholder fragments, unrelated target links, memorized birth-year/payment thresholds, and fixed top-k clauses seen in `s1` no longer appeared in this export. Reusable column mappings, code translations and formulas remain.

Remaining quality problems prevent treating this as the final learning configuration:

- `s97` associates an after-transaction frequency code with an incorrect monthly description/aliases and an overly broad term.
- `s150` maps a generic partner-bank phrase to the question's AB value; `s2` similarly maps generic district name to one requested district.
- Several count rules still generalize query-specific cardinality or population choices.
- Some aliases broaden a term's scope, such as dropping the annual or named-school qualification.
- Gold-derived ambiguities remain, including overlapping enrollment populations, account-owner terminology, and alternative ownership-code fields. The labels were not changed.

## Repairs and final validation

Inspection also found an implementation bug: Term aliases were merged before a contradictory MEANS candidate was rejected. Aliases now merge only after compatible rule acceptance, with a real-HydraDB regression test proving a rejected candidate cannot add its misleading alias.

Reflection now receives existing schema value descriptions as well as column descriptions and profiles. Its instructions explicitly distinguish a named category from a generic field, requested entity values from business definitions, and incidental count choices from reusable meanings.

Ruff and all 59 tests passed after these repairs. Fresh `s3` validation is running before M4 completion and the full learned benchmark. These changes use stream corrections only, not held-out errors or evidence. This run is preserved unchanged.
