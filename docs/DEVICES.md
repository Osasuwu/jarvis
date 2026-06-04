# DEVICES.md — per-device paths & SSH map

Cross-device reference so an agent (or human) on any machine knows where each
project lives on every other machine, and how to reach it over SSH. All three
boxes are on the same Tailscale tailnet (IPs are stable `100.x` tailnet
addresses).

**This is reference info, not state** — update it only when a device's paths,
username, or tailnet IP actually change. Per-machine generated config lives in
`config/device.json` (gitignored); this file is the *shared* view.

## Device matrix

| Device | Role | Tailnet IP | SSH user | Home | Repos root |
|---|---|---|---|---|---|
| **Workshop** (`VividFormsPC4`) | Always-on server / scheduled tasks (see `project_workshop_pc_server`) | `100.105.131.44` | `PC4_v` | `C:\Users\PC4_v` | `D:\Github` |
| **laptop** | Mobile dev | `100.98.114.113` | `petrk` | `C:\Users\petrk` | `C:\Users\petrk\Github` |
| **home** | Home desktop | `100.114.15.71` | `petrk` | `C:\Users\petrk` | `C:\Users\petrk\Github` |

## Project paths per device

| Project | Workshop | laptop | home |
|---|---|---|---|
| jarvis | `D:\Github\jarvis` | `C:\Users\petrk\Github\jarvis` | `C:\Users\petrk\Github\jarvis` |
| redrobot | `D:\Github\redrobot` | `C:\Users\petrk\Github\redrobot` | `C:\Users\petrk\Github\redrobot` |
| `~/.claude` (installed) | `C:\Users\PC4_v\.claude` | `C:\Users\petrk\.claude` | `C:\Users\petrk\.claude` |

Rule of thumb: **Workshop keeps repos on `D:\Github`; laptop & home use
`C:\Users\petrk\Github`.** Only Workshop differs from the `~\Github` pattern.

### Toolchain locations
| Tool | Workshop | laptop | home |
|---|---|---|---|
| git | `C:\Program Files\Git\cmd\git.exe` | same | same |
| python | system PATH | `C:\Users\petrk\AppData\Local\Programs\Python\Python313\python.exe` | `C:\Python314\python.exe` |

## SSH

`~/.ssh/config` aliases (define the same block on each device, swapping out the
local one):

```
Host workshop
    HostName 100.105.131.44
    User PC4_v
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes

Host laptop
    HostName 100.98.114.113
    User petrk
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes

Host home
    HostName 100.114.15.71
    User petrk
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
```

### Running commands remotely — gotcha
The **default SSH shell on all three Windows boxes is `cmd.exe`**, not
PowerShell or bash. `;` is not a command separator there. To run a PowerShell
script remotely without quoting hell, base64-encode it as UTF-16LE and use
`-EncodedCommand`:

```bash
B64=$(python -c 'import base64;print(base64.b64encode(open("script.ps1","rb").read().decode().encode("utf-16-le")).decode())')
ssh home "powershell -NoProfile -EncodedCommand $B64"
```

(Plain `ssh home "powershell -Command \"...\""` mangles nested quotes through
cmd → avoid it.) Output may be prefixed with a `#< CLIXML` progress banner and a
post-quantum-KEX warning on stderr — filter both out.

## Sync / maintenance per device

Each device independently `git pull`s and runs the installer. After pulling
jarvis:

```powershell
cd <jarvis path for this device>
git pull --ff-only
.\install.ps1 -Apply          # propagates SOUL/CLAUDE.md/skills/MCP into ~/.claude
```

`install.ps1 -Apply` is idempotent and writes a timestamped backup under
`~/.claude.backup-*`. Source of truth for the user-level `~/.claude/CLAUDE.md`
mirror is `<jarvis>/.claude-userlevel/CLAUDE.md` — never edit the mirror.
