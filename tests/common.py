"""Shared helpers for live_test.py, replay.py and drift.py."""
import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
SPEC_PATH = ROOT / "maritime_openapi.yaml"
BASE_URL = "https://api.maritime.sh"

# The 18 documented operations this project covers.
IN_SCOPE = [
    ("get", "/health"),
    ("get", "/api/templates"),
    ("get", "/api/agents"),
    ("post", "/api/agents"),
    ("get", "/api/agents/{agent_id}"),
    ("delete", "/api/agents/{agent_id}"),
    ("post", "/api/agents/{agent_id}/chat"),
    ("post", "/api/agents/{agent_id}/exec"),
    ("get", "/api/agents/{agent_id}/logs"),
    ("get", "/api/agents/{agent_id}/files/list"),
    ("get", "/api/agents/{agent_id}/files/download"),
    ("post", "/api/agents/{agent_id}/files/upload"),
    ("put", "/api/agents/{agent_id}/files/write"),
    ("post", "/api/agents/{agent_id}/files/mkdir"),
    ("post", "/api/agents/{agent_id}/files/move"),
    ("delete", "/api/agents/{agent_id}/files/delete"),
    ("post", "/api/webhooks/{agent_id}"),
    ("get", "/api/webhooks/{agent_id}/token"),
]


def load_env():
    """Read KEY=value pairs from .env.local without exporting them."""
    env = {}
    path = ROOT / ".env.local"
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    return env


def load_spec():
    from openapi_core import OpenAPI
    return OpenAPI.from_dict(yaml.safe_load(SPEC_PATH.read_text()))


def read_capture(folder, name):
    """Return (status, content_type, body bytes) for a saved capture."""
    folder = Path(folder)
    lines = (folder / f"{name}.headers").read_text(errors="replace").splitlines()
    # Skip interim responses such as "HTTP/1.1 100 Continue" written by curl.
    status_lines = [l for l in lines if l.startswith("HTTP/")]
    status = int(status_lines[-1].split()[1])
    ctype = ""
    for l in lines:
        if l.lower().startswith("content-type:"):
            ctype = l.split(":", 1)[1].strip()
    return status, ctype, (folder / f"{name}.body").read_bytes()


def validate(spec, method, path, status, ctype, body):
    """Validate one response against the spec. Returns None if it passes, else an error string."""
    from openapi_core.testing import MockRequest, MockResponse

    mimetype = ctype.split(";")[0].strip() or "application/json"
    req = MockRequest(BASE_URL, method.lower(), path)
    resp = MockResponse(body, status_code=status, content_type=mimetype)
    try:
        spec.validate_response(req, resp)
        return None
    except Exception as e:  # report the root cause, which is far more useful than the wrapper
        cause = e.__cause__ or e
        detail = str(cause)
        if hasattr(cause, "schema_errors"):
            detail = "; ".join(str(x.message) for x in cause.schema_errors)
        return f"{type(e).__name__}: {detail}"[:500]


def redact(data: bytes, secrets):
    for s in secrets:
        if s:
            data = data.replace(s.encode(), b"REDACTED")
    # Webhook tokens in URLs or JSON, even ones we didn't capture as variables.
    data = re.sub(rb'("token"\s*:\s*")[^"]+', rb"\1wht_REDACTED", data)
    data = re.sub(rb"(token=)[A-Za-z0-9_.\-]+", rb"\1wht_REDACTED", data)
    return data


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2) + "\n")
