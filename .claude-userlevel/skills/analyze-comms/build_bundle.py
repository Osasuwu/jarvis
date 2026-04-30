"""Build curated bundle for LLM pattern analysis.

For each corrective/affirmative user msg, includes the immediately preceding assistant text.
Plus a stratified sample of neutral user msgs for style characterization.

This file CONTAINS quotes — must NOT be committed to a public repo. Upload to private GDrive.
"""
from __future__ import annotations
import json, re, random, sys
from collections import defaultdict
from pathlib import Path

NEG_PATTERNS = [
    r"\bне\s+так\b", r"\bне\s+то\b", r"\bстоп\b", r"\bнет,?\s", r"\bпочему\s+ты\b",
    r"\bопять\b", r"\bя\s+же\s+(говорил|сказал|просил)\b", r"\bты\s+не\s+поня",
    r"\bперестань\b", r"\bхватит\b",
    r"\bno,?\s", r"\bstop\b", r"\bdon't\b", r"\bwhy\s+are\s+you\b",
    r"\bagain\b", r"\bnot\s+what\s+i\b",
]
NEG_RE = re.compile("|".join(NEG_PATTERNS), re.I)
POS_PATTERNS = [
    r"\bотлично\b", r"\bкруто\b", r"\bтак\s+и\s+делай\b", r"\bправильно\b",
    r"\bда,?\s+именно\b", r"\bперфект", r"\bхорошо\b",
    r"\bperfect\b", r"\bexactly\b", r"\bnice\b", r"\bgreat\b",
]
POS_RE = re.compile("|".join(POS_PATTERNS), re.I)


def truncate(s: str, n: int = 600) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[:n] + " […]"


def main(src_path: str, out_path: str):
    src = Path(src_path)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    recs = [json.loads(l) for l in open(src, encoding="utf-8")]
    by_sess = defaultdict(list)
    for r in recs:
        by_sess[r["sess"]].append(r)
    real = {s: msgs for s, msgs in by_sess.items() if sum(1 for m in msgs if m["role"] == "u") >= 3}

    correctives, affirmatives, style_samples = [], [], []
    for s, msgs in real.items():
        msgs.sort(key=lambda m: m["ts"])
        for i, m in enumerate(msgs):
            if m["role"] != "u":
                continue
            prev_a = next((msgs[j] for j in range(i - 1, -1, -1) if msgs[j]["role"] == "a"), None)
            if NEG_RE.search(m["text"]):
                correctives.append((prev_a, m))
            elif POS_RE.search(m["text"]):
                affirmatives.append((prev_a, m))
        u_neutral = [m for m in msgs if m["role"] == "u"
                     and not NEG_RE.search(m["text"]) and not POS_RE.search(m["text"])]
        random.seed(s)
        style_samples.extend(random.sample(u_neutral, min(3, len(u_neutral))))

    # chronological order for narrative flow
    correctives.sort(key=lambda x: x[1]["ts"])
    affirmatives.sort(key=lambda x: x[1]["ts"])

    with out.open("w", encoding="utf-8") as f:
        f.write("# Communication patterns bundle\n\n")
        f.write(f"{len(real)} interactive sessions, "
                f"{sum(1 for s in real.values() for m in s if m['role']=='u')} user msgs.\n\n")

        f.write(f"## Corrective moments ({len(correctives)})\n\n")
        f.write("Format: assistant said X → user pushed back Y. Look for triggers.\n\n")
        for prev_a, u in correctives:
            f.write(f"### [{u['ts'][:16]}] sess {u['sess'][:8]}\n")
            f.write(f"**A:** {truncate(prev_a['text'], 500) if prev_a else '(none)'}\n\n")
            f.write(f"**U:** {truncate(u['text'], 500)}\n\n---\n\n")

        f.write(f"\n## Affirmative moments ({len(affirmatives)})\n\n")
        for prev_a, u in affirmatives:
            f.write(f"### [{u['ts'][:16]}] sess {u['sess'][:8]}\n")
            if prev_a:
                f.write(f"**A:** {truncate(prev_a['text'], 400)}\n\n")
            f.write(f"**U:** {truncate(u['text'], 300)}\n\n---\n\n")

        f.write(f"\n## Neutral user style samples ({len(style_samples)})\n\n")
        for u in style_samples:
            f.write(f"- [{u['ts'][:10]} {u['sess'][:8]}] {truncate(u['text'], 350)}\n")

    print(f"out: {out}  size: {out.stat().st_size / 1024:.1f} KB")
    print(f"correctives: {len(correctives)}  affirmatives: {len(affirmatives)}  style: {len(style_samples)}")


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "comms_extract.jsonl"
    out = sys.argv[2] if len(sys.argv) > 2 else "comms_bundle.md"
    main(src, out)
