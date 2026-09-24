# Eval v2 benchmark framework

This project does not run an offline eval/benchmark harness for agent behaviour — no replay harness, no judge-scored sycophancy suite, no calibration-PR benchmark runs.

## Why this is out of scope

The eval v2 direction (milestone "Benchmark framework (Pillar 3)") was frozen with an explicit kill criterion: if the tracer bullet (#1278) and judge validation (#1279) showed no progress by the 2026-09-23 review date, the direction closes unless a new decision extends it. The date passed with no commits and no extension, so the criterion fired on its own terms.

The substrate is gone too. `evals/` — `run_evals.py`, `replay_harness.py`, the keyword scorer, the sycophancy scenario YAMLs — was deleted in 973721e (#1868) with the reactive-core stack, and the memory-recall benchmarks targeted a memory service that no longer exists (#1867). Reviving this means rebuilding from zero, not resuming.

What survives of the underlying concern — "is the agent getting better or worse?" — is covered by cheaper signals that already run: the two-layer code-gate on every PR, tests as ground truth, and the dated confidence field in the decision journal. If a benchmark comes back, it should start from a concrete regression that those signals missed, not from the frozen v2 design.

## Prior requests

- #505 — Recall calibration: q09 stochastic regression + slice 4 keyword_query drift
- #760 — eval(sycophancy): replay_harness.score keyword matcher under-counts genuine pushback
- #1261 — design: eval v2 — non-blocking run on calibration PRs, pass^k as regression unit
- #1278 — eval v2: harness with paraphrase regeneration, privileged judge and pair verdict
- #1279 — eval v2: judge validation on ≥30 labelled transcripts
- #1280 — eval v2: remove dead eval systems
- #1281 — eval v2: combat set — 12 matched pairs + ≥4 clean scenarios
- #1282 — eval v2: content-addressed baseline with quota-exclusive runs
- #1283 — eval v2: noise calibration — three k=5 runs, flip-rate
- #1284 — eval v2: non-blocking report on calibration PRs + paths-filter meta-test
