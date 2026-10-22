# Maritime API: documentation gap analysis

This analysis looks at 18 core operations of the Maritime REST API. It records where the published documentation falls short of what a developer needs to integrate, and how the companion OpenAPI document, [`maritime_openapi.yaml`](maritime_openapi.yaml), closes each gap.

## Summary

Maritime documents its API in two places. The docs page has prose descriptions and a few examples. The auto-generated OpenAPI spec has paths and partial schemas. The docs page doesn't link to the spec, so most developers will only ever see the docs page. The spec is listed only in the site's `llms.txt`.

The tables count each gap in each source. The **Both** column counts only gaps that neither source fills, which is what a developer who reads both actually faces.

**Operations with the gap:**

| Gap | Out of | Docs page | Official spec | Both |
|---|---|---|---|---|
| No response example | 18 operations | 11 | 18 | 11 |
| No request example | 18 operations | 10 | 18 | 10 |
| No error documented beyond a generic `422` | 18 operations | 15 | 16 | 15 |
| No operation description | 18 operations | 2 | 7 | 2 |
| Response shape not documented | 17 that return a body | 10 | 13 | 6 |
| Request body structure not given | 8 that take a body | 2 | 5 | 2 |

**Fields with no description:**

| Gap | Out of | Docs page | Official spec | Both |
|---|---|---|---|---|
| Request-body fields | 39 fields in 8 request bodies | 26 | 39 | 26 |
| Agent response fields | 34 fields in the agent record | 34 | 34 | 34 |

**How these were counted:** an example is a curl command, JSON body or sample output. A **Run it** button counts as a response example, because clicking it shows a live response, but not as a request example. The docs page has one on templates and one on list agents (which needs a dashboard sign-in). A response shape or error counts as documented if it appears in a schema, an example, or prose that names it. For example, the spec's description of webhook invoke says it returns the agent record, and the docs page says move answers `409`. The 39 request-body fields are the 32 the spec declares plus 7 hidden in bodies it types only as "any object" (exec, write, mkdir, move).

The two sources complement each other a little. The docs page supplies examples and the exec and file body fields. The spec supplies typed responses for create, get and logs, and descriptions for most operations. Even combined, they leave 6 operations with no documented response, 15 with no documented error, 25 of the 27 create fields unexplained, and nothing at all on the agent record. Live testing also turned up four places where Maritime's docs, on the API page and the Limits page, are wrong or misleading.

**Most significant findings:**

1. **Webhook tokens aren't enforced, and the docs only half say so.** The docs say calls *without* a token still work. Testing showed calls with a *wrong* token are accepted too.
2. **The "machines awake at once" limit does not return HTTP 429.** The Limits page states that the Free plan allows only 1 machine awake at once and answers `429` with a 15-second retry hint. Live testing on 2026-10-08 revealed two realities:
   - On **Chat (`POST /chat`)**, the limit is enforced by the LLM proxy, but it returns **`HTTP 200 OK`** within 0.56s with an advisory payload (`{"response": "This agent can't be woken right now: You have 1 machines awake. Your plan permits 1. Sleep a machine, or upgrade your plan: https://maritime.sh/billing"}`). The agent is **not** woken and remains in `status: sleeping`.
   - On **Files (`GET /files/list`)**, the limit is bypassed entirely: calling it returns `200 OK` and wakes the micro-VM, allowing multiple machines to run concurrently in `status: active` on the Free plan.
   In neither case does the API return `429` or a `Retry-After` header.
3. **Authentication error codes partially contradict the documentation.** The Limits page states that missing, invalid, revoked, or expired keys return `401`, while keys lacking required scopes return `403`. In reality:
   - A missing `Authorization` header returns `403 Not authenticated` (not `401`).
   - Invalid, revoked, and expired keys return `401 Invalid token`.
   - Keys lacking required scopes (e.g. `scopes: ["deploy"]` on agent create) or keys restricted to a specific `project_id` correctly return `403 Forbidden` with explicit detail messages (`"This API key lacks the '<scope>' scope required for this action."` or project restriction details), confirming the Limits page's scope rule.
