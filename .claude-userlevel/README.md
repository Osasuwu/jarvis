# `.claude-userlevel/` — source of truth for user-level Jarvis

This directory mirrors what ships to `~/.claude/` via
`scripts/install/installer.py`. Keep it separate from `.claude/` so M5 (#340)
can tombstone the project-scoped copy cleanly without deleting
project-specific skills that legitimately stay under
`jarvis/.claude/skills/` (e.g. `/sprint-report`).

## Layout

```
.claude-userlevel/
└── skills/          # Core universal skills (M2 #337)
    ├── implement/
    ├── delegate/
    └── ...
```

Later milestones will add:

- `SOUL.md` (M4 #339)
- `settings.json` (M3 #338 — hooks)
- `.mcp.json` (M3 #338)

## Why a whitelist in `install-manifest.yaml`?

An explicit whitelist means dropping a README, experiment note, or
half-finished skill into this tree doesn't auto-leak into every user's
`~/.claude/`. Add new core skills to the `skills.include` list in
`install-manifest.yaml` at the same time you add the directory here.

## Keeping in sync with `.claude/skills/`

Until M5, the same skill exists in two places (DRY violation accepted
for the no-op window). Pick one as canonical on each edit:

- **Core skill change** → edit `.claude-userlevel/skills/<name>/` and
  also update the duplicate in `.claude/skills/<name>/` so project-CWD
  Claude Code keeps working. Simplest rule: edit both in one commit.
- After M5 merges, `.claude/skills/<core>/` is deleted and the
  userlevel copy becomes the only copy.

## Path portability audit (follow-up)

Skill bodies currently reference `scripts/` and `config/` as
project-CWD-relative paths. Once user-level Jarvis runs from non-jarvis
CWDs (post-M3), these need `$JARVIS_HOME/scripts/...` rewrites. Tracked
as a follow-up — non-blocking for M2 because until M3 flips, skills
still execute inside jarvis CWD where relative paths resolve.
