# AI Hero skills — attribution

The following skills are imported from **Matt Pocock's** [`mattpocock/skills`](https://github.com/mattpocock/skills) repository (MIT, 2026):

| Skill | Original path | Adaptation |
|---|---|---|
| `caveman` | `productivity/caveman` | as-is |
| `diagnose` | `engineering/diagnose` | as-is |
| `grill-me` | `productivity/grill-me` | as-is |
| `grill-with-docs` | `engineering/grill-with-docs` | as-is |
| `improve-codebase-architecture` | `engineering/improve-codebase-architecture` | as-is (refs CONTEXT.md / docs/adr/ — create lazily) |
| `tdd` | `engineering/tdd` | as-is (full bundle: deep-modules, interface-design, mocking, refactoring, tests) |
| `to-issues` | `engineering/to-issues` | replaced `/setup-matt-pocock-skills` ref → "see project CLAUDE.md" |
| `to-prd` | `engineering/to-prd` | same |
| `triage` | `engineering/triage` | same |
| `write-a-skill` | `productivity/write-a-skill` | as-is |
| `zoom-out` | `engineering/zoom-out` | as-is |

## Why imported

Pocock's philosophy aligns with Jarvis's: real engineering > vibe coding, evals as unit tests, smart zone (~100K tokens) discipline, vertical slices, deep modules, TDD as feedback loop. See [`docs/research-aihero-principles.md`](../../docs/research-aihero-principles.md) for full mapping.

His repo is explicitly designed for fork-and-adapt: *"These skills are designed to be small, easy to adapt, and composable. … Hack around with them. Make them your own."*

## Update workflow

When Matt updates a skill upstream:

```bash
gh repo clone mattpocock/skills /tmp/pocock-skills
diff -r /tmp/pocock-skills/skills/<category>/<name>/ \
        .claude-userlevel/skills/<name>/
```

Re-apply our `setup-matt-pocock-skills` adaptations on top.

## License

All upstream content is MIT (Copyright (c) 2026 Matt Pocock). Original LICENSE: https://github.com/mattpocock/skills/blob/main/LICENSE.
