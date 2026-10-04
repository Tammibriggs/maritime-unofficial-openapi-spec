# Maritime Agents API: test coverage

This file lists every live test run against the 18 operations in [`maritime_openapi.yaml`](maritime_openapi.yaml), and what is still untested. Each test is a case in [`tests/cases.yaml`](tests/cases.yaml); the case name is in brackets so you can find its capture in `tests/runs/<timestamp>/<case>.body`.

| Run | Steps | Result |
|---|---|---|
| 2026-10-03, first pass (`curl`) | About 60 calls | Baseline captures in `tests/baseline/captures/` |
| 2026-10-03, re-run | 70 | All passed |
| 2026-10-04, extended run (`tests/runs/2026-10-04T01-44-12`) | 199 | 190 passed, 9 failed. All 9 were new behaviour; the spec now matches them |
| 2026-10-04, follow-up (`tests/runs/2026-10-04T01-51-34`) | 14 | 13 passed; the duplicate-name case returned 409, now in the spec |
| 2026-10-08, follow-up (`tests/runs/2026-10-08T18-21-59-followup`) | 14 | Verified wake-limit 429 unenforced (200), file invalid JSON (422), scoped keys (401), revoked/expired keys (401), and create auth |

`tests/cases.yaml` has 200 steps: 70 from 2026-10-03 and 130 added on 2026-10-04. The 2026-10-08 follow-up resolved 5 previously untested edge cases. Every captured response validates against the spec. In the tables below, **New** marks tests added on 2026-10-04, and **Follow-up** marks tests from 2026-10-08.

## Checks that apply to every endpoint

| Test | Result | New |
|---|---|---|
| No API key on list agents [`agents_list_noauth`] | `403 Not authenticated` | |
| Invalid key on list agents [`agents_list_badkey`] | `401 Invalid token` | |
| No key on 12 more authenticated operations: get, delete, chat, exec, logs and the 7 file endpoints [`noauth_*`] | `403` on every one | New |
| Invalid key on the same 12, plus the webhook token [`badkey_*`] | `401` on every one | New |
| No key on create agent [`missing_create_agent`] | `403 Not authenticated` | Follow-up |
| Invalid key on create agent [`badkey_create_agent`] | `401 Invalid token` | Follow-up |
| Revoked API key on list agents [`revoked_list_agents`] | `401 Invalid token` | Follow-up |
| Expired API key on list agents [`expired_list_agents`] | `401 Invalid token` | Follow-up |
| Key with `scopes: ["deploy"]` on core agent endpoints [`scope_*`] | `401 Invalid token` (core routes reject scoped keys) | Follow-up |
| Key sent without `Bearer` [`auth_raw`] | `403` (treated as missing) | New |
| Key sent in `X-API-Key` [`auth_xapikey`] | `403` (treated as missing) | New |
| Invalid key on health, templates and webhook invoke [`health_badkey`, `templates_badkey`, `wh_badkey`] | Ignored | New |
| Unknown agent ID on every agent route [`*_404`, `*_404z`] | `404 Agent … not found` on every one | Partly new |
| Malformed (non-UUID) agent ID [`get_badid`] | `404`, not `422` | |
| Wrong method on 4 routes [`m405_*`] | `405`; the `Allow` header can be incomplete (`PUT /api/agents` → `Allow: GET`) | New |
| CORS preflight from `https://example.com` [`cors_preflight`] | `400 Disallowed CORS origin` | New |
| Plain GET with an `Origin` header [`cors_simple`] | No `Access-Control-Allow-Origin` header | New |
| Unknown query parameters (`limit`, `offset` on list agents) [`agents_list_q`] | Ignored; the full list comes back | New |
| Response fields not declared in the spec (offline audit of all captures) | None, apart from the free-form `input` echoed in `422`s | New |

## Health and templates

| Test | Result | New |
|---|---|---|
| `GET /health` without auth [`health`] | `200` | |
| `GET /api/templates` without auth [`templates`] | `200`; six templates | |

## Agents

