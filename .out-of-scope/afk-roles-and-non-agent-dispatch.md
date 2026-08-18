# AFK agent roles and non-agent dispatch

Milestone 58 (executor→sandcastle convergence) does not build per-role AFK agents, per-role permission sets, or a dispatch path for non-agent work items. The dispatch mechanism it ships stays single-shape: one queue, one spawn call, one substrate value per row.

## Why this is out of scope

The proposal is sound and will almost certainly land later. A dispatch mechanism that is uniform at the call site and varies only in *where the request is delivered* — coder into a container, researcher into a worktree, analyst or reviewer into whatever their tool surface needs, a non-agent item into a queue a human or a script drains — is the right end state, and milestone 58's shape was chosen so it does not foreclose that.

It is out of scope now for one reason: **no second role exists**. There is exactly one AFK work type in the tree today (implement a GitHub issue in a container), so a role abstraction would have exactly one implementation. Per SOUL §Judgment calibration, an abstraction needs two real implementations — otherwise it is indirection, not abstraction, and the shape gets fixed by the single case that happened to be first. The same argument applies harder to non-agent dispatch: there is no destination to dispatch to, so the design would be inventing both the producer and the consumer.

Two things milestone 58 does ship that are the load-bearing preparation for roles, so the later slice is an extension rather than a rewrite:

- **`substrate ∈ {container, worktree}` as an explicit queue-row value** (decision `c5e2e14a-4750-4e9d-bb26-9d44b9ef5b02`), defaulted from operator config. The non-container lane stops being an implicit default and becomes nameable. On the pinned library this is a parameter of the same call — `NoSandboxProvider` sits in the `SandboxProvider` union at every entry point — not a second mechanism, so the one-substrate-mechanism end state is preserved while the value varies.
- **The permission perimeter baked into the image** rather than applied at spawn time (decision `04632934-5987-4f5e-b4de-b84837e8340f`). Per-role tool allowlists are not expressible on `@ai-hero/sandcastle@0.12.0` at all — the library has no per-role allowlist surface — but per-role *container config* is (`docker({imageName, mounts, env, network, groups, devices, …})`). So the natural implementation of "each role gets only what it needs" is one image per role, which is what moving the perimeter into the image sets up.

The trigger to build this is the arrival of a second role with a real work item behind it — not a hypothetical one. When that happens, the work is: a `role` column beside `substrate`, a role→image+substrate resolution table in operator config, and nothing on the spawn path itself.

Decision `8de24926-af03-4baf-a51c-0d6966b39117` (2026-08-18) records the deferral and this carrier. Prior deferral of the same shape: `e270b435-69ed-4136-b7f3-ac9dfca93ef8`.

## Prior requests

- #959 — umbrella "executor→sandcastle convergence"; roles and non-agent dispatch were raised during its 2026-08-18 `/grill` and deferred there.
