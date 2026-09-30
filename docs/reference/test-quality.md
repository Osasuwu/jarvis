# Test quality — what makes a test worth adding

Pull-only. Read it before you add, change or delete a test, and before you review one;
`AGENTS.md` → *Engineering posture* points here. It is the repo's own copy of the rule, so a run
with no user-level layer (the unattended worker) has the whole of it. Written from the test
audit in #1942–#1945: every rule below has a defect class behind it that reached `main` through
a green CI and a review.

One question decides every case: **would this test go red if the behaviour it is named after
broke?** A test that stays green in that case is worse than no test — it is counted as coverage.

## Before adding a test

- **Find the neighbour first.** If an existing test already goes red on the mutation you are
  about to guard, do not add a second one. An invariant over a set of files (every workflow
  pins its actions) is one test that walks the set, not a copy per file — copies leave the
  files nobody copied it for unguarded.
- **Not every acceptance criterion is a test.** Some are verified by a command's output. A
  one-off static fact (a symbol removed, a file renamed, a value changed once) can be verified
  by reading; behaviour cannot, and neither can a property that has to keep holding after this
  PR (every future workflow obeys it) — that one needs a check that stays. Say which in the PR.
- **Never write** (the next two bullets are the exceptions): a test that a file exists or a
  symbol imports; a constructor-or-getter echo; a constant compared with the expression that
  defines it; a pin on the wording of prose, on the source text of one production function, or
  on an artifact that can no longer change (an applied migration); a test whose only claim is
  that a call does not raise; a test added to reach a count.
- **A literal pin is a real test when the literal is the contract**: a URL, a header, a message
  another program parses, a string the user reads, a default or limit a recorded decision
  fixed, the canonical member list of a closed set. Cite the issue.
- **Two more that are real tests.** A lint that bans or requires a construct across the whole
  tree — it walks the set and goes red on a planted violation. A "does not raise" test when
  raising is what the broken behaviour does, or when it is the accepting half of a limit with
  its rejecting half next to it.
- **One data-lint is one test.** A schema rule over N entries is a loop that collects every
  failing entry and reports them in one failure, not N parametrized items.

## The oracle

- **The expected value is independent of the code under test.** A literal you worked out, not
  a constant imported from the module, and not the production code's steps written out again
  inside the test file. For a workflow, SQL policy or shell script: execute or parse the real
  artifact. A Python re-creation of it tests the re-creation (see *Open exception* below).
  The one case where both sides come from production is parity between two artifacts that
  must agree (a script and its twin, a default and the example file that documents it).
- **Which members to check goes the other way: take it from production.** When a test walks a
  set (the workflow list, the registered gates, the protected paths), the membership is read
  from the real code or config, never kept as a hand-written list in the test. This is about
  which members, not about values: what each member must equal stays a literal.
- **It must fail when the code under test does nothing, or does the nearest wrong thing.** As
  the test's claim, `>= 1`, `is not None`, `isinstance`, `len(x) > 0`, a bare return code,
  `result is True` from a canned reply, `a or b`, and an `in` / `startswith` / `match=` whose
  substring another outcome also produces are true in more than one outcome. Assert the value.
  (The same checks are right as a guard in front of a loop — see *No assertion that may
  never run*.)
- **A substring of a whole file is not an oracle** when the string can occur somewhere else in
  the file (a comment, another job). Parse, then look at the node.
- **Everything the test's name claims is asserted.**
- **No assertion that may never run.** An `assert` under `if`, inside a `for`, or in a callback
  needs an unconditional assertion before it that the branch is taken, the collection is
  non-empty, the callback was called.
- **A rejection test trips exactly one limit and names it** — `pytest.raises(X, match=...)` or
  the error code. Every other input stays inside its limits.
- **Do not seed with the answer.** A fixture that already holds the output, or a mock whose
  canned return is the expected value, lets the code under test be a no-op.
- **Hermetic, and it runs in CI.** No dependence on the developer's environment, home
  directory, clock or network. No `importorskip` / `skipif` on something CI does not install
  (a skip whose condition is false in the CI job, such as `win32` on a suite CI runs on
  Linux, is fine), no fixture that turns a setup failure into a skip, no non-strict `xfail`.