| Test | Result | New |
|---|---|---|
| List agents [`agents_list`] | `200`, a bare array | |
| Create with `{name, templateId: zeroclaw}` [`create`] | `201`, `status: deploying` | |
| Create without `name` [`create_422`] | `422` | |
| Create with `{}` [`create_empty`] | `422` for `name` only (`templateId` is optional) | New |
| Create with a numeric `templateId` [`create_tmpl_int`] | `422` | New |
| Create with invalid JSON [`create_badjson`] | `422`, `json_invalid` | New |
| Create with a form-encoded body [`create_form`] | `422` | New |
| Create with an unknown `templateId` [`create_badtemplate`] | **`201`**: a `framework: custom` agent that takes a seat | New |
| Create a fourth agent on the free plan (side effect of the case above) | **`402`**, `code: seat_limit` | New |
| Create with a name already in use [`create_dup`] | **`409`** | New |
| Create with a 278-character name [`create_longname`] | `201` | New |
| Get while deploying, active and sleeping [`get_deploying`, `get`, `get_sleeping`] | `200`; the same 34 fields in each state | Partly new |
| Poll until active [`wait_active`] | About 25 s | |
| Delete [`delete`], get after delete, delete again | `204`, then `404` twice | |
| Delete 0.5 s after create, while deploying [`delete_deploying`, `delete_long`] | `204` | New |

## Chat

| Test | Result | New |
|---|---|---|
| A message [`chat`] | `200 {"response": …}` in about 3 s | |
| Empty body [`chat_422`] | `422` | |
| Two messages sharing a `conversation_id` [`chat_t2a`, `chat_t2b`] | Accepted; ZeroClaw didn't recall the first | |
| The docs page's example, "summarize today" [`chat_docs`] | `200` | New |
| `message: ""` [`chat_empty`] | `200`; the agent replied | New |
| Unicode and emoji [`chat_unicode`] | `200`; echoed correctly | New |
| An unknown extra field [`chat_extra`] | Ignored | New |
| Numeric `conversation_id` [`chat_conv_int`] | `422` | New |
| Chat to a sleeping agent [`chat_wake`] | Woke it; replied in 3.5 s | New |
| Chat with OpenClaw without `OPENAI_API_KEY` | `200`; Maritime proxy injected `mllm_` key and replied in 9.3 s | New |
| Chat with Claude Code without `ANTHROPIC_API_KEY` | `200`; returned in 1.0 s with advisory response noting missing key | New |
| Chat to sleeping agent while another is active on Free plan | **`200`** in 0.56 s with advisory response string noting 1 machine awake cap; agent remained sleeping | Follow-up |

## Exec

| Test | Result | New |
|---|---|---|
| Argv array; shell string with stderr and exit 3 [`exec_argv`, `exec_str`] | `200`; stderr merged into stdout; exit 3 still `200` | |
| Empty body [`exec_missing`] | `400` | |
| `timeout: 3` vs `timeoutS: 3` on `sleep 8` [`exec_timeout`, `exec_timeoutS`] | `timeout` → `502` in 3.8 s; `timeoutS` ignored | |
| `timeout: 500` [`exec_toobig`] | Accepted | |
| The docs page's example (`ls -la /data`, `timeout: 30`) [`exec_docs`] | `200` | New |
| 300,000 bytes of output [`exec_cap`] | **Capped**: `[output truncated]\n` plus the last 262,144 bytes | New |
| `sleep 125` with `timeout: 500` [`exec_clamp`] | **`502` after 120.6 s**: clamped to 120 s | New |
| `command: ""` and `command: []` [`exec_empty_str`, `exec_empty_list`] | `400` | New |
| A binary that doesn't exist [`exec_nobin`] | `200`, exit code `127` | New |
| `timeout` of `0`, `1.5` and `"5"` [`exec_t0`, `exec_tfloat`, `exec_tstr`] | Ran normally | New |
| `timeout: -1` [`exec_tneg`] | `502` at once | New |
| `whoami; pwd; echo $HOME; id` [`exec_whoami`] | `root`, cwd `/`, `HOME=/` | New |
| An unknown extra field [`exec_extra`] | Ignored | New |
| Invalid JSON [`exec_badjson`] | `422` array (not the hand-validated `400`) | New |

## Logs

