# Lore: a two-minute Loom

**Target:** about 1:50, including short transitions. The narration below is sized for a calm read at 125–135 words per minute. Rehearse once with a timer; do not speed through the numbers.

## Before recording

- Open the [hosted app](https://ishesatoshi-lore.hf.space), its Proof view and the [public README](https://github.com/isHeSatoshi/lore) in separate tabs. Hide keys, cookies, terminals and account details.
- Use one real, fresh sandbox session. Ask follow-up B first and check that it is wrong. Then ask A, correct only A, explicitly confirm its SQL, and ask B again. Show B becoming correct using a new rule. Never teach B or switch sandboxes between these steps.
- Pause Loom during model waits, or trim only the waiting afterward. Keep the same sandbox and event order. The narration explicitly says waiting was removed; do not call the sequence uncut or guaranteed.
- Suggested starting point: the toxicology pair that passed the [public-browser check](results/r4/hosting_browser.json), `s298 → t481`. Its question, hint and follow-up are the third toxicology suggestion in [`results/r4/demo.json`](results/r4/demo.json). It is a previously measured example, not a guaranteed rerun.
- Inspect and independently check the proposed SQL before confirming it. If this attempt does not transfer correctly, do not narrate a success over it. Use a genuine successful recording or show the archived evidence and clearly call it a recorded example.

## Read this aloud

SQL can run successfully and still answer the wrong question. A schema gives an agent column names, not your team's meaning.

This is Lore, a semantic layer on HydraDB and SelfGraph that learns from corrections without retraining the model.

Here's a real sandbox session, with waiting removed. The first answer is wrong. I add a correction, inspect the proposed SQL, and confirm it. Lore stores a reusable meaning as a graph rule, with its source.

Now I ask a different question that I have not corrected. Lore retrieves the new rule and gets this answer right. That's the loop: correct once, reuse the lesson.

We tested five hundred held-out BIRD questions using MiniMax M3.1 Flash at medium effort. Schema-only prompting scored forty-six point two percent. Lore reached fifty-four point two. Vector examples scored forty-eight point six.

Flat retrieval of the same facts reached fifty-three point two. That comparison is inconclusive: we have not proved a graph-specific accuracy win.

The graph's practical value is inspectable rules, provenance, revisions, and controlled updates. The first users I have in mind are teams building internal data agents.

The hosted demo, source code, and full results are linked in the README. That's Lore: corrections the next query can use.

## Screen cues, not spoken

| Time | Show |
|---|---|
| 0:00–0:10 | Ask view, question and SQL visible. Open on the problem, not a title slide. |
| 0:10–0:20 | Lore's app and the selected database. |
| 0:20–0:43 | The genuine wrong answer, hint, proposed SQL, explicit **Confirm this SQL**, then the new rule and its source. Remove model waits, not failures or state changes. |
| 0:43–0:57 | The different follow-up, correct result and actual knowledge block containing the new rule. If possible, briefly show its wrong pre-teaching answer too. |
| 0:57–1:15 | Proof view or README result table. Point to 46.2%, 54.2% and 48.6%. Say “percentage points” if you describe the eight-point gain. |
| 1:15–1:28 | Keep the 53.2% flat row and the inconclusive paired interval visible. |
| 1:28–1:42 | Graph rule details: source, revision and certification controls. Describe features, not a proven graph-specific accuracy lift. |
| 1:42–1:52 | README links to demo, source and full results. Stop before 2:00. |

If you need to shorten the take, drop the sentence about the initial users. Keep the flat-control caveat and the actual correction-to-reuse sequence.
