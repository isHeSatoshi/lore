# Lore

### Correct the answer. Keep the lesson.

_Built for the [HydraDB Hackathon](https://luma.com/bqwllms4), Track 1: the self-improving graph._

[Try Lore](https://ishesatoshi-lore.hf.space) · [Results](results/r4/summary.json) · [Run locally](docs/REPRODUCE.md#run-locally-with-the-measured-factory-transport) · [Validation](results/r4/hosting_public.json)

![Execution accuracy as Lore learns from more verified examples](results/r4/curve.png)

## The problem

An AI can write SQL that runs perfectly and still answers the wrong question. A schema tells it which columns exist, not which orders count as revenue or what an analyst means by “active.”

You can explain the mistake. But if the correction stays in one conversation, the next question can repeat it.

Lore keeps the useful lesson. It stores confirmed corrections as reusable knowledge and retrieves relevant rules before the AI writes its next query. **The model stays the same; its instruction sheet improves.**

## How it works

1. **Ask.** Lore combines your question with the schema and relevant saved rules.
2. **Correct.** A person checks the revised SQL and explicitly confirms it.
3. **Reuse.** Lore saves reusable meanings, links them to columns, and can retrieve them for a different question.

HydraDB stores the graph; SelfGraph manages its facts, connections and history. You can inspect a rule and its source rather than trust an unexplained memory.

## The result

Same **MiniMax M3.1 Flash**, medium effort through Factory. All 500 held-out BIRD Mini-Dev questions; a separate 864-question learning stream.

| What the model receives | Correct | Mean prompt tokens |
|---|---:|---:|
| Schema and question | 46.2% | 4,478 |
| Supplied per-question evidence | 52.2% | 4,509 |
| **Lore's learned graph** | **54.2%** | 5,101 |
| Nearest verified examples | 48.6% | 4,688 |

Lore's accuracy rose **49.4% → 51.2% → 54.2%** as it learned, evaluated on the same held-out questions at every checkpoint.

Lore answered **40 more questions correctly than schema alone**.

This is one model and one public benchmark, not a production guarantee. Corrections still need human review.

[Learning curve](results/r4/curve.png) · [Every database](results/r4/per_db.md) · [Full protocol, uncertainty and reproduction](docs/REPRODUCE.md)

## Try it

Open the [hosted app](https://ishesatoshi-lore.hf.space), explore the trained rules, or use a separate sandbox. Free hosting can sleep and lose visitor state.

[Local setup](docs/REPRODUCE.md#run-locally-with-the-measured-factory-transport) · [Hosting guide](deploy/hf/README.md) · [Tests and validation](docs/REPRODUCE.md#interactive-validation-and-deployment-limits)

Code: [MIT](LICENSE). BIRD data and derived benchmark/seed data: [CC BY-SA 4.0](DATA_LICENSE.md). Third-party runtime notices are in the [hosting guide](deploy/hf/README.md).
