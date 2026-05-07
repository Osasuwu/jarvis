import { run, claudeCode } from "@ai-hero/sandcastle";
import { docker } from "@ai-hero/sandcastle/sandboxes/docker";

// Jarvis sandcastle entry — AFK loop over ready-for-agent issues.
// Run: npx tsx .sandcastle/main.mts
//
// This is scaffolding. The /delegate skill still uses the in-session Agent
// dispatch path; sandcastle is being introduced as a parallel option. See
// docs/design/sandcastle-integration.md (TBD) before wiring /delegate on top.

await run({
  name: "jarvis-worker",
  sandbox: docker(),
  agent: claudeCode("claude-sonnet-4-6"),
  promptFile: "./.sandcastle/prompt.md",
  maxIterations: 3,
  branchStrategy: { type: "merge-to-head" },
  hooks: {
    sandbox: {
      onSandboxReady: [
        // Repo is Python+Claude-Code-native, but agents may still need gh + git.
        // No npm install here by default — package.json is for sandcastle only.
        { command: "git config user.email agent@jarvis.local" },
        { command: "git config user.name 'Jarvis Agent'" },
      ],
    },
  },
});
