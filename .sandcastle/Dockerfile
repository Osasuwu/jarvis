# Sandcastle agent image — slice 1 (epic #534, issue #537)
#
# Thin runtime: Claude Code CLI + git + gh + curl. The agent inside this
# container talks to a local Ollama instance running on the host (Docker
# Desktop's host.docker.internal:11434), via Ollama's native
# Anthropic-compatible endpoint. No proxy. No model weights baked in.
#
# Build:   docker build -t sandcastle:jarvis .sandcastle/
# Used by: .sandcastle/main.mts (npm run sandcastle)
#
# Decisions: 894ac658 (Claude Code + local Ollama, sterile container) and
# 436f9549 (sandcastle opens PRs only, never merges) — see epic #534.

FROM node:22-bookworm

# System deps. jq is used by gh and by ad-hoc shell in the agent prompt.
RUN apt-get update && apt-get install -y --no-install-recommends \
      git \
      curl \
      ca-certificates \
      jq \
      gnupg \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI — needed for `gh issue edit`, `gh pr create`. Official apt repo.
# Pinned to the keyring location upstream documents; refresh on image rebuild.
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

# Sandcastle bind-mounts the worktree at SANDBOX_REPO_DIR and exec's into it.
# Container just needs to stay alive; sandcastle drives commands via `docker exec`.
ENTRYPOINT ["sleep", "infinity"]