4. **Three of the docs' own example paths fail on some agents.** The docs use `/data` as their universal example path. While `/data` is the volume root for `openclaw`, `codex`, and `dsh`, it is outside a ZeroClaw agent's volume (`/zeroclaw-data`) and a Hermes agent's volume (`/opt/data`), so the list, upload and file-delete examples return `400` on those frameworks.
5. **Errors use status codes the official spec omits or misclassifies.** While the Limits page lists `402` (plan limit) and `409` (conflict/name taken), the official OpenAPI spec omits both and declares only `422` or no error responses. Furthermore, several endpoints return validation errors as `400` rather than the `422` the spec declares (though invalid JSON returns `422` across all endpoints), and write and mkdir return `500 Internal Server Error` for a path conflict a client caused.
6. **Create doesn't check `templateId`.** A misspelt template ID returns `201`. It creates a `framework: custom` agent with nothing to run, and that agent takes one of the plan's seats.
7. **The most complete reference is hidden.** The spec is the only place that types the create, get and logs responses, but the docs page never links to it. Where a developer does find it, searching it for exec's timeout turns up only `timeoutS`, a Computers field that agent exec silently ignores.

The resulting OpenAPI document covers all 18 operations and passes `redocly lint`. It matches all 68 captured live responses from 2026-10-03, 200 responses from an extended run on 2026-10-04, follow-up verification runs on 2026-10-08 covering revoked/expired tokens, concurrent wake behaviors, and JSON decoding errors across file endpoints, and re-verification on 2026-10-10 confirming scoped key 403 authorization enforcement. [`TESTING.md`](TESTING.md) lists every test and what's still untested.

## Scope and method

**In scope** (18 operations): health, templates, agent create/list/get/delete, chat, exec, logs, the seven file endpoints, webhook invoke and webhook token. These form one workflow: pick a template, create an agent, talk to it, work with its files, and trigger it externally. End users, usage, billing, Computers and lifecycle endpoints are out of scope.

**Sources compared:**