## Mutation probe

Every test you add or change gets one, whatever the size of the PR.

1. Commit your change. Make the smallest edit to the **production file** that breaks the
   behaviour in the test's name while the code still runs: a wrong value, a flipped condition,
   a swapped order, a dropped branch. Deleting the function, adding a `raise` or breaking an
   import does not count — that turns every test red, including the ones that assert nothing.
   For the same reason a test that was red before the code existed has not been probed.
   Where raising is itself the behaviour in the test's name (a does-not-raise test, a
   rejection), the exception is the wrong value and the mutation is the edit that brings it
   back or takes it away. For a data-lint the production file is the data: plant one
   violating entry. For a workflow or a migration it is the file the test reads; a test that
   does not read the real file has no probe, and that is the finding.
2. Run the test's whole file. The test must fail. An older test that fails on the same
   mutation for the same claim is the neighbour you missed: the new test is the duplicate.
   Restore the file (`git checkout -- <file>`).
3. Never mutate the test, or a copy of the logic that lives in the test file.
4. A probe that stays green is a finding: fix the test or delete it, do not push it.
   A test with no probe to run gets a line saying so, never an invented one:
   `no probe — <test>: <what it cannot catch>` for a mirror (*Open exception* below);
   `not probed — <why>` where the run may not edit the artifact (the unattended worker
   never edits `.github/workflows/**`, not even to probe) or the test is skipped on this
   platform. That probe falls to whoever merges.
5. A fixture edit is probed once, through the code path the fixture exists to reach.
6. Run the tests you touched with `pytest -rs`: none may be reported skipped, except a skip
   whose condition is false in the CI job — name it. A skip on a dependency the CI job does
   not install is not done: make the job install it or take the skip out.

If your diff tightens a limit, changes a default, adds an early exit, edits a fixture or moves
logic: grep `tests/` for the changed symbol, the limit's name, the fixture's name and the
exception type or error code the changed limit raises. The tests
whose claim the change touches get the same probe — a rejection test may now be rejected for
the new reason and no longer guard the old one, a moved test may still patch the old path.
Repairing what this finds is in scope of the PR.

## Deleting a test

Name the kept test that goes red for the same cause, with the mutation that reddens it, or the
reason the deleted one could not fail, or the *Never write* class it falls in. If the deletion leaves production code with no test at
all, say so in the PR.

## What the PR's `## Testing` section holds

- each acceptance criterion and how it was verified: the test that goes red for it, a command's
  output, or — for a one-off static fact only — reading;
- every added or changed test appears in a line `<production file>:<line> <mutation> → <tests>
  red` (one line per distinct mutation, listing the tests it turns red — one mutation
  offered for tests that claim different behaviours is not enough; where the probe is not a
  line edit, the change in place of the line), or in a `no probe` / `not probed` line;
- for every deleted test, the kept test and its mutation, or the reason, or the class;
- the line `CI run not checked for skips` — an unattended run cannot wait for its own CI, so
  reading the PR run's summary line against `main`'s latest falls to whoever merges: passed
  moved by the diff's net change in tests (added minus removed), skipped is not above
  `main`'s. The line is then replaced with the two pairs of numbers.

A pass count is not evidence and is not asked for.

## Open exception: `tests/ci/` mirrors

[`ci-guard-meta-tests.md`](ci-guard-meta-tests.md) asks each workflow guard's meta-test to
"reimplement the guard's decision rule in Python" — which *The oracle* above rules out, because
the workflow can then change with the mirror still green. Whether that convention stays is
undecided ([#1944](https://github.com/Osasuwu/jarvis/issues/1944)). Until it is: parse the real
workflow and assert on its nodes wherever that expresses the claim; where a test has to mirror
logic, state in the PR what it cannot catch (the `no probe` line), and do not offer a mutation
of the mirror as the probe.

## What this file cannot do

It reaches the author at write time. An assertion that never executes, a test that is skipped
only in CI, a fixture that went dead under a later PR and a duplicate that arrived in a
different PR are invisible to the author; they belong to a gate, the review prompt or a
periodic audit — [#1948](https://github.com/Osasuwu/jarvis/issues/1948).
