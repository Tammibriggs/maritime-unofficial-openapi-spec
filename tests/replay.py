"""Validate a folder of captured responses against maritime_openapi.yaml.

Usage: .venv/bin/python tests/replay.py [CAPTURE_DIR]   (default: tests/baseline/captures)

Each folder holds <name>.headers / <name>.body pairs and a manifest.json that
gives each capture's method and path. Exits 1 if any capture fails.
"""
import json
import sys
from pathlib import Path

from common import TESTS, load_spec, read_capture, validate


def replay(folder):
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_text())
    spec = load_spec()
    results = []
    for entry in manifest:
        if not entry.get("validate", True):
            continue
        status, ctype, body = read_capture(folder, entry["name"])
        err = validate(spec, entry["method"], entry["path"], status, ctype, body)
        results.append((entry["name"], status, err))
    return results


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else TESTS / "baseline" / "captures"
    results = replay(folder)
    failed = [r for r in results if r[2]]
    for name, status, err in results:
        print(f"{'FAIL' if err else 'OK  '} {status} {name}" + (f"\n     {err}" if err else ""))
    print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
