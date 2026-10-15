"""Run every case in cases.yaml against the live Maritime API.

Usage:
  .venv/bin/python tests/live_test.py              full run (creates and deletes one test agent)
  .venv/bin/python tests/live_test.py --dry-run    print the plan; no requests
  .venv/bin/python tests/live_test.py --only chat,exec_argv
                                                   run only these cases (plus create/teardown)
  .venv/bin/python tests/live_test.py --cleanup    delete leftover oas-test-* agents, nothing else

Safety rules:
  - Only agents whose name starts with "oas-test-" are ever modified or deleted.
  - The run stops before creating anything if a leftover test agent exists or the
    plan's agent limit would be exceeded.
  - Every oas-test-* agent the run created is deleted in a finally block, even
    when a case fails, and only after its name is checked again.
  - The API key and webhook tokens never appear in output or saved files.
"""
import argparse
import datetime as dt
import json
import re
import sys
import time

import requests
import yaml

from common import BASE_URL, TESTS, load_env, load_spec, redact, validate, write_json

TEST_PREFIX = "oas-test-"
AGENT_LIMIT = 3  # free plan
CSV = b"id,value\n1,alpha\n2,beta\n"


class Runner:
    def __init__(self, key, out):
        self.key = key
        self.out = out
        self.vars = {}
        self.secrets = [key]
        self.session = requests.Session()

    def fill(self, value):
        """Replace {VAR} placeholders in strings, lists and dicts."""
        if isinstance(value, str):
            for k, v in self.vars.items():
                value = value.replace("{" + k + "}", str(v))
            return value
        if isinstance(value, list):
            return [self.fill(v) for v in value]
        if isinstance(value, dict):
            return {k: self.fill(v) for k, v in value.items()}
        return value

    def request(self, method, path, auth="key", timeout=150, **kw):
        headers = kw.pop("headers", {}) or {}
        if auth == "key":
            headers["Authorization"] = f"Bearer {self.key}"
        elif auth == "bad":
            headers["Authorization"] = "Bearer mk_invalid000"
        elif auth == "raw":  # the key without the Bearer prefix
            headers["Authorization"] = self.key
        elif auth == "xapikey":  # the key in a header the docs don't mention
            headers["X-API-Key"] = self.key
        return self.session.request(method, BASE_URL + path, headers=headers, timeout=timeout, **kw)

    def mask(self, text):
        for s in self.secrets:
            if s:
                text = text.replace(s, "REDACTED")
        return text

    def run_case(self, case):
        """Send one case (or `repeat` copies of it). Returns (response, elapsed, path, detail)."""
        c = self.fill(case)
        if c.get("wait_before"):
            time.sleep(c["wait_before"])
        kw = {"headers": dict(c.get("headers") or {}), "params": c.get("query")}
        if "json" in c:
            kw["json"] = c["json"]
        if "body" in c:  # a raw body, sent as-is with its own content type
            kw["data"] = c["body"].encode()
            if c.get("content_type"):
                kw["headers"]["Content-Type"] = c["content_type"]
        if "file" in c or "form" in c:
            kw["data"] = c.get("form")
            if "file" in c:
                content = c["file_content"].encode() if "file_content" in c else CSV
                kw["files"] = {"file": (c["file"], content, "text/csv")}
        detail = ""
        start = time.time()
        if c.get("repeat"):
            # Send the request N times back to back; keep the first non-200 response (or the last one).
            tally, r = {}, None
            for _ in range(c["repeat"]):
                resp = self.request(c["method"], c["path"], auth=c.get("auth", "key"), timeout=c.get("timeout", 150), **kw)
                tally[resp.status_code] = tally.get(resp.status_code, 0) + 1
                if r is None or r.status_code == 200:
                    r = resp
            detail = "statuses: " + ", ".join(f"{k}x{v}" for k, v in sorted(tally.items()))
        else:
            r = self.request(c["method"], c["path"], auth=c.get("auth", "key"), timeout=c.get("timeout", 150), **kw)
        elapsed = time.time() - start

        for var, field in (c.get("save") or {}).items():
            if not r.ok:
                continue  # nothing to save from an error; dependent cases are skipped
            value = r.json()
            for part in str(field).split("."):
                value = value[int(part)] if part.isdigit() else value[part]
            self.vars[var] = value
            if var.startswith("TOKEN"):
                self.secrets.append(value)
        # Compare two saved values without printing them (tokens are redacted in captures).
        for var, other in (c.get("compare") or {}).items():
            same = self.vars.get(var) == self.vars.get(other)
            detail = f"{{{var}}} {'equals' if same else 'differs from'} {{{other}}}"

        # Save the capture in the same format as the 2026-10-03 baseline.
        head = f"HTTP/1.1 {r.status_code} {r.reason}\n" + "".join(f"{k}: {v}\n" for k, v in r.headers.items())
        (self.out / f"{c['name']}.headers").write_bytes(redact(head.encode(), self.secrets))
        (self.out / f"{c['name']}.body").write_bytes(redact(r.content, self.secrets))
        return r, elapsed, c["path"], detail

    def unresolved(self, case):
        """Name a placeholder the case still needs, or a var whose presence skips it."""
        if case.get("unless") and case["unless"] in self.vars:
            return f"{{{case['unless']}}} is set"
        m = re.search(r"\{([A-Z_0-9]+)\}", self.fill(case.get("path", "")))
        return f"{{{m.group(1)}}} was never saved" if m else None

    def poll(self, case):
        p = self.fill(case["poll"])
        deadline = time.time() + p.get("max", 300)
        while time.time() < deadline:
            value = self.request("GET", p["path"]).json().get(p["field"])
            if value == p["equals"]:
                return True, value
            time.sleep(p.get("every", 5))
        return False, value


