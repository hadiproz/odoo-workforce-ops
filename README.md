# Workforce Ops — Odoo placement operations (portfolio)

[![CI](https://github.com/hadiproz/odoo-workforce-ops/actions/workflows/ci.yml/badge.svg)](https://github.com/hadiproz/odoo-workforce-ops/actions/workflows/ci.yml)

A small custom Odoo addon for an outsourcing company that places workers at
client companies. It is a **portfolio / learning project by a final-year
student**, not a production system and not tied to any real employer.

The module is original work and is released under the MIT license.

## What it does

`workforce_ops` manages three business objects:

- **Job orders** — a client company's staffing request: client, position
  title, required headcount, computed filled headcount and progress, deadline,
  and a guarded workflow (`draft → confirmed → in_progress → done`, plus
  `cancelled`).
- **Workers** — placeable people with contact details, a job position, an
  archive control, and a computed status (`available / placed / inactive`).
- **Placements** — the link between one worker and one job order, with a start
  date, an optional end date, and a workflow (`draft → placed → finished`,
  plus `cancelled`).

The central business rule is enforced in code and in PostgreSQL: **a worker
may have at most one active (`placed`) placement at a time**. A Python
constraint raises `ValidationError`, and a partial unique index
(`workforce_placement_worker_active_unique`) protects the same invariant
against concurrent transactions.

Computed values stay consistent with placement changes: filling or releasing a
placement updates the job order's filled/progress values and the worker's
status, including when the records involved are hidden from the current user.

### Features

| Area | Delivered |
| --- | --- |
| Models | `workforce.job.order`, `workforce.worker`, `workforce.placement` |
| Workflows | Server-guarded state actions; no state jumps through raw writes |
| Computations | Stored filled count, progress percentage, worker status |
| Views | Form, list, kanban and search views for all three models |
| Menu | One **Workforce Ops** app with Job Orders, Workers, Placements |
| Security | Workforce User and Workforce Manager, native Odoo 20 `ir.access` |
| Report | **Placement Assignment Letter** QWeb PDF, printable from the form |
| API | `GET /api/workforce/job_orders`, `POST /api/workforce/placements` |
| Demo data | 3 clients, 5 workers, 3 job orders, 2 placements (fictional) |
| Tests | Odoo `TransactionCase` / `HttpCase`, run by CI with `--test-enable` |

## Screenshots

Screenshots will be added after a local run on a machine with Docker. They are
intentionally not fabricated or committed in advance.

## Quickstart (local Docker)

Prerequisites: Docker with Compose v2.

```bash
git clone https://github.com/hadiproz/odoo-workforce-ops.git
cd odoo-workforce-ops
docker compose up -d
```

Then open <http://localhost:8069>, create a database (tick **Load demo data**
if you want the sample records), and install the **Workforce Ops** app from
Apps.

After installation, assign a role: **Settings → Users & Companies → Users**,
open a user, and set **Workforce Ops** to **User** or **Manager**. The menus
and API endpoints are restricted to those roles; a user without a Workforce
role sees no Workforce menus and receives an access error from the API. This
includes the `admin` user if you use it.

The Compose file mounts `./addons` at `/mnt/extra-addons` read-only and keeps
PostgreSQL and Odoo data in named volumes. To start clean, remove the volumes
with `docker compose down --volumes` (this deletes the databases).

## Repository / module structure

```text
odoo-workforce-ops/
  README.md
  LICENSE
  docker-compose.yml
  ci/run_tests.sh
  .github/workflows/ci.yml
  addons/workforce_ops/
    __init__.py
    __manifest__.py
    models/
      job_order.py
      worker.py
      placement.py
    security/
      workforce_security.xml
      ir.access.csv
    views/
      job_order_views.xml
      worker_views.xml
      placement_views.xml
      workforce_menus.xml
    controllers/
      main.py
    report/
      placement_report.xml
    demo/
      demo.xml
    tests/
      common.py
      test_job_order.py
      test_worker.py
      test_placement.py
      test_security.py
      test_report.py
      test_http.py
      test_demo.py
```

### Security model

Odoo 20 replaced the legacy split between `ir.model.access.csv` and recorded
rules with native `ir.access` records that carry both the operation grant and
an optional record domain. This project follows that Odoo 20 mechanism:

- `security/ir.access.csv` grants Workforce User `cu` on job orders and
  placements, `cru` on workers, and Workforce Manager `crud` on all three.
  Workforce Users cannot unlink any of the three models.
- `security/workforce_security.xml` defines the two groups and adds the native
  read domains: Workforce Users cannot read cancelled job orders or cancelled
  placements (including placements whose job order is cancelled). Managers
  read everything.
- These domains apply to reads only. A Workforce User can still cancel a
  readable record, and the action returns to the list instead of reloading a
  now-hidden form.

This is the approved Odoo 20 deviation from the older `ir.model.access.csv` /
`ir.rule` wording in the brief; no legacy shim or dead CSV is shipped.

## REST API

Both endpoints are plain JSON over HTTP, require an authenticated Odoo session
with a Workforce role, and operate with that user's normal ORM rights. They are
not JSON-RPC endpoints.

### Authentication

Odoo's session login route is JSON-RPC and needs a JSON-RPC envelope:

```bash
BASE_URL=http://localhost:8069
DB=workforce_ops
LOGIN=admin
PASSWORD=admin
COOKIE_JAR="$(mktemp)"

curl --silent --show-error --cookie-jar "$COOKIE_JAR" \
  --header 'Content-Type: application/json' \
  --data "$(jq -n --arg db "$DB" --arg login "$LOGIN" --arg password "$PASSWORD" \
    '{jsonrpc:"2.0",method:"call",params:{db:$db,login:$login,password:$password},id:1}')" \
  "$BASE_URL/web/session/authenticate"
```

The response is HTTP 200 even when the credentials are wrong, so check that it
has no `error` member and a positive `result.uid`. These credentials are
disposable examples, not production advice. Accounts with MFA enabled need the
normal browser login flow.

### List non-cancelled job orders

```bash
curl --include --cookie "$COOKIE_JAR" \
  --header 'Accept: application/json' \
  "$BASE_URL/api/workforce/job_orders"
```

```json
[
  {
    "id": 41,
    "client_name": "PT Nusantara Logistik Sejahtera",
    "position": "Warehouse Operator",
    "required": 3,
    "filled": 1,
    "state": "in_progress"
  }
]
```

`id`, `required` and `filled` are JSON integers. Results are ordered by `id`.
An empty result is `[]`. Cancelled orders are never returned, even for
Managers. Unsupported query parameters return a 400 JSON error.

### Create a draft placement

```bash
curl --include --cookie "$COOKIE_JAR" \
  --header 'Content-Type: application/json' \
  --data '{"job_order_id":41,"worker_id":17,"start_date":"2026-12-01"}' \
  "$BASE_URL/api/workforce/placements"
```

```json
{"id": 101}
```

The endpoint creates a **draft** placement and returns HTTP 201. It does not
place the worker or change the job-order workflow. Repeat the call to create
another draft. Use real IDs from your instance; the examples above are
illustrative.

### Errors

Handler-owned errors use this shape:

```json
{"error": {"code": "invalid_request", "message": "start_date must be a valid YYYY-MM-DD date."}}
```

| Status | Code | Meaning |
| --- | --- | --- |
| 400 | `invalid_request` | Bad body shape, ID type, date, or query parameter |
| 400 | `validation_error` | Model validation error (safe message) |
| 403 | `forbidden` | Caller has no Workforce role or operation permission |
| 404 | `reference_not_found` | Referenced worker/order missing or not readable |
| 415 | `unsupported_media_type` | POST body is not `application/json` |

An unauthenticated request with `auth='user'` is rejected by Odoo's HTTP
dispatcher with a redirect to `/web/login` before the handler runs; the addon
cannot return JSON in that case. Use `curl` without `--location` for the API
calls and check the status and content type rather than assuming that a login
page is JSON.

## How CI verifies the module

`.github/workflows/ci.yml` runs on every push to `main` and every pull request
targeting `main` on `ubuntu-24.04`. All runtime proof is in GitHub Actions;
this project does not require a local Docker daemon.

`ci/run_tests.sh` performs, in order:

1. Static checks of Python syntax, XML well-formedness, CSV headers, and the
   manifest file list.
2. Pulls the pinned images, starts PostgreSQL with a healthcheck, and records
   the resolved image digests plus Odoo/Python/PostgreSQL/wkhtmltopdf versions.
3. Installs the module in a fresh database **without demo data** and runs the
   addon tests with `--test-enable --test-tags=/workforce_ops`.
4. Installs the module again in a fresh database **with demo data**, runs the
   same tests, and verifies the exact 13 demo XML records and their computed
   states.
5. Boots the normal web container against the demo database and requires a
   real HTTP 200 from `/web/login`.
6. Fails on a nonzero Odoo exit code, a missing/zero-test or non-clean test
   summary, a missing required test, a module that is not `installed`, a demo
   data mismatch, or a non-200 HTTP response.
7. Uploads the Odoo logs, version evidence, module checks and login response as
   a workflow artifact (14-day retention).

The required named tests include the three brief acceptance tests
(`test_confirm_draft_job_order`, `test_filled_count_when_placed`,
`test_worker_has_at_most_one_active_placement`) plus every test class,
including the real-PDF rendering test.

Run the same script locally on a Docker host with:

```bash
bash ci/run_tests.sh
```

The GitHub workflow removes its isolated Compose project after uploading the
evidence; the script itself never starts a Docker daemon.

## Tech versions

- **Odoo 20** — image `odoo:20.0-20261112` (pinned by digest
  `sha256:8bcae4c1f895683ee851e19dd3e7d999e81e770defe9015bc9dad8bbf10f2b0d`).
  The tag was verified over the network against the Docker Hub API on
  2026-11-13: `library/odoo:20` returned HTTP 200, the dated tag returned HTTP
  200, and `library/odoo:21` returned HTTP 404. The target is therefore Odoo
  20, not a fallback major.
- **PostgreSQL 16** — image `postgres:16` (pinned by digest
  `sha256:63e83b5a3dc36a917dccb76fe1bd2ac51f1ec9c1deb47ff20d4f04233bf6eae9`),
  which is Odoo 20's documented minimum major.
- Python 3.12+ is required by Odoo 20; the official image's own interpreter is
  recorded in CI.
- CI runner: `ubuntu-24.04` with Compose v2.

## Demo data

The demo file loads exactly 13 addon-owned records: 3 fictional Indonesian
client companies, 5 fictional workers, 3 job orders and 2 placements. Names,
addresses and contacts are samples; emails use reserved `example.com`
addresses. Demo records are loaded only through the manifest `demo` key and
appear only when a database is created with demo data.

## Limitations

- This is a single shared dataset; it is not multi-company or tenant-isolated.
- The job-order `done` state is an explicit user action, not an automatic
  completion metric; finished placements reduce the filled count even on a
  done order.
- The API list is deliberately unpaginated, and the POST endpoint intentionally
  has CSRF disabled for session-authenticated JSON calls.
- The assignment letter renders current linked data; it does not snapshot
  client or position values at placement time.
- Browser-level visual rendering (kanban/forms) is not exercised by CI. The CI
  proof covers installation, ORM tests, HTTP endpoints, real PDF bytes and the
  HTTP login page.

## License

MIT — Copyright (c) 2026 Hadi Sutomo Wonosantoso. See [LICENSE](LICENSE).
The Odoo manifest uses Odoo's broader `Other OSI approved licence` metadata
value; the source itself is MIT.
