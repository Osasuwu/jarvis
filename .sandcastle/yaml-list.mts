// Minimal flat-list YAML extractor (#1121). No yaml npm dependency is
// installed in this toolchain (package.json devDependencies carries only
// @ai-hero/sandcastle + tsx), and config/sandcastle.yaml's
// billing_key_denylist is a single flat scalar array, so this hand-rolled
// extractor reads just that one key rather than pulling in a general YAML
// parser for one array.
// ceiling: only extracts a flat `key:\n  - "ITEM"` list under the given top
// key; nested/multiline YAML under that key would not parse. Fine for this
// config's shape — switch to a real yaml parser if the shape ever changes.

import { readFileSync } from "node:fs";

export function readYamlStringList(yamlPath: string, key: string): string[] {
  const text = readFileSync(yamlPath, "utf-8");
  const lines = text.split(/\r?\n/);
  const startIdx = lines.findIndex((l) => l.trim() === `${key}:`);
  if (startIdx === -1) return [];
  const items: string[] = [];
  for (let i = startIdx + 1; i < lines.length; i++) {
    const line = lines[i];
    const match = line.match(/^\s*-\s*(.+?)\s*$/);
    if (!match) break;
    items.push(match[1].replace(/^["']|["']$/g, ""));
  }
  return items;
}
