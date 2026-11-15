# Lore submission handoff

## Readiness

**Not ready to submit yet.** Full learned comparisons, the measured teaching
demo, trained load and the final local image check remain unfinished.
Fresh Factory-only `r4` measurements are running with MiniMax M3.1 Flash at
medium effort. Raw-provider `r2` remains paused on quota, with saved progress.
SDK and raw-provider answers are not combined; failed `r3` preflight answers
are excluded.

The owner approved free Hugging Face hosting, superseding the local-only
preference. The native/Gradio and pinned SDK prototypes pass. Hosting account
access and write scope are verified; eligible free Space creation and the real
deployment remain pending. No paid plan, other
provider or tunnel is approved. A loopback address is not a hosted judge link.
Public repository creation and push are approved after final checks.

| Deliverable | Current state |
|---|---|
| Local app | `http://127.0.0.1:8000`, development preview |
| Public repository | Not created or pushed yet |
| Hosted judge link | Free Hugging Face approved; access verified, deployment pending |
| Loom | Owner recording and link still needed |
| Social posts | Drafts only; not authorized to send |

## Historical measured summary, not the pending r4 headline

On the full BIRD Mini-Dev test set, MiniMax-M3.1-Flash at medium effort scored
227/500 (45.4%) without evidence and 258/500 (51.6%) with supplied evidence.
The 6.2-point gap is a baseline headroom measurement, **not a Lore gain**.

Sources: [`results/r2/baseline.json`](results/r2/baseline.json) and
[`results/r2/summary.json`](results/r2/summary.json).

The separate SDK protocol is recorded in
[`results/r4/learning_configuration.json`](results/r4/learning_configuration.json).
The latest full integration run passed 120 tests. Tests do not substitute for
the accuracy, independent teaching-replay, trained-load or hosted-app gates.

Do not use the exploratory small-run scores as the final headline. All three
audits, including failures and remaining noisy rules, are preserved in
`results/s1/`, `results/s2/` and `results/s3/`.

Before submission, replace this provisional summary with the final Lore,
vector and flat results, their paired intervals, prompt-token counts and
trained-load measurements. Report a losing or inconclusive comparison plainly.

## Recording outline

Use a fresh sandbox and a pair that passed the real API replay checks. Do not
describe a synthetic graph fixture or a cached baseline answer as a successful
teaching demonstration.

1. **Problem:** schema alone misses the analyst's meaning. Show a real wrong
   answer to the first question.
2. **Correction:** enter the recorded hint, inspect the proposed SQL, then
   explicitly confirm it. Show the new rule and its source.
3. **Reuse:** ask the different second question. Show its result and the learned
   rule in the actual grounding trace. Never teach the second question.
4. **Graph:** explain rules on columns, shared-column examples, direct joins,
   feedback weights and certification. Native path search is not implemented.
5. **Proof:** show the final full-test curve, vector and flat comparisons,
   uncertainty, token counts and trained grounding load.
6. **Buyer and limits:** the initial buyer hypothesis is a team shipping an
   internal data agent. Reviewable corrections and provenance are the product
   value. Demand and willingness to pay have not been validated.
7. **Links:** show the actual public repository and verified hosted app. If
   hosting is still blocked, say so; a localhost URL is not judge-accessible.

## Draft launch copy, not sent

> Lore learns database meanings from verified SQL corrections and stores them
> as inspectable graph facts on HydraDB and SelfGraph.
>
> We compare schema-only prompting, supplied evidence, graph grounding, vector
> memory and flat retrieval on the same held-out questions.
>
> Final measured results and links will be added after validation. This is one
> model, one seed and a simulated analyst-feedback stream, not a production
> performance claim.

The original social drafts are in
[`ABOUT_PROJECT.md`](ABOUT_PROJECT.md#13-draft-posts). Update every placeholder
from generated results and real links. The owner must approve any posting.

## Final checks

- [ ] Full floor, ceiling, Lore, vector and flat results cover all test questions.
- [ ] Report paired intervals, per-database scores, tokens and the flat ablation.
- [ ] Export finished seeds and select the measured demo databases.
- [ ] Complete the real teaching replays and browser walkthrough.
- [ ] Run trained grounding load and the final local deployment image check.
- [ ] Recheck clean-source reproduction, secrets, Git history and staged scope.
- [ ] Update the README and this handoff with final results and limitations.
- [ ] Create and push the public repository using the owner's approval.
- [ ] Owner records Loom and supplies its link.
- [ ] Verify eligible free Hugging Face access, deploy and test the real judge link.
- [ ] Owner approves and sends any launch posts, then submits the real links.
