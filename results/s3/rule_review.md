# M4 validation review

The required small-run checks are complete: 60 stream questions, all 95 held-out questions for both floor and Lore, 87 MEANS relations (52 California, 35 financial), and both leak tests passing. Every relation was inspected, including its term, aliases, target, SQL, note, and stream correction.

Floor scored 34/95 (35.79%); Lore scored 49/95 (51.58%). The paired difference is 15.79 percentage points with a 95% interval [3.16, 28.42]. This exploratory result is not the full benchmark, and was not chosen as the best of the small runs.

## Audit repairs

The earlier malformed fragments, unrelated target links and memorized numeric/year thresholds improved after the reflection repairs. The review found two additional mechanically checkable failures:

- `s49` hid a question-specific top-county plan inside a subquery with LIMIT.
- `s148` invented an active-loan rule from a column absent from the verified correction.

Final validation now rejects LIMIT/OFFSET anywhere in a fragment and references outside the verified correction's parsed columns. Unit and real-HydraDB checks pass. `post_review_validation.json` verifies rejection of those four historical relations, leaving 83 candidates under the final filters. The stored `s3` graph, answers and 49/95 score have **not** been changed or rescored after that repair.

## Known limits, not a truth certification

Some inferred aliases and generic meanings remain too broad. Examples include a monthly-statement alias on an after-transaction rule, generic mailing-state wording bound to CA, and a mailing-address alias on physical-address fields. Gold-derived enrollment sums, ownership terminology and units can also be misleading.

These are documented model/label limitations, not silently corrected benchmark labels or claims that all rules are sound. The reflection prompt was tightened through the stream-only audits; confidence and certification remain separate from semantic proof. The full run must measure the resulting system honestly, including any errors these heuristics cause.

M4's stated completion checks pass. Freeze the learning configuration for the full `r2` run, retain all three exploratory runs, and do not claim a full-test gain before that evaluation completes.
