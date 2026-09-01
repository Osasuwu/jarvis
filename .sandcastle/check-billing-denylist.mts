// Contract check for the shared billing-key denylist (#1121). Verifies
// yaml-list.mts's hand-rolled extractor reads config/sandcastle.yaml's
// billing_key_denylist the same way agents/sandcastle_config.py's
// load_sandcastle_config does, and that a fixture with a differently-shaped
// list still round-trips. Mirror Python coverage:
// tests/reactive_core/test_sandcastle_config.py::TestBillingKeyDenylist.

import { readYamlStringList } from "./yaml-list.mts";

let failures = 0;
const fail = (msg: string) => {
  failures += 1;
  console.error(`FAIL: ${msg}`);
};

// 1. Reads the repo's own config/sandcastle.yaml and finds a non-empty list
// carrying the known-required keys — an empty result here would silently
// disable the subscription-mode billing guard in main.mts.
const repoConfigPath = new URL("../config/sandcastle.yaml", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const repoList = readYamlStringList(repoConfigPath, "billing_key_denylist");
if (repoList.length === 0) fail("repo config/sandcastle.yaml billing_key_denylist parsed as empty");
for (const required of ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"]) {
  if (!repoList.includes(required)) fail(`repo denylist missing required key ${required}`);
}

// 2. A fixture YAML with quoted items and an unrelated trailing key parses
// only the target list, stops at the first non-list-item line, and strips
// quotes.
import { mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const tmpDir = mkdtempSync(join(tmpdir(), "sandcastle-yaml-list-"));
const fixturePath = join(tmpDir, "fixture.yaml");
writeFileSync(
  fixturePath,
  'slots: ["slot-1"]\nbilling_key_denylist:\n  - "ANTHROPIC_API_KEY"\n  - ANTHROPIC_AUTH_TOKEN\nquota_gate:\n  enabled: true\n',
  "utf-8",
);
const fixtureList = readYamlStringList(fixturePath, "billing_key_denylist");
if (JSON.stringify(fixtureList) !== JSON.stringify(["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"])) {
  fail(`fixture list mismatch: got ${JSON.stringify(fixtureList)}`);
}

// 3. A missing key returns an empty list rather than throwing.
const missingKeyList = readYamlStringList(fixturePath, "no_such_key");
if (missingKeyList.length !== 0) fail("missing key should return an empty list");

rmSync(tmpDir, { recursive: true, force: true });

if (failures > 0) {
  console.error(`check-billing-denylist: ${failures} failure(s)`);
  process.exit(1);
}
console.log("check-billing-denylist: yaml-list extractor validates against repo config + fixture");
