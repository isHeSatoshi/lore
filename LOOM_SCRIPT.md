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

### Technical terms in the script

- **Semantic layer:** the saved meanings and rules that help interpret the database.
- **Prompt:** the instructions and context sent to the model.
- **Knowledge block:** a small piece of that prompt containing relevant retrieved facts, rather than the whole chat history.
- **Read-only SQL:** a database query that reads data without changing it.
- **Execution accuracy:** how often the query's full result matches the reference result under the benchmark's comparison rules.
- **Revision history:** a record of changes to saved knowledge.

## Read this aloud

Imagine asking an AI for last month's revenue. The SQL runs, but includes refunded orders.

You correct it. Why should the next question need the same explanation?

That's the problem Lore addresses: remembering database meaning, not just conversation history.

Lore is a semantic layer between the language model and the database. It retrieves rules linked to relevant columns, builds a small knowledge block, and adds it to the prompt before the model generates read-only SQL.

When someone checks and confirms a correction, Lore extracts reusable meanings. HydraDB stores them as a graph; SelfGraph manages the connections, sources, and revision history. A later question can retrieve the lesson without being taught separately.

The model is not retrained. Its context changes.

That revenue example is hypothetical. The actual evaluation used five hundred held-out BIRD questions with MiniMax M3.1 Flash at medium effort. Execution accuracy rose from forty-six point two percent with schema alone to fifty-four point two with Lore.

Simpler retrieval of the same facts scored fifty-three point two, so the test does not prove the graph itself is more accurate.

The goal is a database assistant whose corrections become inspectable knowledge the next query can use.

## What to show while you read

**Target: around 1:50–1:55.** Only read the narration above aloud. Rehearse once with a timer. If needed, omit “The model is not retrained. Its context changes.” rather than rushing the results.

This is a narrated overview. It does not require you to demonstrate a live correction or claim you developed the project.

| Approximate time | Screen | What you are explaining |
|---|---|---|
| 0:00–0:22 | [Lore's Ask view](https://ishesatoshi-lore.hf.space). Do not run the revenue example against an unrelated database. | The revenue story illustrates the problem; it is not an actual measured demo. |
| 0:22–0:43 | The actual retrieved knowledge block and generated SQL from an existing answer. | Rules become model context before SQL generation. Do not label an empty block as successful retrieval. |
| 0:43–1:09 | An existing trained rule in Graph, with its source and revision details. | Confirmed corrections become reusable, inspectable facts. Do not click Confirm merely for the recording. |
| 1:09–1:35 | Proof view or the [README result table](https://github.com/isHeSatoshi/lore#the-result). | Point to 46.2% and 54.2%. These are held-out benchmark results, not the revenue example. |
| 1:35–1:55 | Keep 53.2% visible, then return to the graph or README links. | The comparison with simpler retrieval is inconclusive; finish with the product goal. |

You can say “the project” and “the test.” You do not need to say “I built” or “we developed.” Showing existing trained rules is not a live correction-to-reuse demonstration, and this script does not present it as one.

## If you want to add a real teaching clip later

This is optional for understanding this script. The [submission handoff](SUBMISSION.md#recording-outline) describes the fuller demonstration.

Use one fresh sandbox. Ask follow-up B first and check that it is wrong. Ask A, correct only A, have someone who understands the SQL verify it, explicitly confirm it, then ask B again. Only call it successful transfer if B is now correct and uses a new rule. Never teach B or switch sandboxes.

Pause recording during model waits or remove only waiting afterward, and disclose that. Keep failures and state changes honest. The [archived public trial](results/r4/hosting_browser.json) has a successful toxicology example and a failed school example; a past success is not a guaranteed rerun. If you cannot verify the SQL, do not confirm it just to produce a video.
