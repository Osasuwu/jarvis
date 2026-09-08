# Sandcastle agent image — slice 2 (epic #534, issue #540)
#
# Runtime: Claude Code CLI + git + gh.
# The agent inside this container talks to a local Ollama instance running
# on the host (Docker Desktop's host.docker.internal:11434), via Ollama's
# native Anthropic-compatible endpoint.
#
# Build (from repo root — context must include .claude-userlevel/skills/):
#   docker build -t sandcastle:jarvis -f .sandcastle/Dockerfile .
#
# Used by: .sandcastle/main.mts (npm run sandcastle)
#
# Decisions:
#   894ac658 — Claude Code + local Ollama, sterile container
#   436f9549 — sandcastle opens PRs only, never merges
#   (228a2d9b's memory MCP bridge was retired along with the memory stack, #1801)

FROM node:22-bookworm

# System deps. python3 for the protected-files PreToolUse hook (stdlib only,
# no venv needed). jq for gh shell snippets.
RUN apt-get update && apt-get install -y --no-install-recommends \
      git \
      curl \
      ca-certificates \
      jq \
      gnupg \
      python3 \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI — needed for `gh issue edit`, `gh pr create`. Official apt repo.
RUN install -dm 0755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
       | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg > /dev/null \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
       > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

# Match sandcastle's reference image: rename node user → agent, keep UID 1000
# so bind-mounts owned by the host user resolve cleanly.
RUN usermod -d /home/agent -m -l agent node \
    && groupmod -n agent node
USER agent
WORKDIR /home/agent

# Claude Code CLI (official installer). Lands in ~/.local/bin/claude.
RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH="/home/agent/.local/bin:$PATH"

# Canonical skill set — vendor .claude-userlevel/skills/ so the agent has the
# same skill surface as an inline /implement session. User-scope path picked up
# automatically by Claude Code at runtime.
COPY --chown=agent:agent .claude-userlevel/skills/ /home/agent/.claude/skills/

# Permission perimeter — baked into the image, not applied at spawn time.
# container-settings.json carries the credential-path permissions.deny array
# and the PreToolUse hook wired to scripts/protected-files.py (arrives via the
# worktree bind-mount at SANDBOX_REPO_DIR, so no separate script COPY needed).
# Landing at /home/agent/.claude/settings.json makes it Claude Code's
# user-scope settings inside the container (#1121 step 12).
COPY --chown=agent:agent .sandcastle/container-settings.json /home/agent/.claude/settings.json

# Documented today (docs/design/sandcastle-integration.md) as an active
# control on the spawn env — this makes it actually true.
ENV JARVIS_PRINCIPAL=subagent

# Sandcastle bind-mounts the worktree at SANDBOX_REPO_DIR and exec's into it.
# Container just needs to stay alive; sandcastle drives commands via `docker exec`.
ENTRYPOINT ["sleep", "infinity"]
