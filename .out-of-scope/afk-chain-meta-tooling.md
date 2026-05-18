# AFK-chain meta-tooling

This project does not invest in hardening the local AFK-chain wrapper that lived in `.scratch/` on a single device.

## Why this is out of scope

The wrapper was a personal-experiment harness for running long autonomous-loop chains on Main PC. It is not part of the canonical autonomous-loop architecture (`docs/design/autonomous-loop.md`), it never shipped to the install manifest, and the 2026-05-16 chain run that motivated #648 surfaced the broader pattern: long unsupervised chains degrade into meta-recursive tracker-filing rather than producing merged code.

Investing engineering time in making the local wrapper portable across devices, or in fixing its quota-detection path, would be polishing a tool whose output we are simultaneously trying to bound. The canonical answer is the scheduled `autonomous-loop` skill (cron + safety bounds + write-action gates), not a hand-rolled wrapper.

If chain quality improves and per-device portability genuinely matters later, the right move is to fold the useful bits into the canonical skill — not to revive the `.scratch/` wrapper.

## Prior requests

- #648 — "AFK chain wrapper lives in untracked `.scratch/`; quota-detection fix is local-only"
