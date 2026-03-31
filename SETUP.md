# Setup — personal-AI-agent

Steps to configure on a new device.

## 1. Clone repos

```bash
git clone https://github.com/Osasuwu/personal-AI-agent ~/GitHub/personal-AI-agent
git clone https://github.com/Osasuwu/GitHub ~/GitHub
```

## 2. Python environment (MCP memory server only)

```bash
cd ~/GitHub/personal-AI-agent
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r mcp-memory/requirements.txt
```

## 3. Install git hook (skills sync)

Syncs `.claude/skills/` to `~/GitHub` automatically on commit.

```bash
cp ~/GitHub/personal-AI-agent/scripts/post-commit \
   ~/GitHub/personal-AI-agent/.git/hooks/post-commit
chmod +x ~/GitHub/personal-AI-agent/.git/hooks/post-commit
```

After this: any commit in personal-AI-agent that touches `.claude/skills/` will automatically commit the updated skills to `~/GitHub` as well.

## 4. MCP config

`.mcp.json` files are committed — no manual setup needed. Supabase credentials are read from environment variables. Add to your shell profile:

```bash
export SUPABASE_URL="..."
export SUPABASE_KEY="..."
export VOYAGE_API_KEY="..."
```
