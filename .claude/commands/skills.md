---
name: skills
description: "List all available skills and commands with descriptions"
---

Run this command and present the output as a formatted table:

```bash
echo "=== SKILLS (model-invoked) ===" && \
for dir in ~/.claude/skills/*/; do
  name=$(basename "$dir")
  desc=$(grep -m1 '^description:' "$dir/SKILL.md" 2>/dev/null | sed 's/^description: *"//' | sed 's/"$//' | sed "s/^description: *'//;s/'$//")
  printf "%-20s %s\n" "/$name" "${desc:-(no description)}"
done && \
echo "" && echo "=== COMMANDS (user-invoked) ===" && \
for f in ~/.claude/commands/*.md; do
  name=$(basename "$f" .md)
  desc=$(grep -m1 '^description:' "$f" 2>/dev/null | sed 's/^description: *"//' | sed 's/"$//' | sed "s/^description: *'//;s/'$//")
  printf "%-20s %s\n" "/$name" "${desc:-(no description)}"
done
```

Format the output as two markdown tables: Skills and Commands.
