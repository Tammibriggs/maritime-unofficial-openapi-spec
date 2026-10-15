"""Check whether Maritime's official spec or REST API docs page changed since the baseline.

Usage:
  .venv/bin/python tests/drift.py                    compare live sources with tests/baseline/
  .venv/bin/python tests/drift.py --update-baseline  after reviewing, make the live sources the new baseline

Needs no API key. Writes tests/drift/latest.md and exits 1 if anything changed.
"""
import argparse
import datetime as dt
import difflib
import json
import sys
from html.parser import HTMLParser
from pathlib import Path

import requests

from common import IN_SCOPE, TESTS

SPEC_URL = "https://api.maritime.sh/openapi.json"
DOCS_URL = "https://maritime.sh/docs/api"
BASE = TESTS / "baseline"
WATCHED_PREFIXES = ("/health", "/api/templates", "/api/agents", "/api/webhooks")


class _Text(HTMLParser):
    """Strip HTML to text, one line per block element, skipping scripts and styles."""
    BLOCKS = {"p", "div", "li", "pre", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br", "section", "article", "code", "td", "th"}

    def __init__(self):
        super().__init__()
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(html):
    p = _Text()
    p.feed(html)
    lines = (" ".join(l.split()) for l in "".join(p.parts).splitlines())
    return "\n".join(l for l in lines if l) + "\n"


def resolve(node, schemas, seen=()):
    """Inline $refs so a change to a referenced schema shows up under the operation."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if ref and ref.startswith("#/components/schemas/"):
            name = ref.rsplit("/", 1)[-1]
            if name in seen:
                return {"$ref": name}
            return {"$schema_name": name, **resolve(schemas.get(name, {}), schemas, seen + (name,))}
        return {k: resolve(v, schemas, seen) for k, v in node.items()}
    if isinstance(node, list):
        return [resolve(v, schemas, seen) for v in node]
    return node


def operation(spec, method, path):
    op = spec.get("paths", {}).get(path, {}).get(method)
    if op is None:
        return None
    schemas = spec.get("components", {}).get("schemas", {})
    keep = {k: op.get(k) for k in ("summary", "description", "parameters", "requestBody", "responses")}
    return resolve(keep, schemas)


def watched_ops(spec):
    return {
        f"{m.upper()} {p}"
        for p, ms in spec.get("paths", {}).items() if p.startswith(WATCHED_PREFIXES)
        for m in ms if m in ("get", "post", "put", "patch", "delete")
    }


def diff(a, b, name_a, name_b, limit=80):
    lines = list(difflib.unified_diff(a.splitlines(), b.splitlines(), name_a, name_b, lineterm="", n=2))
    more = len(lines) - limit
    return "\n".join(lines[:limit]) + (f"\n... {more} more lines" if more > 0 else "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update-baseline", action="store_true")
    args = ap.parse_args()

    new_spec_raw = requests.get(SPEC_URL, timeout=60).text
    new_html = requests.get(DOCS_URL, timeout=60).text
    new_spec = json.loads(new_spec_raw)
    new_text = html_to_text(new_html)

    if args.update_baseline:
        (BASE / "openapi.json").write_text(new_spec_raw)
        (BASE / "docs_api.html").write_text(new_html)
        (BASE / "docs_api.txt").write_text(new_text)
        print("Baseline updated from the live spec and docs page.")
        return

    old_spec = json.loads((BASE / "openapi.json").read_text())
    old_text = (BASE / "docs_api.txt").read_text()
    changes = []

    old_v, new_v = old_spec.get("info", {}).get("version"), new_spec.get("info", {}).get("version")
    header = [f"# Drift check {dt.datetime.now():%Y-%m-%d %H:%M}", "",
              f"Official spec version: baseline `{old_v}`, live `{new_v}`.", ""]

    # 1. The 18 in-scope operations
    for method, path in IN_SCOPE:
        old, new = operation(old_spec, method, path), operation(new_spec, method, path)
        label = f"{method.upper()} {path}"
        if new is None:
            changes.append(f"## {label}\n\nRemoved from the official spec.")
        elif old is None:
            changes.append(f"## {label}\n\nAdded to the official spec (it wasn't in the baseline).")
        elif old != new:
            d = diff(json.dumps(old, indent=1, sort_keys=True), json.dumps(new, indent=1, sort_keys=True), "baseline", "live")
            changes.append(f"## {label}\n\nChanged in the official spec:\n\n```diff\n{d}\n```")

    # 2. Operations added or removed near the in-scope ones
    old_ops, new_ops = watched_ops(old_spec), watched_ops(new_spec)
    added, removed = sorted(new_ops - old_ops), sorted(old_ops - new_ops)
    if added or removed:
        body = "".join(f"- Added: `{o}`\n" for o in added) + "".join(f"- Removed: `{o}`\n" for o in removed)
        changes.append(f"## Operations added or removed (agents, webhooks, templates, health)\n\n{body}")

    # 3. The docs page
    if old_text != new_text:
        d = diff(old_text, new_text, "baseline docs page", "live docs page", limit=150)
        changes.append(f"## REST API docs page\n\nThe page text changed:\n\n```diff\n{d}\n```")

    summary = (f"**{len(changes)} change(s) found.** Review them, re-run the live tests, then update the "
               "baseline with `--update-baseline`." if changes else "**No changes** since the baseline.")
    report = "\n".join(header + [summary, ""] + [c + "\n" for c in changes])
    out = TESTS / "drift" / "latest.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report)
    print(report if len(report) < 4000 else report[:4000] + f"\n... (full report in {out})")
    sys.exit(1 if changes else 0)


if __name__ == "__main__":
    main()
