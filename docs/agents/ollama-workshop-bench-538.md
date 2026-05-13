# Workshop PC Ollama benchmark — sandcastle slice #538

**Date:** 2026-05-13
**Device:** VividFormsPC4Workshop (Workshop PC)
**Hardware:** NVIDIA GeForce RTX 5080, **16 GB VRAM**, 64 GB system RAM, 24 logical CPUs
**Driver:** 32.0.15.9186
**Ollama:** local server on `:11434`
**Reference issue (parent epic):** [#534](https://github.com/Osasuwu/jarvis/issues/534)
**Slice:** [#538](https://github.com/Osasuwu/jarvis/issues/538)

Purpose: pick the production-default Ollama coding model for the sandcastle AFK loop, plus a downgrade-tier fallback for the Tier-1 OOM retry in [#543](https://github.com/Osasuwu/jarvis/issues/543).

## Method

`scripts/bench-ollama.ps1` per model: unload → cold call → warm call. Throughput = `eval_count / eval_duration`. Prompt = a small but non-trivial coding ask (parameterise a PowerShell script). Output capped at 400 tokens (synthetic) / 600 tokens (real-task) to keep wall time bounded.

Two prompt variants:

1. **Synthetic-coding** — short, deterministic, full-load saturation (`num_predict=400`).
2. **Real-task** — actual transformation requested elsewhere in the repo (parameterising `bench-ollama.ps1` params block). Output inspected manually for correctness.

Raw logs: `.sandcastle/runtime/bench-538/` (gitignored).

## Results — synthetic coding prompt

| Model | Quant | Disk size | Cold wall | Warm wall | **Warm tok/s** | Eval tokens |
|---|---|---|---|---|---|---|
| `qwen2.5-coder:7b`  | Q4_K_M | 4.7 GB | 5.1 s  | 2.6 s  | **227.3** | 400 |
| `qwen2.5-coder:14b` | Q4_K_M | 9.0 GB | 15.6 s | 5.0 s  | **94.6**  | 400 |
| `qwen2.5-coder:32b` | Q4_K_M | 19 GB  | 88.5 s | 77.3 s | **5.2**   | 400 |
| `qwen3-coder:30b`   | Q4 MoE A3B | 18 GB  | 32.1 s | 9.5 s  | **42.9**  | 400 |

GPU mem during runs: **14.2 GB / 16.3 GB used** on 14b (tight headroom), **7.5 GB used** on 7b (large headroom), **14.9 GB used** on qwen3-coder:30b MoE (just fits — MoE active-params keep weight residency under the budget).

**qwen3-coder:30b surprise:** the MoE A3B architecture (3B active params per token) lets the model fit in 16 GB VRAM despite 30B total params. Result: 42.9 tok/s — **above** the 30 tok/s threshold. Not the production primary because (a) 14b runs 2.2× faster, leaving more headroom for retry loops, and (b) qwen2.5-coder family consistency between Tier 0 (14b) and Tier 1 (7b) keeps prompt format predictable.

`qwen2.5-coder:32b` Q4_K_M at 19 GB exceeds the 16 GB VRAM budget — Ollama spills layers to CPU. Result is **~18× slower** than 14b. Effectively unusable for an AFK loop.

## Results — real-task prompt (14b only)

Task: rewrite a hardcoded `$models = @(...)` line in `bench-ollama.ps1` into a `param()` block with defaults wired into existing variables. No explanation, code only.

- Wall: **4.45 s**, eval **108 tokens**, **87.2 tok/s**.
- Output: correct `param()` block, sensible defaults, basic wiring; missed clean `$opts.num_predict` integration into the existing hashtable literal (left as a stray mutation). Workable as a first draft, not zero-edit ready. Sandcastle's value depends on the agent iterating, not on single-shot perfection — this quality bar is acceptable for the AFK loop.

## Threshold for AFK viability

A typical sandcastle iteration outputs an order of **2 000–5 000 tokens** of agent reasoning + code. To drain a queue of ~10 issues inside a 4-hour safe-hours window (jarvis 22:00–02:00) with budget for retries:

- Per iteration: ≤ 15 min wall, of which gen time ≤ 5 min.
- 5 min for ≤ 5 000 tokens → **≥ ~17 tok/s sustained** required.
- Cushion for prompt eval, tool calls, container overhead, occasional 30B fallback → **target ≥ 30 tok/s sustained**.

Observed `qwen2.5-coder:14b` at **94 tok/s** is comfortably above the threshold (3× headroom). Observed `qwen2.5-coder:32b` at **5 tok/s** is **below threshold by 3–6×** — unusable as primary.

## Decision

| Tier | Model | Reason |
|---|---|---|
| **Production primary (Tier 0)** | `qwen2.5-coder:14b` | Fits 16 GB VRAM, 94 tok/s warm, real-task quality acceptable. |
| **Downgrade tier (Tier 1, on OOM)** | `qwen2.5-coder:7b` | 227 tok/s warm, 4.7 GB on disk, 7.5 GB VRAM use. Same `qwen2.5-coder` family as Tier 0 → prompt-format compatible. |
| **Viable alternative (revisit if 14b output quality insufficient)** | `qwen3-coder:30b` (MoE A3B) | 42.9 tok/s, 14.9 GB VRAM, above threshold. Different family from 7b Tier 1 — pairing it with a Tier 1 of the same qwen3-coder line would be cleaner if promoted. |
| **Disqualified on this hardware** | `qwen2.5-coder:32b` | 19 GB Q4 dense exceeds 16 GB VRAM, spills to CPU, 5 tok/s. |

## Tier 2 escalation (DeepSeek API) — unchanged

Slice [#543](https://github.com/Osasuwu/jarvis/issues/543) already wires the Tier-2 DeepSeek-class API as the post-Ollama escape hatch. Hardware ceiling here does **not** force escalation to Tier 2 for routine issues — 14b is sufficient for the AFK loop. Tier 2 remains for cases the agent itself flags as too-large.

## Cost of being wrong

If 14b output quality proves too low across a sandcastle week, the chain is: relabel issues `use-claude-api` (per #543) to bypass Ollama entirely, then revisit primary choice. Cost is bounded by orchestrator review cadence — a bad model picks up no merges, the queue stalls visibly, the choice gets revisited within one HITL review cycle. Reversibility: trivial (param change in `Run-Sandcastle.ps1`).