| Source | What it provides |
|---|---|
| [REST API docs page](https://maritime.sh/docs/api) | Prose descriptions, a few request bodies, limits, five example responses, and **Run it** buttons on two endpoints |
| [Auto-generated OpenAPI spec](https://api.maritime.sh/openapi.json) (FastAPI, OpenAPI 3.1, v0.1.0) | Paths, parameters, partial request and response schemas |
| Live calls, 2026-10-03 | Real responses, status codes and headers for every operation |
| Extended live calls, 2026-10-04 | Boundaries, wrong types, auth and 404 on every route, limits, the webhook rate limit, CORS and `405` handling |

**Testing approach.** A disposable agent was created from the `zeroclaw` template, which needs no third-party LLM key. Each operation was exercised on its success path and on the error paths that could be triggered safely. The agent was then deleted. All responses were saved and later replayed against the finished spec with `openapi-core` to confirm every schema matches real traffic. The 2026-10-04 run followed the same pattern, with a second short-lived test agent for the duplicate-name and delete-while-deploying cases.

## Gap categories

### 1. Contradictions: the documentation is wrong

These are the highest-severity gaps. A developer who follows the documentation exactly gets the wrong result.

| Endpoint | Documentation says | Observed behaviour | Evidence |
|---|---|---|---|
| `POST /webhooks/{id}` | Docs: "Calls without a token still work for now" | Calls with an incorrect token are also accepted | `X-Maritime-Webhook-Token: wrong` returned `200`, and the payload was delivered (agent log: "Webhook received with 1 keys"). |
| `GET /files/list`, `POST /files/upload`, `DELETE /files/delete` | Docs examples: `?path=/data`, `dest_dir=/data/inbox`, `?path=/data/old` | Return `400` on `zeroclaw` (`Invalid path` / `Invalid destination`) and would fail on `hermes` | The volume root is framework-dependent: `/data` on `openclaw`/`codex`/`dsh`, `/zeroclaw-data` on `zeroclaw`, and `/opt/data` on `hermes`. The docs warn not to hardcode the root, but their own examples do. |
| Endpoints that wake agents (`chat`, `exec`, file operations, `webhooks`) | Limits page: "Machines awake at once: Free 1 [...] a wake past the limit answers 429 with a 15 second retry hint" | Not enforced: waking a second sleeping agent while one is already active succeeds with `200` | Testing on 2026-10-08: `Zero Claw` was set to `active`, then `GET /files/list` was called on a sleeping test agent. It returned `200` in 2.8s; both ran concurrently in `active` state with no 429 or retry headers. |
| All authenticated endpoints | Limits page: `401` for missing, invalid, revoked, or expired keys; `403` for insufficient scope | Missing key returns `403 Not authenticated` (not `401`). Keys with insufficient scope or project restrictions return `403` with specific scope messages. Invalid, revoked, or expired keys return `401 Invalid token`. | Testing on 2026-10-04 and 2026-10-08 found missing `Authorization` header returns `403` on all 16 authenticated endpoints; testing on 2026-10-10 confirmed keys lacking scopes (`provision`, `deploy`, `manage`) return `403` with granular error details. |

### 2. Missing response schemas

The official spec declares an empty schema for 14 of the 17 operations that return a body, so code generators produce untyped results. (Agent delete returns `204` with no body, so its empty schema is correct.) The docs page shows example output for five operations and has **Run it** buttons on two more (templates and list agents), and the spec's prose says webhook invoke returns the agent record. That still leaves 6 operations whose response is documented nowhere: download, write, mkdir, move, file delete and webhook token.

Every response is now fully typed from observed data, for example:

- **Chat:** `{"response": string}`
- **Exec:** `{"exitCode", "stdout", "stderr"}`. `stderr` is always empty because output is merged into `stdout`.
- **File list:** `{"path", "root", "entries": [{"name", "isDir", "size", "mtime"}]}`. `mtime` is in Unix seconds.
- **Write, mkdir, delete:** `{"ok", "path"}`. **Move:** `{"ok", "from", "to"}`.
- **Webhook token:** `{"agentId", "token", "header", "url", "source"}`
- **Webhook invoke:** returns the full agent record. This isn't mentioned on the docs page; the spec description only hints at it.

### 3. Undocumented errors

In the official OpenAPI spec, all 18 operations list `422` as their only error response, or none at all. The published docs describe several errors across two pages: the Limits page (`https://maritime.sh/docs/limits`) lists platform-wide status codes (`401` missing/invalid key, `402` plan limit, `403` insufficient scope, `404` agent not found, `409` name conflict, `429` rate limit), while the REST API page (`https://maritime.sh/docs/api`) documents move's `404`/`409`, file delete's `404`, webhook's `429`, and exec's `400`, `404`, `409`, `501`, and `503`.

However, the official spec omits almost all of these status codes and their response schemas. In addition, live testing revealed notable discrepancies from the documentation: missing authentication returns `403 Not authenticated` (rather than the Limits page's stated `401`), and client-caused path conflicts on write and mkdir trigger unhandled `500` server errors. Testing verified these real error responses:

| Status | When | Endpoints |
|---|---|---|
| `401` | Invalid, expired, or revoked API key (`"Invalid token"`) | All 16 authenticated endpoints (verified live 2026-10-04, 2026-10-08, and 2026-10-10) |
| `403` | Missing `Authorization` header (`"Not authenticated"`); API key lacking required scope (`"This API key lacks the '<scope>' scope required for this action."`); or project-restricted key on core routes | All 16 authenticated endpoints (missing auth verified 2026-10-04/08; scopes verified 2026-10-10) |
| `402` | Plan's agent limit reached (`code: seat_limit`, `upgrade: true`) | create |
| `404` | Unknown agent; also returned for a malformed, non-UUID ID | All agent-scoped (each one checked on 2026-10-04) |
| `404` | Missing file, source or directory; a file path given to list (`"Not a directory"`); a **zero-byte** file on download | download, delete, move, list |
| `400` | Path outside the agent's volume, or the volume root on delete | list, write, mkdir, move, delete |
| `400` | `dest_dir` outside the volume (`"Invalid destination"`) | upload |
| `400` | A directory given to download (`"path is a directory"`) | download |
| `400` | Move onto itself (`"Source and destination are the same"`) | move |
| `400` | Bad hand-validated body (`"content must be a string"`, `"command must be a non-empty string or list of strings"`, or `"Invalid path"` for a missing path field) | write, exec, mkdir, move |
| `405` | Unsupported method, with an `Allow` header that can be incomplete (`PUT /api/agents` answered `Allow: GET`) | All |
| `409` | Move destination already exists; agent name already used | move, create |
| `422` | Unknown log `level` (with a **string** `detail`, unlike other 422s) | logs |
| `422` | Body isn't valid JSON (array `detail`, type `json_invalid`), even on hand-validated endpoints | create, exec, write, mkdir, move (all verified live) |
| `429` | Webhook rate limit: the 31st invoke in a minute (`"Rate limit exceeded: 30/min for public-webhook"`, `Retry-After: 44`) | webhook invoke |
| `500` | Write onto an existing directory (`"Write failed"`); mkdir where a file exists (`"Could not create folder"`) | write, mkdir |
| `502` | Exec command timed out, or a negative `timeout` (`"Exec failed"`) | exec |

The error body has two shapes: `detail` is a string for most errors, and an array of validation issues for schema validation failures. The spec now models both, as `Error` and `ValidationError`.

### 4. Undescribed fields and parameters

The official spec declares 32 request-body fields and 34 agent response fields, and none has a description. Four bodies (exec, write, mkdir, move) are typed only as "any object", which hides 7 more fields. The docs page describes 13 of these 39 request fields: `name`, `templateId`, `message`, `conversation_id`, the three upload form fields, `command`, `timeout`, `path` and `content` for write, and `from` and `to`. Neither source describes the other 25 create fields, mkdir's `path`, or any field of the agent record.

**Exec's timeout field appears only on the docs page.** The spec types the exec body as "any object", and its only timeout field is `timeoutS`, which belongs to the Computers `ExecRequest` model. Agent exec ignores `timeoutS`: `sleep 8` with `timeoutS: 3` ran the full 8 s and returned `200`, while `timeout: 3` stopped it with a `502` after about 4 s. A developer who looks the field up in the spec finds the wrong one.

**Fixed:** every field in scope now has a description. Fields with no public explanation (`autoPair`, `desktop`, `gatewayPassword`, `serverId`, `uploadS3Key`, `addOns`) are explicitly labelled "Not described in the public docs" rather than guessed.

**Enumerations recovered from live behaviour:**

- **Log `level`:** `debug`, `info`, `warn`, `error`. The only place this list appears is the API's own error message.
- **Agent `status`** (observed): `deploying` → `active` → `sleeping`. Developers might expect `running`; the API says `active`.
- **Log `source`** (observed): `system`, `container`, `webhook`.

### 5. Behaviour documented only in prose, or not at all

| Behaviour | Where it was documented | Status in the new spec |
|---|---|---|
| Upload to an existing file name silently overwrites (unlike move, which refuses with `409`) | Nowhere | Documented |
| Upload without `dest_dir` saves to `<volume>/workspace/inbox/` with a Unix-timestamp prefix | Partially (auto-spec description) | Documented, with both response examples |
| `write` creates missing parent directories | Nowhere | Documented |
| `mkdir` succeeds if the directory already exists | Implied by "mkdir -p" in the auto-spec | Documented |
| A non-zero exit code still returns `200` | Nowhere | Documented |
| `conversation_id` continuity depends on the framework; the response doesn't echo it | Nowhere | Documented as observed |
| Calls to a sleeping agent wake it (about 2.7 s for a file listing) | Docs prose | Documented in the API and tag descriptions |
| Agent deploy took about 25 s from `201` to `active` (zeroclaw) | Nowhere | Documented as a guide |
| Webhook token can go in a header or a query parameter | Docs prose | Modelled as two optional `apiKey` security schemes |
| The webhook request body is arbitrary JSON; plain text, invalid JSON and empty bodies are also accepted and delivered (as "0 keys") | Nowhere (no request body in the auto-spec) | Documented |
| Logs pagination via `before` | Auto-spec parameter only | Documented with usage guidance |
| An unknown `templateId` creates a `framework: custom` agent instead of failing | Nowhere | Documented |
| Agent names must be unique (`409`); a 278-character name is accepted | Nowhere | Documented |
| Exec output over 256 KiB keeps the **last** 256 KiB, prefixed `[output truncated]\n` | Docs: "capped at 256 KB" (which end is kept isn't said) | Documented |
| Exec `timeout` above 120 is clamped to 120 (`502` after 120.6 s), not rejected | Docs: "max 120" | Documented |
| Exec runs as `root` in `/`; a missing binary returns `200` with exit code `127` | Nowhere | Documented |
| A zero-byte file can't be downloaded (`404`), though list shows it | Nowhere | Documented |
| Upload creates a missing `dest_dir` and strips directories from the filename (`../evil.csv` becomes `evil.csv`) | Nowhere | Documented |
| Write onto a directory, or mkdir onto a file, returns `500` | Nowhere | Documented |
| Log `level` matching is case-insensitive; `limit=0` returns `[]` | Nowhere | Documented |
| Only `Authorization: Bearer` is read; public endpoints ignore a bad key; unknown query parameters and body fields are ignored | Nowhere | Documented |
| Browser calls from other origins are refused (`400 Disallowed CORS origin` on preflight) | Nowhere | Documented |
| An agent can be deleted while still `deploying` | Nowhere | Documented |
| The webhook token stays the same across calls | Auto-spec says "derived" only | Documented as observed |

### 6. No examples

None of the 18 operations has a request or response example in the official spec. The docs page has request examples for 8 operations and response examples for 7 (5 written out, plus the **Run it** buttons on templates and list agents), so 9 operations have no example in either source. The new spec has realistic examples, taken from real responses, for every request body and every success and error response. Where an endpoint has meaningfully different modes, it shows several named examples: create from a template vs from an image, exec with argv vs a shell string, upload to a directory vs as an attachment.

## Per-endpoint summary

Severity reflects the worst gap closed: **High** means following the existing docs leads to wrong behaviour or an unusable response; **Medium** means a developer would have to experiment to find out; **Low** means polish.

| # | Operation | Key gaps closed | Severity |
|---|---|---|---|
| 1 | `GET /health` | Empty response schema | Low |
| 2 | `GET /api/templates` | Empty response schema; `envRequired` meaning undocumented | Medium |
| 3 | `GET /api/agents` | Empty response schema; auth errors (401/403) | Medium |
| 4 | `POST /api/agents` | 25 fields described nowhere; status lifecycle; `templateId` sets `framework` but isn't checked; `402` plan limit and `409` duplicate name | Medium |
| 5 | `GET /api/agents/{id}` | `status` values; 404 for malformed IDs | Medium |
| 6 | `DELETE /api/agents/{id}` | 404 on repeat delete; works while deploying | Low |
| 7 | `POST /chat` | Empty response schema; `conversation_id` behaviour; empty message accepted | High |
| 8 | `POST /exec` | `timeout` missing from the spec (only the Computers `timeoutS` appears); untyped body; empty response schema; 400, 422 and 502 errors; non-zero exit returns `200`; truncation keeps the tail; timeouts clamped | Medium |
| 9 | `GET /logs` | `level` values and case-insensitivity; `limit` bounds (0–1000); `before` cursor; string-detail 422 | Medium |
| 10 | `GET /files/list` | Empty response schema; docs example fails; 400 and 404 | High |
| 11 | `GET /files/download` | Response content type and headers (including `filename*`); 400 for a directory; 404, including for empty files | Medium |
| 12 | `POST /files/upload` | Empty response; two modes; silent overwrite; docs example fails with `400 Invalid destination`; filename sanitised | High |
| 13 | `PUT /files/write` | Untyped body; empty response; 400 and 500 errors; creates parents | Medium |
| 14 | `POST /files/mkdir` | Untyped body; empty response; idempotence; 500 when a file is in the way | Low |
| 15 | `POST /files/move` | Untyped body; empty response; 400, 404 and 409 | Medium |
| 16 | `DELETE /files/delete` | Empty response; 400 for root and outside paths; docs example fails; 404 | Medium |
| 17 | `POST /webhooks/{id}` | Token not enforced (even wrong tokens); no request body; empty response; real response is the agent record; `429` body and `Retry-After` | High |
| 18 | `GET /webhooks/{id}/token` | Empty response schema | Medium |

## What remains unverified

The 2026-10-04 run closed four items from the earlier list: the webhook `429`, the exec output cap, exec timeout clamping, and the plan-limit error on create. Follow-up verification on 2026-10-08 closed five more: auth checks on create (`403` missing, `401` bad key), revoked and expired API keys (`401`), invalid JSON decoding on write/mkdir/move (`422`), and testing the "machines awake at once" limit (which proved the `429` limit is unenforced on the live API). On 2026-10-10, live verification across permission scopes confirmed that keys with insufficient scope or project restrictions return `403 Forbidden` with explicit scope error messages, correcting an earlier note. The rest couldn't be safely or cheaply triggered. They're documented from the docs and labelled in each operation's `x-verification` block:

- **The 100 MB file transfer cap.** It would mean uploading over 100 MB.
- **The `{"status": "accepted"}` webhook response**, which only appears once Maritime turns token enforcement on.
- **Agent error states.** None occurred. The unknown-template agent was still `deploying` when it was listed right after creation; its later state wasn't checked.
- **Creating from a GitHub repo or a container image.** Only template creation was exercised.
- **`conversation_id` on frameworks other than ZeroClaw.**

[`TESTING.md`](TESTING.md) has the full list of what remains untested and why.

## Recommendations for Maritime

1. Link the OpenAPI spec from the REST API page, so developers find the typed schemas it already has.
2. Declare response models on the 14 endpoints whose schema is `{}`, so the auto-generated spec stops discarding the shapes the API actually returns.
3. Type the exec request body: declare `timeout` (1–120) and `command` as a string or an array, so the field can be found in the spec and isn't confused with the Computers `timeoutS`.
4. Document `401`/`403`/`404`/`400`/`409` globally, and choose one status for request validation (`400` or `422`).
5. Change the file-list, upload and file-delete examples to use the `root` returned by the API, or note that `/data` is framework-dependent (e.g. `/zeroclaw-data` on ZeroClaw, `/opt/data` on Hermes) where the examples are shown.
6. Say plainly that webhook tokens aren't validated yet, and send a deprecation header on unauthenticated invokes before enforcement begins.
7. Reject an unknown `templateId` with a `4xx` instead of creating an agent that uses up a seat.
8. Return `4xx` rather than `500` for client-caused path conflicts on write and mkdir, and let download serve empty files.
