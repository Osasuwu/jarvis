import { run, claudeCode } from "@ai-hero/sandcastle";
import { docker } from "@ai-hero/sandcastle/sandboxes/docker";

// Jarvis sandcastle entry — slice 1 of epic #534. Manual smoke loop on Main PC.
// Run: npm run sandcastle  (or: npx tsx .sandcastle/main.mts)
//
// Prereqs + decisions: see .sandcastle/README.md and decisions 894ac658,
// 436f9549, 0c3017c6 referenced from epic #534. Watchdog + schedule + memory
// MCP bridge land in slices 2/4 — this file stays config-only (<50 lines).

const ollamaModel = process.env.OLLAMA_MODEL ?? "qwen2.5-coder:14b";
const ollamaUrl = process.env.OLLAMA_BASE_URL ?? "http://host.docker.internal:11434";
const ghToken = process.env.GH_TOKEN;
if (!ghToken) {
  throw new Error(
    "GH_TOKEN is required (sandcastle agent claims issues + opens PRs via gh). " +
      "Set it in .sandcastle/.env — see .sandcastle/.env.example.",
  );
}

await run({
  name: "jarvis-worker",
  sandbox: docker({
    imageName: "sandcastle:jarvis",
    env: {
      // Native Anthropic-compatible endpoint exposed by Ollama ≥ 0.14 (Jan 2026).
      ANTHROPIC_BASE_URL: ollamaUrl,
      ANTHROPIC_AUTH_TOKEN: "ollama",
      // Forward host-side gh credentials so the agent can claim issues + open PRs.
      GH_TOKEN: ghToken,
    },
  }),
  agent: claudeCode(ollamaModel),
  promptFile: "./.sandcastle/prompt.md",
  maxIterations: 1,
  branchStrategy: { type: "merge-to-head" },
  hooks: {
    sandbox: {
      onSandboxReady: [
        { command: "git config user.email agent@jarvis.local" },
        { command: "git config user.name 'Jarvis Agent'" },
      ],
    },
  },
});
