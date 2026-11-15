# Failed Factory preflight, excluded from results

`r3` stopped during its first floor batch. Six answers completed before the
adapter encountered a heterogeneous SDK `ToolCall` message. None of these
answers, learned state, or v1 completions are used by the clean `r4` experiment.

The preflight also exposed a policy mismatch: an empty `restrict_tools` list
means no restriction in the installed CLI. The declaration `tools: []` in the
captured preflight configuration therefore did not describe the effective
policy. This run is invalid, not a completed zero-tool experiment.

The repaired v2 transport uses `restrict_tools={Read}` together with
`disabled_tools={Read}`, then checks the effective catalog before every model
turn. Every tool must report `allowed=False`. It also handles standalone
`ToolCall` messages and meters unsuccessful returned turns.

Validation before `r4`: seven real prompts passed with zero allowed tools,
including the original failing question and the largest schema prompt.
The largest prompt took 14.18 seconds; the fresh concurrent batch took
16.11 seconds. Child peak RSS was 263616 KiB. These are transport checks,
not benchmark accuracy results.

The six journaled preflight responses recorded 92623 input and 3407 output
tokens. Interrupted or rejected in-flight work may have unreported usage.
