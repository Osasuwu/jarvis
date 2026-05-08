import { run, claudeCode } from "@ai-hero/sandcastle";
import { docker } from "@ai-hero/sandcastle/sandboxes/docker";

// Jarvis sandcastle entry — slices 1 + 2 of epic #534. Manual smoke loop on Main PC.
// Run: npm run sandcastle  (or: npx tsx .sandcastle/main.mts)
//
// Prereqs + decisions: see .sandcastle/README.md and decisions 894ac658,
// 436f9549, 228a2d9b, 0c3017c6 referenced from epic #534. Watchdog + schedule
// land in slice 4 — this file stays config-only.

const ollamaModel = process.env.OLLAMA_MODEL ?? "qwen2.5-coder:14b";
const ollamaUrl = process.env.OLLAMA_BASE_URL ?? "http://host.docker.internal:11434";
const ghToken = process.env.GH_TOKEN;
if (!ghToken) {
  throw new Error(
    "GH_TOKEN is required (sandcastle agent claims issues + opens PRs via gh). " +
      "Set it in .sandcastle/.env — see .sandcastle/.env.example.",
  );
}

// Memory MCP bridge env (slice 2, issue #540). Forwarded into the container so
// the in-container memory MCP server (/opt/mcp-memory/server.py) can reach
// Supabase. SUPABASE_KEY MUST be the anon key — service-role is banned per
// decision 228a2d9b. VOYAGE_API_KEY is optional (recall degrades to keyword).
const supabaseUrl = process.env.SUPABASE_URL;
const supabaseKey = process.env.SUPABASE_KEY;
const voyageKey = process.env.VOYAGE_API_KEY ?? "";
if (!supabaseUrl || !supabaseKey) {
  throw new Error(
    "SUPABASE_URL and SUPABASE_KEY are required for the memory MCP bridge. " +
      "Set them in .sandcastle/.env — anon key only, never service-role. " +
      "See .sandcastle/.env.example for details.",
  );
}

// Stable per-run identifier consumed by the agent's source_provenance tags
// (prompt.md §"Memory provenance"). Format: <run-name>-<UTC-yyyymmdd-hhmmss>.
// Stays opaque (no secrets) so it's safe to embed in memory rows and PR bodies.
const runId =
  process.env.SANDCASTLE_RUN_ID ??
  `jarvis-worker-${new Date().toISOString().replace(/[-:T.Z]/g, "").slice(0, 14)}`;

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
      // Memory MCP bridge — Claude Code expands ${...} in the project-scope
      // .mcp.json (copied from /opt/sandcastle/container-mcp.json by the
      // onSandboxReady hook below) from these container env vars.
      SUPABASE_URL: supabaseUrl,
      SUPABASE_KEY: supabaseKey,
      VOYAGE_API_KEY: voyageKey,
      // Per-run id for the agent's source_provenance tags. See prompt.md.
      SANDCASTLE_RUN_ID: runId,
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
        // Override the worktree's .mcp.json with the container-scoped version
        // (memory MCP only). The host .mcp.json registers many host-only
        // servers that would fail inside the sterile container. Sandcastle
        // uses copy-on-write worktrees so this never touches the host repo.
        // Adding the path to .git/info/exclude first ensures `git add -A`
        // inside the agent loop cannot accidentally stage the override.
        { command: "echo /.mcp.json >> .git/info/exclude" },
        { command: "cp /opt/sandcastle/container-mcp.json .mcp.json" },
      ],
    },
  },
});
