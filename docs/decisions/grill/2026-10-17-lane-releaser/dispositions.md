# Dispositions — /grill lane releaser on non-admin hosts (#2097), 2026-10-17

Source: `sampling.md` in this directory. Only the sampling tier ran, so the items were grouped by hand into four clusters (D1–D4), and the user answered each cluster on 2026-10-17.

| ID | Item (short) | Disposition | Rationale |
|---|---|---|---|
| S1 [HIGH] | On a personal-account repo the only roles are the owner and write collaborators. Option (a), giving the labellers admin, is therefore impossible, and only the owner can release a HIGH hold. | **accept** (D1) | The doc step names enforceability first: who releases HIGH on this host. The redrobot adoption decision records (a) as impossible. |
| S2 [MEDIUM] | Letting a write-level labeller release the hold reverses the 2026-10-16 rule, which made the admin role the key. | **accept: reverse now** (D2) | Starting today, on hosts whose labellers are not admin, the labeller's approval of the head SHA may release the hold on their own lane PR. jarvis is unaffected because its labeller is admin. The code comes with #2107. |
| S3 [MEDIUM] | The doc step has no mechanical signal, and the releaser setting goes untracked once #2097 closes. | **defer** (D3) | To #2107. |
| S4 (alt) | At publish, emit a warning and also request review from `operator` when the labeller is not admin. | **defer** (D3) | To #2107. |
| S5 (alt) | Use a boolean `release-on-write` input instead of a set of logins. | **defer** (D4) | To #2107, as its open shape question. |
| S6 (alt) | `risk-tier` says "advisory: base branch not protected" when the base branch is unprotected. | **defer** (D3) | To #2107. |
| S7 (assumption) | Enforceability is the precondition. A host that cannot make `risk-tier` required (a private repo on the Free plan) gets no hold from it, and lane auto-merge fails there. | **accept** (D1) | The host-setup step leads with it. Today redrobot cannot complete step 3.3. |