| Test | Result | New |
|---|---|---|
| `limit=5` [`logs`]; `before` cursor [`logs_before`]; `level=error` [`logs_err`] | `200`; paging works | |
| `level=bogus` [`logs_badlvl`] | `422` with a string `detail` listing the levels | |
| `limit=5000` [`logs_bigl`] | `422`, maximum 1000 | |
| The docs page's example (`limit=100&level=error`) [`logs_docs`] | `200` | New |
| `limit` of `0`, `1`, `1000` [`logs_l0`, `logs_l1`, `logs_l1000`] | All `200`; `0` returns `[]` | New |
| `limit=abc` [`logs_lstr`] | `422` | New |
| `before=yesterday` [`logs_badbefore`] | `422` | New |
| `level` of `debug`, `info`, `warn` [`logs_debug`, `logs_info`, `logs_warn`] | `200` | New |
| `level=INFO` [`logs_upper`] | `200` with info entries: matching is case-insensitive | New |
| Logs after webhooks and after the burst [`logs_after_wh`, `logs_after_burst`] | Each delivery logged as "Webhook received with N keys" | Partly new |

## Files

| Test | Result | New |
|---|---|---|
| List the root; the docs' `?path=/data`; a missing directory [`files_list`, `files_list_data`, `files_list_404`] | `200` (root `/zeroclaw-data` on ZeroClaw; see table below); `400`; `404` | |
| List a file path [`list_file`] | `404 Not a directory` | New |
| List `{root}/../etc` [`list_traversal`] | `400` | New |
| List a folder with a dotfile and a unicode name [`list_hidden`] | Both listed, directories first | New |
| mkdir twice; outside the volume [`mkdir`, `mkdir_again`, `mkdir_outside`] | `200`, `200`, `400` | |
| mkdir on an existing directory containing files and subdirectories [`mkdir_existing`] | `200 {"ok": true, "path": …}` | New |
| mkdir with `../`; with no `path` [`mkdir_traversal`, `mkdir_missing`] | `400 Invalid path` | New |
| mkdir where a file exists [`mkdir_overfile`] | **`500 Could not create folder`** | New |
| Write, overwrite, no `content`, a prefix trick, deep new path [`write*`] | `200`, `200`, `400`, `400`, `200` | |
| Write empty content [`write_empty`] | `200`, a zero-byte file | New |
| Write numeric content [`write_int`] | `400 content must be a string` | New |
| Write onto an existing directory [`write_overdir`] | **`500 Write failed`** | New |
| Write to `café notes.md`; a dotfile; with `../`; with intra-volume `../`; with an extra field [`write_unicode`, `write_dotfile`, `write_traversal`, `write_intra_traversal`, `write_extra`] | `200`, `200`, `400`, `200`, `200` | New |
| Move; missing source; existing destination [`move`, `move_404`, `move_409`] | `200`, `404`, `409` | |
| Move onto itself [`move_self`] | `400 Source and destination are the same` | New |
| Move to `/tmp`; without `to` [`move_outside`, `move_missing`] | `400 Invalid path` | New |
| Move a directory [`move_dir`] | `200` | New |
| Invalid JSON on write, mkdir, and move [`write_badjson`, `mkdir_badjson`, `move_badjson`] | `422 Unprocessable Entity` with `json_invalid` | Follow-up |
| Upload with `dest_dir` twice; no file; as a chat attachment [`upload_*`] | `200` (silent overwrite); `422`; `200` to `workspace/inbox/` | |
| Upload to the docs' `/data/inbox`; to `/tmp` [`upload_docs`, `upload_outside`] | `400 Invalid destination` | New |
| Upload to a `dest_dir` that doesn't exist [`upload_newdir`] | `200`; directory created | New |
| Upload a file named `../evil.csv` [`upload_traversal`] | Saved as `evil.csv` | New |
| Upload a zero-byte file [`upload_empty`] | `200`, `size: 0` | New |
| Upload with `dest_dir` and `message` [`upload_both`] | Saved to `dest_dir` | New |
| Download from the volume and from `/tmp`; missing file; `/etc/hostname` [`download*`, `exec_tmpdl`] | `200` with the real content type; `404`; `404` | |
| Download the docs' `/data/report.pdf` [`download_docs`] | `404` | New |
| Download a directory [`download_dir`] | `400 path is a directory` | New |
| Download `café notes.md` [`download_unicode`] | `200`; `filename*` carries the UTF-8 name | New |
| Download a zero-byte file [`download_empty`] | **`404 File not found`** | New |
| Delete file, folder (recursive), again, root, no path, attachment [`del_*`] | `200`, `200`, `404`, `400`, `422`, `200` | |
| Delete the docs' `/data/old`; `/tmp/oas.txt`; a `../` path [`del_docs`, `del_outside`, `del_traversal`] | `400 Invalid path` | New |
| File call to a sleeping agent [`wake_files`] | Woke it (2.2 s) | |
| Waking while another agent is active on Free plan [`wake_files_list`] | `200 OK` (2.8s; wake limit unenforced on live API) | Follow-up |

