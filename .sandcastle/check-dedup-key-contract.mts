// One-sided contract check for the shared dedup-key fixture (#1121 step 11).
// The fixture tests/fixtures/sandcastle-dedup-key.json pins the completion-
// event dedup key format both the supervisor's own emission (main.mts) and
// the future S4 sweeper's re-emission must reproduce byte-for-byte — the
// issue's motivating bug was an a0/a1 drift between this side and the Python
// mirror. The mirror Python check lives in
// tests/sandcastle/test_dedup_key_contract.py.

import { readFile } from "node:fs/promises";
import { buildDedupKey } from "./completion.mts";

const fixturePath = new URL("../tests/fixtures/sandcastle-dedup-key.json", import.meta.url);
const fixture: { cases: Array<{ eventType: string; taskId: string; attempt: number; dedupKey: string }> } =
  JSON.parse(await readFile(fixturePath, "utf8"));

let failures = 0;
const fail = (msg: string) => {
  failures += 1;
  console.error(`FAIL: ${msg}`);
};

if (fixture.cases.length === 0) fail("fixture has no cases");

for (const c of fixture.cases) {
  const actual = buildDedupKey(c.eventType, c.taskId, c.attempt);
  if (actual !== c.dedupKey) {
    fail(`buildDedupKey(${c.eventType}, ${c.taskId}, ${c.attempt}) = ${actual}, expected ${c.dedupKey}`);
  }
}

if (failures > 0) {
  console.error(`check-dedup-key-contract: ${failures} failure(s)`);
  process.exit(1);
}
console.log("check-dedup-key-contract: fixture validates against TS buildDedupKey");
