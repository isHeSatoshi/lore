# Lore submission handoff

## Readiness

**Not ready to submit yet.** Full comparisons, final-source validation and
the seeded native cold start pass. All twelve teaching pairs and all 3,000
trained-load requests now pass. The live-reader cold/integration refresh also
passes; public hosted checks remain open. Factory-only `r4` is complete with MiniMax
M3.1 Flash at medium effort. Raw-provider `r2` remains paused on quota.
SDK and raw-provider answers are not combined; failed `r3` preflight answers
are excluded.

The owner approved free Hugging Face hosting, superseding the local-only
preference. The native/Gradio and pinned SDK prototypes pass. Hosting account
access and write scope are verified; the public free ZeroGPU Space is created
and rebuilding after a dependency-order repair. Public app checks remain pending. No paid plan, other
provider or tunnel is approved. A loopback address is not a hosted judge link.
Public repository creation and push are approved after final checks.

| Deliverable | Current state |
|---|---|
| Local app | `http://127.0.0.1:8000`, development preview |
| Public repository | Not created or pushed yet |
| Hosted judge link | [HF Space](https://huggingface.co/spaces/isHeSatoshi/lore), building; not yet verified |
| Loom | Owner recording and link still needed |
| Social posts | Drafts only; not authorized to send |

## Final measured summary

On all 500 BIRD Mini-Dev questions, MiniMax M3.1 Flash at medium effort scores:

| System | Strict EX | Mean prompt tokens |
|---|---:|---:|
| Floor | 46.2% | 4,478 |
| Supplied-evidence ceiling | 52.2% | 4,509 |
| Lore | 54.2% | 5,101 |
| Vector | 48.6% | 4,688 |
| Flat, same learned facts | 53.2% | 5,382 |

Paired Lore gains: **+8.0 pp [3.0,13.0]** versus floor,
**+5.6 pp [1.0,10.2]** versus vector, and
**+1.0 pp [−3.8,5.6]** versus flat. The flat comparison is **inconclusive**.
Do not claim a proven graph-specific accuracy advantage over flat facts.
All learned checkpoints cover 500 questions. Recorded benchmark usage is
29,099,485 input tokens, 4,287,245 output tokens and 6,299 calls.
SDK-internal/cancelled usage may be unreported; demo discovery is separate.

Source: [`results/r4/summary.json`](results/r4/summary.json).

The separate SDK protocol is recorded in
[`results/r4/learning_configuration.json`](results/r4/learning_configuration.json).
The latest full integration run passed **155 tests**, with Ruff and the typed
frontend build passing. The real native cold start restores all 345 stored
rules across the four measured databases: 38.80 seconds fresh, 6.03 seconds
on restart, zero model calls. [Proof](results/r4/hosting_cold.json).
These are local observations, not hosted guarantees. Tests do not substitute for
the accuracy, independent teaching-replay, trained-load or hosted-app gates.

Do not use the exploratory small-run scores as the final headline. All three
audits, including failures and remaining noisy rules, are preserved in
`results/s1/`, `results/s2/` and `results/s3/`.

Public UI/teaching verification and the repository URL are still needed before submission.
All first-round teaching outcomes are retained: four passes across 48 attempts
did not meet the three-per-database release gate. Bounded further discovery
uses the existing rule explanation and more diverse follow-ups.

Final discovery establishes three strict pairs in each selected database
(38/53/16/54 trials, 3 passes each), with all failures retained. No single-question
fallback was used. The trained load report has zero errors at 10/50/100 offered
clients, 1,000 requests each. Queue-inclusive p99 is 4.74/26.08/42.75 seconds.
The earlier failed pool stress remains in `results/r4/load.failed1.json`.
The anchored uncached live reader matches original full blocks and traces on
all 500 held-out inputs. None of the frozen accuracy sources changed.

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
> On 500 held-out questions, Lore scores 54.2%, versus 46.2% for schema-only
> prompting and 48.6% for vector examples. Its 1-point lead over same-facts flat
> retrieval is inconclusive. This is one model, one seed and simulated feedback,
> not a production performance claim. Public links follow after live validation.

The original social drafts are in
[`ABOUT_PROJECT.md`](ABOUT_PROJECT.md#13-draft-posts). Update every placeholder
from generated results and real links. The owner must approve any posting.

## Final checks

- [x] Full floor, ceiling, Lore, vector and flat results cover all test questions.
- [x] Report paired intervals, per-database scores, tokens and the flat ablation.
- [x] Export finished seeds and select the measured demo databases.
- [ ] Complete the real teaching replays and browser walkthrough.
- [x] Run the real seeded native launcher cold-start and restoration check.
- [x] Run trained grounding load.
- [ ] Recheck clean-source reproduction, secrets, Git history and staged scope.
- [ ] Update the README and this handoff with final results and limitations.
- [ ] Create and push the public repository using the owner's approval.
- [ ] Owner records Loom and supplies its link.
- [ ] Verify eligible free Hugging Face access, deploy and test the real judge link.
- [ ] Owner approves and sends any launch posts, then submits the real links.
