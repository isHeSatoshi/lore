# Lore, explained simply

This page has two parts: understand the project first, then read the short script. You do not need to claim you wrote the code or run a live teaching demonstration.

## First, what is this project?

**Lore helps an AI reuse what a person has taught it about a database.**

A database is a collection of tables. An AI can turn a normal question into SQL, the instructions that tell the database what to calculate. But knowing the table and column names does not mean the AI understands the business.

For example, a company might define revenue as completed sales excluding refunds. The AI might not know that definition. Its SQL can run successfully and still calculate the wrong thing.

That revenue example explains the problem. It is **not** a measured revenue demo in this project.

### What Lore changes

Think of Lore as a shared, reviewable instruction sheet beside the AI:

1. Someone asks a question. Lore looks for relevant saved knowledge and includes it in the AI's instructions.
2. The AI writes a database query. The app shows the query and its result.
3. If the answer is wrong, a knowledgeable person explains the correction and checks the revised query.
4. Only after explicit confirmation does Lore try to extract reusable rules from that correction.
5. A later question can receive those rules before the AI writes its query.

It does **not** change or retrain the AI model. It changes the knowledge supplied to the model. A saved rule can still be wrong, irrelevant or too broad, so review matters. Not every correction improves every later answer.

### Why a graph? What is HydraDB?

A graph stores things and their connections. Here, a rule connects to the database columns it describes, with information about its source. That makes the knowledge inspectable rather than leaving it buried in a chat.

- **HydraDB** is the database that persists this connected knowledge.
- **SelfGraph** is the library used to manage the facts, connections, history and retrieval.
- **Lore** is the application that uses them to help answer database questions and learn from confirmed corrections.
- **MiniMax M3.1 Flash**, at medium effort through Factory, is the AI model used in the completed experiment.

You do not need to say all four names in the video.

### What the numbers actually mean

The completed experiment used 500 held-out BIRD Mini-Dev questions. “Held out” means their answers were not used as teaching examples. Lore's separate learning stream had 864 verified questions.

| Setup | Correct answers |
|---|---:|
| Same AI given the database structure and question | 231 out of 500 |
| Same AI helped by Lore | 271 out of 500 |
| Same AI given simpler retrieval of the same learned facts | 266 out of 500 |

That is **40 additional correct answers over the structure-only baseline**, or 46.2% → 54.2%. It is an eight-percentage-point gain, not “eight times better.”

The five-answer difference against simpler retrieval is inconclusive. Do not claim the experiment proves graphs are more accurate than other ways to store these facts. This is one model and one public benchmark, not a promise about every company's data.

## Read this aloud

Imagine asking an AI, “How much revenue did we make last month?”

It gives a convincing number, but includes refunded orders.

You explain that refunds should not count. If the correction stays in that chat, the next question can repeat the mistake.

Lore keeps the lesson, not just the conversation.

It sits between the AI and your database. After a person checks and confirms a correction, Lore stores a reusable rule, connected to the relevant data. For a later question, it finds useful rules and gives them to the AI before it writes the query.

The model is not being retrained. It is getting a better instruction sheet.

The revenue story is an illustration. The actual test used five hundred database questions held apart from teaching. The same AI answered two hundred thirty-one correctly with the database structure alone, and two hundred seventy-one with Lore. Forty additional correct answers.

The rules live in a graph on HydraDB, so people can inspect their connections and sources. But the test does not prove the graph beats simpler retrieval of the same facts.

That is Lore: helping the next question benefit from the last correction.

## What to show while you read

**Target: around 1:45–1:55.** Only read the section above aloud. Rehearse once with a timer. Leave the technical explainer and these directions out of the recording.

This version works as a narrated overview, without a risky live demonstration or pretending you developed the project.

| Approximate time | Screen | What you are explaining |
|---|---|---|
| 0:00–0:27 | [Lore's Ask view](https://ishesatoshi-lore.hf.space). Do not type the revenue example into an unrelated database. | A plausible answer can still use the wrong definition. The revenue story is hypothetical. |
| 0:27–0:58 | Ask view, then an existing trained rule in Graph. | Lore retrieves rules and learns only from a checked, confirmed correction. Do not click Confirm just for the video. |
| 0:58–1:08 | Keep the saved rule visible. | The AI stays the same; the supplied knowledge changes. |
| 1:08–1:35 | Proof view or the [README result table](https://github.com/isHeSatoshi/lore#the-result). | Point to 231 and 271. These are benchmark results, not the revenue example or a claim about the screen's current query. |
| 1:35–1:53 | Graph, then README links to app and source. | Inspectable knowledge, the unresolved graph comparison, and the closing idea. |

You can say “the project” and “the test.” You do not need to say “I built” or “we developed.” Showing existing trained rules is not a live correction-to-reuse demonstration, and this script does not present it as one.

## If you want to add a real teaching clip later

This is optional for understanding this script. The [submission handoff](SUBMISSION.md#recording-outline) describes the fuller demonstration.

Use one fresh sandbox. Ask follow-up B first and check that it is wrong. Ask A, correct only A, have someone who understands the SQL verify it, explicitly confirm it, then ask B again. Only call it successful transfer if B is now correct and uses a new rule. Never teach B or switch sandboxes.

Pause recording during model waits or remove only waiting afterward, and disclose that. Keep failures and state changes honest. The [archived public trial](results/r4/hosting_browser.json) has a successful toxicology example and a failed school example; a past success is not a guaranteed rerun. If you cannot verify the SQL, do not confirm it just to produce a video.