def list_agents(runner):
    r = runner.request("GET", "/api/agents")
    r.raise_for_status()
    return r.json()


def delete_test_agent(runner, agent_id):
    """Delete one agent, but only if it still exists and its name has the test prefix."""
    r = runner.request("GET", f"/api/agents/{agent_id}")
    if r.status_code == 404:
        return None
    name = r.json().get("name", "")
    if not name.startswith(TEST_PREFIX):
        print(f"Refusing to delete {agent_id}: name {name!r} lacks the {TEST_PREFIX} prefix")
        return None
    return runner.request("DELETE", f"/api/agents/{agent_id}").status_code


def cleanup(runner):
    leftovers = [a for a in list_agents(runner) if a["name"].startswith(TEST_PREFIX)]
    for a in leftovers:
        r = runner.request("DELETE", f"/api/agents/{a['id']}")
        print(f"deleted {a['name']} ({a['id']}): {r.status_code}")
    if not leftovers:
        print("No leftover test agents.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cleanup", action="store_true")
    ap.add_argument("--only", help="comma-separated case names")
    args = ap.parse_args()

    cfg = yaml.safe_load((TESTS / "cases.yaml").read_text())
    cases = cfg["cases"]
    if args.only:
        keep = set(args.only.split(",")) | {"create", "wait_active", "files_list", "wh_token", "logs"}
        unknown = keep - {c["name"] for c in cases}
        if unknown:
            sys.exit(f"Unknown case(s): {', '.join(sorted(unknown))}")
        # Keep the cases that save variables other cases need, and the teardown.
        cases = [c for c in cases if c["name"] in keep or c.get("phase") == "teardown"]

    if args.dry_run:
        for c in cases:
            what = f"poll {c['poll']['path']} until {c['poll']['field']}={c['poll']['equals']}" if "poll" in c \
                else f"{c['method']:6} {c['path']}  -> {c['expect']}"
            print(f"{c['name']:20} {what}")
        print(f"\n{len(cases)} steps. No requests were made.")
        return

    key = load_env().get("MARITIME_API_KEY")
    if not key:
        sys.exit("MARITIME_API_KEY is missing from .env.local")

    stamp = dt.datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    out = TESTS / "runs" / stamp
    runner = Runner(key, out)
    runner.vars.update(cfg.get("vars", {}))
    runner.vars["DATE"] = dt.date.today().isoformat()

    if args.cleanup:
        cleanup(runner)
        return

    # Safety checks before creating anything.
    agents = list_agents(runner)
    leftovers = [a["name"] for a in agents if a["name"].startswith(TEST_PREFIX)]
    if leftovers:
        sys.exit(f"Leftover test agent(s): {', '.join(leftovers)}. Run with --cleanup first.")
    # Cases that save B create a second test agent while the first still exists.
    needed = 2 if any("B" in (c.get("save") or {}) for c in cases) else 1
    if len(agents) + needed > AGENT_LIMIT:
        sys.exit(f"The account has {len(agents)} agents (limit {AGENT_LIMIT}); no room for {needed} test agent(s).")
    before_ids = {a["id"] for a in agents}

    out.mkdir(parents=True)
    spec = load_spec()
    manifest, rows = [], []
    try:
        for case in cases:
            name = case["name"]
            if "poll" in case:
                ok, value = runner.poll(case)
                rows.append((name, "-", "-", "PASS" if ok else "FAIL", "" if ok else f"timed out; last value {value!r}", 0))
                print(f"{'PASS' if ok else 'FAIL'} {name}")
                if not ok and name == "wait_active":
                    raise RuntimeError("The test agent never became active")
                continue
            missing = runner.unresolved(case)
            if missing:
                rows.append((name, case["expect"], "-", "SKIP", missing, 0))
                print(f"SKIP {name}: {missing}")
                continue
            r, elapsed, path, detail = runner.run_case(case)
            problems = [detail] if detail else []
            ok_codes = case["expect"] if isinstance(case["expect"], list) else [case["expect"]]
            if r.status_code not in ok_codes:
                problems.append(f"expected {case['expect']}, got {r.status_code}")
            err = None
            if case.get("validate", True):
                err = validate(spec, case["method"], path, r.status_code, r.headers.get("content-type", ""), r.content)
                if err:
                    problems.append(runner.mask(err))
            verdict = "FAIL" if r.status_code not in ok_codes or err else "PASS"
            rows.append((name, case["expect"], r.status_code, verdict, "; ".join(problems), elapsed))
            manifest.append({"name": name, "method": case["method"], "path": path, "validate": case.get("validate", True)})
            print(f"{verdict} {name}: {r.status_code} ({elapsed:.1f}s)" + (f"  {problems}" if problems else ""))
            if name == "create" and r.status_code != 201:
                raise RuntimeError("Could not create the test agent")
    except Exception as e:
        print(f"Run stopped: {runner.mask(str(e))}")
        rows.append(("(run stopped)", "-", "-", "FAIL", runner.mask(str(e)), 0))
    finally:
        # Delete every test agent this run created, including any a validation case created by accident.
        for a in list_agents(runner):
            if a["id"] not in before_ids and a["name"].startswith(TEST_PREFIX):
                status = delete_test_agent(runner, a["id"])
                if status:
                    print(f"Cleanup: deleted test agent {a['name']} ({a['id']}): {status}")
        write_json(out / "manifest.json", manifest)
        write_report(out, rows, runner)

    failed = [r for r in rows if r[3] == "FAIL"]
    print(f"\n{len(rows) - len(failed)} passed, {len(failed)} failed. Report: {out / 'report.md'}")
    sys.exit(1 if failed else 0)


def write_report(out, rows, runner):
    notes = {c["name"]: c.get("note", "") for c in yaml.safe_load((TESTS / "cases.yaml").read_text())["cases"]}
    lines = [
        f"# Live run {out.name}",
        "",
        f"Template: `{runner.vars.get('TEMPLATE')}`. Volume root: `{runner.vars.get('R', '?')}`.",
        "",
        "| Case | Expected | Got | Result | Detail | Time | Note |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, exp, got, verdict, problem, elapsed in rows:
        lines.append(f"| {name} | {exp} | {got} | {verdict} | {problem.replace('|', '/')} | {elapsed:.1f}s | {notes.get(name, '')} |")
    (out / "report.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
