import { run, claudeCode } from "@ai-hero/sandcastle";
import { docker } from "@ai-hero/sandcastle/sandboxes/docker";
import { writeFile, mkdir } from "node:fs/promises";
import { dirname } from "node:path";

// Jarvis sandcastle entry — slices 1 + 2 of epic #534. Manual smoke loop on Main PC.
// Run: npm run sandcastle  (or: npx tsx .sandcastle/main.mts)
//
// Prereqs + decisions: see .sandcastle/README.md and decisions 894ac658,
// 436f9549, 228a2d9b, 0c3017c6 referenced from epic #534. Watchdog + schedule
// land in slice 4 — this file stays config-only.

// Agent model + endpoint. Slice 5 (#543) introduces multi-tier escalation:
// the PS1 watchdog re-invokes us with SANDCASTLE_AGENT_{MODEL,BASE_URL,AUTH_TOKEN}
// overridden when retrying on a smaller Ollama model (Tier 1) or a remote
// DeepSeek/Claude API endpoint (Tier 2). Falls back to the slice-1/2 Ollama
// defaults when the watchdog isn't driving — single-shot manual smoke runs
// keep working unchanged.
const agentModel =
  process.env.SANDCASTLE_AGENT_MODEL ??
  process.env.OLLAMA_MODEL ??
  "qwen3-coder:30b";
const agentBaseUrl =
  process.env.SANDCASTLE_AGENT_BASE_URL ??
  process.env.OLLAMA_BASE_URL ??
  "http://host.docker.internal:11434";
// Tier 0/1 use the literal "ollama" auth token (Ollama's native Anthropic
// endpoint ignores it); Tier 2 carries a real API key (DeepSeek / Claude).
const agentAuthToken = process.env.SANDCASTLE_AGENT_AUTH_TOKEN ?? "ollama";
// When the watchdog retries on the same issue (escalation chain, AC #3),
// it sets SANDCASTLE_TARGET_ISSUE so prompt.md can pin the agent to that
// issue instead of picking afresh from the queue.
const targetIssue = process.env.SANDCASTLE_TARGET_ISSUE ?? "";
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

// Slice 4 (#541): when the PowerShell watchdog invokes us, it sets
// SANDCASTLE_RESULT_FILE so we dump the RunResult JSON for it to parse
// (commits, branch, iterations, usage). Direct stdout capture is too noisy
// — sandcastle interleaves agent output with orchestrator logs.
const resultFile = process.env.SANDCASTLE_RESULT_FILE;
// `??` does not coalesce empty string -- guard against blank env vars
// silently producing maxIterations=0 (zero-iteration silent run).
const maxIterations = Math.max(1, Number(process.env.SANDCASTLE_MAX_ITERATIONS) || 1);

const result = await run({
  name: "jarvis-worker",
  sandbox: docker({
    imageName: "sandcastle:jarvis",
    env: {
      // Native Anthropic-compatible endpoint exposed by Ollama ≥ 0.14 (Jan 2026)
      // for Tier 0/1; remote provider URL + key for Tier 2 (slice 5, #543).
      ANTHROPIC_BASE_URL: agentBaseUrl,
      ANTHROPIC_AUTH_TOKEN: agentAuthToken,
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
      // Forced-target issue for slice-5 escalation retries. Empty string =
      // free pick from queue (default behavior).
      SANDCASTLE_TARGET_ISSUE: targetIssue,
    },
  }),
  agent: claudeCode(agentModel),
  promptFile: "./.sandcastle/prompt.md",
  maxIterations,
  branchStrategy: { type: "merge-to-head" },
  hooks: {
    sandbox: {
      onSandboxReady: [
        // Sandcastle's own SandboxLifecycle already propagates host git
        // user.name/user.email via `git config --global` before user hooks
        // run, so explicit overrides here are redundant. Repo-local
        // `git config` (without --global) would write to the worktree's
        // parent .git/config which on Windows bind-mounts races on the
        // .lock file (#607 v2 / Workshop PC4 repro 2026-05-13).
        // Override the worktree's .mcp.json with the container-scoped version
        // (memory MCP only). The host .mcp.json registers many host-only
        // servers that would fail inside the sterile container. Sandcastle
        // uses copy-on-write worktrees so this never touches the host repo.
        // Adding the path to info/exclude first ensures `git add -A` inside
        // the agent loop cannot accidentally stage the override.
        //
        // `.git` in a worktree is a *file* (gitdir pointer), not a directory,
        // so `>> .git/info/exclude` opens via the shell and fails with ENOTDIR.
        // `git rev-parse --git-path info/exclude` resolves the actual shared
        // info/exclude path inside the parent .git directory (#607).
        { command: "mkdir -p $(git rev-parse --git-path info)" },
        { command: "echo /.mcp.json >> $(git rev-parse --git-path info/exclude)" },
        { command: "cp /opt/sandcastle/container-mcp.json .mcp.json" },
      ],
    },
  },
});

if (resultFile) {
  await mkdir(dirname(resultFile), { recursive: true });
  await writeFile(
    resultFile,
    JSON.stringify(
      {
        runId,
        branch: result.branch,
        commits: result.commits,
        completionSignal: result.completionSignal,
        logFilePath: result.logFilePath,
        preservedWorktreePath: result.preservedWorktreePath,
        iterations:
          result.iterations?.map((it) => ({
            sessionId: it.sessionId,
            usage: it.usage,
          })) ?? [],
      },
      null,
      2,
    ),
    "utf8",
  );
}
