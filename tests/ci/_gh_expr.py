"""Evaluator for the subset of GitHub Actions expression syntax the workflow guards use.

Shared by the concurrency guards (test_agent_dispatch_concurrency_guard.py for
lane.yml, test_code_review_concurrency_guard.py for code-review.yml). They evaluate
the expressions actually written in the workflow file, so a rewrite that keeps the
behaviour passes and one that breaks it fails.
"""

from __future__ import annotations

import re

import pytest

_TOKEN = re.compile(
    r"""
    \s*(?:
        (?P<string>'(?:[^']|'')*')
      | (?P<number>\d+)
      | (?P<op>&&|\|\||==|!=|!|\(|\)|,)
      | (?P<name>[A-Za-z_][A-Za-z0-9_.-]*)
    )
    """,
    re.VERBOSE,
)


def _gh_format(template: str, *args: object) -> str:
    for i, arg in enumerate(args):
        template = template.replace("{%d}" % i, str(arg))
    return template


def evaluate_expression(expr: str, context: dict[str, object]) -> object:
    """Evaluate one GitHub Actions expression (the text inside ``${{ }}``).

    Covers string/number literals, dotted context lookups, ``&& || == != !``,
    parentheses and ``format()``. ``&&``/``||`` return an operand rather than a
    boolean in both GitHub's language and Python's, which is what makes the
    ``cond && a || b`` idiom translate directly. Anything outside the subset
    fails loudly: extend this function, don't route around it.
    """
    out: list[str] = []
    pos = 0
    expr = expr.strip()
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m:
            pytest.fail(f"unsupported expression syntax at {expr[pos:]!r}")
        pos = m.end()
        if m.group("string"):
            out.append(repr(m.group("string")[1:-1].replace("''", "'")))
        elif m.group("number"):
            out.append(m.group("number"))
        elif m.group("op"):
            out.append({"&&": "and", "||": "or", "!": "not"}.get(m.group("op"), m.group("op")))
        elif m.group("name") == "format":
            out.append("format")
        else:
            name = m.group("name")
            if name not in context:
                pytest.fail(f"expression reads {name!r}, which this guard does not model")
            out.append(repr(context[name]))
    return eval(" ".join(out), {"__builtins__": {}, "format": _gh_format})


def evaluate(value: object, context: dict[str, object]) -> object:
    """Render a workflow value the way Actions does.

    A value that is exactly one ``${{ }}`` keeps its type (needed for the
    boolean ``cancel-in-progress``); otherwise each ``${{ }}`` is interpolated
    into the surrounding text.
    """
    if not isinstance(value, str):
        return value
    whole = re.fullmatch(r"\s*\$\{\{(.*)\}\}\s*", value, re.DOTALL)
    if whole and "${{" not in whole.group(1):
        return evaluate_expression(whole.group(1), context)
    return re.sub(
        r"\$\{\{(.*?)\}\}",
        lambda m: str(evaluate_expression(m.group(1), context)),
        value,
        flags=re.DOTALL,
    )
