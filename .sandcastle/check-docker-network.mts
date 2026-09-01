// Contract check for the dedicated docker network (#1121 step 13). Verifies
// config/sandcastle.yaml carries a non-empty `network` scalar and that
// main.mts's docker() sandbox call wires it through — segmentation only
// (the container can't reach other containers/services on the default
// bridge), NOT egress filtering (outbound internet access is unaffected;
// that's a separate, not-yet-built control).

import { readFileSync } from "node:fs";
import { readYamlScalar } from "./yaml-list.mts";

let failures = 0;
const fail = (msg: string) => {
  failures += 1;
  console.error(`FAIL: ${msg}`);
};

const repoConfigPath = new URL("../config/sandcastle.yaml", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const network = readYamlScalar(repoConfigPath, "network");
if (!network) fail("repo config/sandcastle.yaml network parsed as empty");

const mainPath = new URL("./main.mts", import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1");
const mainText = readFileSync(mainPath, "utf-8");
// Strip line comments before matching so a commented-out wiring line (dead
// code, not a real passthrough) can't fool a naive substring/regex check.
const mainTextNoComments = mainText
  .split(/\r?\n/)
  .map((l) => l.replace(/\/\/.*$/, ""))
  .join("\n");
if (!/docker\(\{[\s\S]*?network:\s*sandcastleNetwork/.test(mainTextNoComments)) {
  fail("main.mts's docker() call does not wire in a live (non-commented) `network: sandcastleNetwork` option");
}

if (failures > 0) {
  console.error(`check-docker-network: ${failures} failure(s)`);
  process.exit(1);
}
console.log("check-docker-network: config/sandcastle.yaml network validates against main.mts docker() wiring");