### Volume roots across templates

Probed live on 2026-10-04/05 by creating disposable agents and calling `GET /api/agents/{agent_id}/files/list` with no `path`:

| Template | Framework | Volume Root | Default Contents Observed |
|---|---|---|---|
| `openclaw` | `openclaw` | `/data` | `.openclaw/`, `inbox/`, `outbox/`, `lost+found/` |
| `zeroclaw` | `zeroclaw` | `/zeroclaw-data` | `.zeroclaw/`, `data/` |
| `hermes` | `hermes` | `/opt/data` | `.hermes/`, `workspace/`, `skills/`, `memories/`, `logs/`, config files |
| `codex` | `custom` | `/data` | `.codex/`, `inbox/`, `outbox/`, `workspace/`, `lost+found/` |
| `dsh` | `dsh` | `/data` | `.dsh/`, `inbox/`, `outbox/`, `workspace/`, `lost+found/` |
| `claude_code` | `custom` | *(untested)* | Requires `ANTHROPIC_API_KEY` |

This confirms `/data` is valid for `openclaw`, `codex`, and `dsh`, but fails with `400 Invalid path` on `zeroclaw` (`/zeroclaw-data`) and `hermes` (`/opt/data`).


## Webhooks

| Test | Result | New |
|---|---|---|
| Get the token; without auth [`wh_token`, `wh_token_noauth`] | `200`; `403` | |
| Get the token a second time [`wh_token_again`] | The same token | New |
| Invoke with header token, query token, no token, wrong token [`wh_header`, `wh_query`, `wh_none`, `wh_bad`] | All `200` and delivered | |
| Invoke an unknown agent [`wh_404`] | `404` | |
| Invoke with `text/plain`, invalid JSON, an empty body, a JSON array [`wh_text`, `wh_badjson`, `wh_empty`, `wh_array`] | All `200`; delivered as "0 keys" (array: "3 keys") | New |
| 35 invokes back to back, after 8 earlier ones [`wh_burst`] | **22 × `200`, then 13 × `429`**, `Retry-After: 44` | New |

## Not tested

### Tests I can't run

| Test | Why |
|---|---|
| The `{"status": "accepted"}` webhook response, and `401` for a wrong token | Only appears once Maritime turns on token enforcement |
| Another account's agents (`403` vs `404`, data leakage) | Needs a second Maritime account |
| Agent error states (a crashed or failed deploy) | Would mean deliberately breaking an agent; the unknown-template agent was deleted before any later state was checked |
| Multi-turn conversation recall (`conversation_id`) on proprietary templates | Needs own provider key to test whether continuous memory works across turns |

### Possible, but not done yet

| Test | What it would take |
|---|---|
| The 100 MB file cap | A 101 MB upload (bandwidth only). Skipped by choice on 2026-10-04 |
| Create from a GitHub repo or a public container image | An image or repo that follows Maritime's container contract, and a longer deploy |
| `conversation_id` on `codex` or `dsh` | One more agent per framework; neither needs an env var |
| How `timeout: 0`, `1.5` and `"5"` are interpreted | `sleep 3` with each value, to see which ones stop it |
| Whether upload with `dest_dir` and `message` notifies the agent | Read the agent's logs or conversation after the upload |
| CORS from Maritime's own origin (`https://maritime.sh`) | One preflight case, to see whether any origin is allowed |
| Waking a sleeping agent with exec or a webhook | Only file calls and chat were tested |
| What happens to an unknown-template agent over time | Poll it for a few minutes before deleting it |

### Not applicable to this API

These items come from a general API-testing checklist, and nothing in the 18 operations supports them: PUT/PATCH merge semantics, `ETag` and `If-Match` concurrency, API versioning, pagination of the agent list, sorting and search, and token refresh flows. Running Schemathesis or Dredd against production was ruled out too. Fuzzing could create agents without the `oas-test-` prefix, which the project's safety rule forbids.
