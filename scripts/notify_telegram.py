"""Owner notification via the Telegram Bot API — the replacement transport for
the demolished ``agents/notify.py`` (#1802/#1868), used by ``/weekly-release``
Step 5 (#1761).

Why it loads ``.env`` itself: a scheduled-task (routine) session is a bare
``claude`` process — nothing sources the repo's ``.env`` for it, so
``TELEGRAM_BOT_TOKEN`` was never in the environment and every routine
notification silently no-opped (#1761). This module walks up from its own
location to the first ``.env`` (in a worktree that is the main checkout's
``.env``) and fills only keys the process environment doesn't already set.

Fails loud: missing credentials or a non-OK API reply exit non-zero with the
missing key *names* on stderr — never values, and the bot token is scrubbed
from any error text.

Usage::

    python -m scripts.notify_telegram "Published release: o/r v0.5.0" "https://..."
"""

from __future__ import annotations

import shutil  # TEMP-1911 violation
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path

TELEGRAM_API = "https://api.telegram.org"
TOKEN_KEY = "TELEGRAM_BOT_TOKEN"
# Same key the old agents/notify.py read; TELEGRAM_CHAT_ID accepted as an alias.
CHAT_KEYS = ("TELEGRAM_ALLOW_USER_ID", "TELEGRAM_CHAT_ID")

PostFn = Callable[[str, bytes], dict]


class NotifyError(RuntimeError):
    pass


def parse_env_file(text: str) -> dict[str, str]:
    """Minimal ``.env`` parser: ``KEY=value`` lines, optional ``export``
    prefix, surrounding quotes stripped, ``#`` comment lines skipped."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def find_env_file(start: Path) -> Path | None:
    for directory in [start, *start.parents]:
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


def resolve_env(environ: Mapping[str, str], env_file: Path | None) -> dict[str, str]:
    """Process environment wins; ``.env`` only fills keys that are unset."""
    merged = parse_env_file(env_file.read_text(encoding="utf-8")) if env_file else {}
    merged.update({k: v for k, v in environ.items() if v})
    return merged


def credentials(env: Mapping[str, str]) -> tuple[str, str]:
    token = (env.get(TOKEN_KEY) or "").strip()
    chat_id = next((env[k].strip() for k in CHAT_KEYS if (env.get(k) or "").strip()), "")
    missing = [
        name for name, val in ((TOKEN_KEY, token), ("/".join(CHAT_KEYS), chat_id)) if not val
    ]
    if missing:
        raise NotifyError(f"telegram credentials not set: {', '.join(missing)}")
    return token, chat_id


def _urllib_post(url: str, data: bytes) -> dict:
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return json.loads(exc.read().decode("utf-8") or "{}")


def send(subject: str, body: str, env: Mapping[str, str], post: PostFn = _urllib_post) -> None:
    token, chat_id = credentials(env)
    text = f"{subject}\n\n{body}".strip()
    payload = json.dumps(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    ).encode("utf-8")
    try:
        reply = post(f"{TELEGRAM_API}/bot{token}/sendMessage", payload)
    except Exception as exc:  # network errors carry the URL, i.e. the token
        raise NotifyError(f"{type(exc).__name__}: {str(exc).replace(token, '***')}") from None
    if not reply.get("ok"):
        raise NotifyError(f"telegram API refused: {reply.get('description', 'no description')}")


def main(argv: list[str]) -> int:
    if not argv or len(argv) > 2:
        print('usage: python -m scripts.notify_telegram "<subject>" ["<body>"]', file=sys.stderr)
        return 2
    env = resolve_env(os.environ, find_env_file(Path(__file__).resolve().parent))
    try:
        send(argv[0], argv[1] if len(argv) > 1 else "", env)
    except NotifyError as exc:
        print(f"notify_telegram: FAILED — {exc}", file=sys.stderr)
        return 1
    print("notify_telegram: sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
