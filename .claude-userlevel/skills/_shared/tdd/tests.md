<!--
Adapted from Pocock's tdd skill (engineering/tdd/tests.md, upstream
mattpocock/skills @ 733d312884b3878a9a9cff693c5886943753a741).
Upstream:
https://github.com/mattpocock/skills/blob/733d312884b3878a9a9cff693c5886943753a741/skills/engineering/tdd/tests.md
Jarvis adaptations: Good/Bad Tests sections kept verbatim from upstream;
added "Choosing Cases" section and the "is this test valuable?" checklist
(#1287, research: docs/research/test-case-design-2026-07-28.md) — upstream
covers test *coupling* (behavior vs implementation) only, with no guidance
on case selection or an objective value oracle.
MIT — see THIRD_PARTY_LICENSES/aihero-skills-MIT.txt.
-->

# Good and Bad Tests

## Good Tests

**Integration-style**: Test through real interfaces, not mocks of internal parts.

```typescript
// GOOD: Tests observable behavior
test("user can checkout with valid cart", async () => {
  const cart = createCart();
  cart.add(product);
  const result = await checkout(cart, paymentMethod);
  expect(result.status).toBe("confirmed");
});
```

Characteristics:

- Tests behavior users/callers care about
- Uses public API only
- Survives internal refactors
- Describes WHAT, not HOW
- One logical assertion per test

## Bad Tests

**Implementation-detail tests**: Coupled to internal structure.

```typescript
// BAD: Tests implementation details
import * as paymentService from "./paymentService";
jest.mock("./paymentService");

test("checkout calls paymentService.process", async () => {
  const mockProcess = paymentService.process as jest.MockedFunction<
    typeof paymentService.process
  >;
  mockProcess.mockResolvedValue({ ok: true });
  await checkout(cart, payment);
  expect(mockProcess).toHaveBeenCalledWith(cart.total);
});
```

Red flags:

- Mocking internal collaborators
- Testing private methods
- Asserting on call counts/order
- Test breaks when refactoring without behavior change
- Test name describes HOW not WHAT
- Verifying through external means instead of interface

```typescript
// BAD: Bypasses interface to verify
test("createUser saves to database", async () => {
  await createUser({ name: "Alice" });
  const row = await db.query("SELECT * FROM users WHERE name = ?", ["Alice"]);
  expect(row).toBeDefined();
});

// GOOD: Verifies through interface
test("createUser makes user retrievable", async () => {
  const user = await createUser({ name: "Alice" });
  const retrieved = await getUser(user.id);
  expect(retrieved.name).toBe("Alice");
});
```

## Choosing Cases

Good/Bad Tests above is about *coupling* — does the test survive a refactor. This section is about *coverage* — did you pick the right cases at all. Apply it per AC item, before writing the test.

1. **Partitions.** Split each input into equivalence classes — inputs the code should treat the same way (valid range, below range, above range, wrong type, empty, null). One representative case per class, not one case per possible value.
2. **Boundaries.** For each partition edge, test the boundary value itself and the value just past it (off-by-one is where bugs cluster — 0 vs 1, max vs max+1, empty string vs single-char).
3. **Interaction rule.** For 2+ parameters: cover every single-parameter value at least once (each value appears in at least one case) before combining pairs. Go deeper than pairwise (triples, exhaustive) only where risk justifies it — a payment-amount × currency × rounding-mode interaction earns triples; three independent UI flags usually don't.
4. **Mandatory negative case.** At least one case per AC item where the *correct* behavior is to **not** succeed — reject, no-op, return empty, throw. A suite with only positive cases has not tested the boundary of the requirement, only its interior.
5. **Hughes' five property types** (Hughes, *How to Specify It!*) — when a case is hard to pin to a single expected value, reach for one of these shapes instead of skipping it:
   - **Invariant** — something that must always hold, regardless of input (a list stays sorted after any insert).
   - **Postcondition** — a direct input → output check (the common case; most unit tests are this).
   - **Metamorphic relation** — a relation between two *related* runs, used when no independent oracle exists for a single run (see below).
   - **Inductive** — the operation composes with itself predictably (`insert` then `insert` again behaves like a single batch `insert`).
   - **Model-based** — the system's behavior matches a simpler reference model (a cache's reads match a plain dict given the same writes).

   **Use a metamorphic relation whenever you cannot independently derive the expected value from the requirement** — e.g. ranking quality, a fuzzy-matching score, an LLM-judged verdict. Instead of asserting an exact output, assert a relation that must hold between two runs: *adding a strictly-more-relevant document must not lower `memory_recall`'s top rank*; *a code-review verdict parser must classify a strict superset of the same findings the same way*; *`rework_policy` must not loosen on a stricter input*; *the installer must be idempotent — running it twice produces the same file state as running it once*. These are this repo's named candidates for metamorphic tests where no single-run oracle exists.

### Checklist: is this test valuable?

Run this before treating a written test as done. Items marked ⛔ are **blocking** — a test that fails one is not done, not "done with a caveat." The rest are advisory — note the gap, don't necessarily rewrite on the spot.

| # | Check | How it's checked | Blocking |
|---|---|---|---|
| 1 | **Traceability** — test points to an AC item or a specific defect | Already covered by `/implement` §4-TDD (every test traces to an AC bullet) | — |
| 2 | **Independent oracle** — expected value is derived *from the requirement*, not copied from a run | Red flag: a literal pasted in after watching the test fail once. If you can't state where the expected value comes from without pointing at the test run, it's not independent. | ⛔ |
| 3 | **Mutation probe** — corrupting the line of implementation the test allegedly covers turns it red | See `tdd-loop.md` §3 — mutate, confirm RED, revert. A test that survives its own mutation is asserting nothing. | ⛔ |
| 4 | **Case selection articulated** — partitions/boundaries were actually listed, and at least one negative case is present | Applies the Partitions/Boundaries/Interaction/Negative-case steps above. For 2+ parameters, every single value is covered at least once. | ⛔ |
| 5 | **Structure-insensitivity** — renaming an internal helper doesn't break the test | No `assert_called*`/mock assertions on internal collaborators; checks state or observable output, not interactions (ties to Good/Bad Tests above) | advisory |
| 6 | **Readable failure** — the test name describes behavior ("should ..."), and the failure reason is visible without reading the test body | Skim the name and the assertion message in isolation | advisory |
| 7 | **Non-duplicate** — doesn't repeat an already-covered partition without adding mutation-killing power | Compare against existing cases for the same AC item before adding a new one | advisory |

**Why exactly 2, 3, 4 are blocking:** they close the three confirmed failure mechanisms behind false-confidence tests — an oracle copied from a run (test can't fail on a regression, only on a diff from itself), a test that mutation-probing shows catches nothing (green regardless of the code), and one-sided case selection (only positive cases, tying back to #1260's "one-sided evals create one-sided optimization" — a suite that never tests rejection trains the same blind spot into the implementation). Items 5–7 are about maintenance cost and signal quality, not false confidence — worth fixing, not worth blocking on.

Deliberately **not** in this checklist: a coverage-percentage threshold, a "one test per method" rule, or a full test-smell catalog. Source: `docs/research/test-case-design-2026-07-28.md` (#1247, confidence 82/100).
