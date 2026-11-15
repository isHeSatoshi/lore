# Small-run rule audit: quality gate failed

All 107 MEANS relations in `rules.json` were read, grouped by origin and identical term/SQL/note so multi-column rules were not mistaken for independent meanings. This includes all 65 California relations and 42 financial relations.

The exploratory result is 34/95 floor versus 45/95 Lore, a difference of 11.58 percentage points with paired-bootstrap 95% interval [-1.05, 24.21]. This interval includes zero. This is not the full 500-question benchmark, nor a validated final learning configuration.

## Findings from stream corrections only

- Question-specific values: `s68` memorized a closure decade, `s11` a 500-student threshold, `s145` a 1998 average, and `s182` birth years and a 4000 payment threshold.
- Invalid or non-reusable fragments: `s11` mixed an unbound `frpm` qualifier with `T1`/`T2` aliases; `s53` stored `<city>`; several rules stored unbound parameters, whole SELECTs, or FROM/JOIN snippets.
- Incorrect target links: `s46` attached an enrollment expression to `schools.School`; `s23` attached a school-name expression to an unrelated FRPM join key; `s150` attached a count expression to extra join/filter columns not referenced by it.
- Unjustified universal policies: `s49` generalized one exact DISTINCT projection and tie policy; `s186` made matching client/account districts an ownership requirement; `s2`, `s24`, and `s69` asserted global exclusions between alternative columns that the single correction did not establish.
- Useful reusable mappings also appeared, including charter and ownership codes, statement frequency codes, the excellence-rate formula, test-taker counts, and the credit-card-withdrawal operation code.
- Gold-derived quirks, including the overlapping enrollment sum in `s11`, remain dataset labels. They were not corrected or treated as independently established business truth.

## Action

M4 is **not passed**. Preserve this run unchanged as exploratory evidence. Tighten reflection to distinguish database meanings from request values and incidental query choices. Validate fragment syntax, table qualifiers, placeholders, and actual referenced target columns. Run the same stream-cap/database/checkpoint protocol in fresh `s2` namespaces, inspect every resulting rule, and rerun both leak checks.

No test question, evidence text, or held-out model error was used to design these reflection changes. The baseline prompts, split, gold SQL, strict evaluator, and denominator remain unchanged.

## Direct regression checks

`repair_checks.json` applies the new syntax/target validator to the original stored relations without changing them. It rejects 44 of the 107 historical relations and retains 63. All seven explicit regression cases pass, including the mixed-alias query, placeholder and wrong-target failures, plus positive controls for a valid school-name target, monthly frequency and excellence-rate formula. This is not a rescore or a semantic-quality verdict; fresh `s2` review is still required.
