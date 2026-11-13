#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ARTIFACTS="${CI_ARTIFACTS_DIR:-ci-artifacts}"
mkdir -p "$ARTIFACTS"

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-workforce_ops_ci_${GITHUB_RUN_ID:-local}_${GITHUB_RUN_ATTEMPT:-1}}"
export ODOO_DB_PASSWORD="${ODOO_DB_PASSWORD:-odoo}"

NO_DEMO_DB="workforce_ops_test"
DEMO_DB="workforce_ops_demo"
NO_DEMO_LOG="$ARTIFACTS/odoo-test-no-demo.log"
DEMO_LOG="$ARTIFACTS/odoo-test-demo.log"

log() { printf '\n=== %s ===\n' "$*"; }
fail() { printf '\nFAILED: %s\n' "$*" >&2; exit 1; }

collect_diagnostics() {
    local rc=$?
    set +e
    docker compose ps > "$ARTIFACTS/compose-ps.txt" 2>&1
    docker compose logs --no-color db > "$ARTIFACTS/db.log" 2>&1
    docker compose logs --no-color web > "$ARTIFACTS/odoo-startup.log" 2>&1
    docker compose images > "$ARTIFACTS/images.txt" 2>&1
    exit "$rc"
}
trap collect_diagnostics EXIT

psql_query() {
    docker compose exec -T db psql -U odoo -d "$1" -Atc "$2" | tr -d '\r'
}

psql_scalar() {
    psql_query "$1" "$2" | head -n 1
}

log "Preflight"
printf 'Compose project: %s\n' "$COMPOSE_PROJECT_NAME" | tee "$ARTIFACTS/summary.txt"
docker --version | tee -a "$ARTIFACTS/versions.txt"
docker compose version | tee -a "$ARTIFACTS/versions.txt"
docker compose config --quiet

python3 - "$REPO_ROOT" <<'PY' | tee "$ARTIFACTS/static-checks.txt"
import ast
import csv
import pathlib
import sys
import xml.etree.ElementTree as ET

repo = pathlib.Path(sys.argv[1])
addon = repo / 'addons' / 'workforce_ops'

for path in sorted(addon.rglob('*.py')):
    ast.parse(path.read_text(), filename=str(path))
for path in sorted(addon.rglob('*.xml')):
    ET.parse(path)
for path in sorted(addon.rglob('*.csv')):
    with path.open(newline='') as handle:
        rows = list(csv.reader(handle))
    assert rows and rows[0][0] == 'id', f'bad CSV header in {path}'

manifest_path = addon / '__manifest__.py'
manifest = ast.literal_eval(manifest_path.read_text())
for section in ('data', 'demo'):
    for relpath in manifest.get(section, []):
        assert (addon / relpath).is_file(), f'missing manifest file {relpath}'
assert manifest['depends'] == ['base', 'web', 'base_report_wkhtmltox']
print('static checks OK')
PY

log "Pulling pinned images"
docker compose pull db web 2>&1 | tee "$ARTIFACTS/pull.log"

log "Starting PostgreSQL"
docker compose up -d --wait --wait-timeout 120 db
psql_scalar postgres 'SHOW server_version;' | tee "$ARTIFACTS/postgres-version.txt"

log "Recording resolved images and runtime versions"
docker compose config --images | while read -r image; do
    printf '%s -> %s\n' "$image" \
        "$(docker image inspect "$image" --format '{{join .RepoDigests ","}}')"
done | tee -a "$ARTIFACTS/versions.txt"

docker compose run --rm -T --no-deps web odoo --version | tee -a "$ARTIFACTS/versions.txt"
docker compose run --rm -T --no-deps web python3 --version | tee -a "$ARTIFACTS/versions.txt"
docker compose run --rm -T --no-deps web wkhtmltopdf --version | tee -a "$ARTIFACTS/versions.txt"

grep -Eq 'Odoo Server 20\.' "$ARTIFACTS/versions.txt" \
    || fail "the Odoo image is not Odoo 20"
python3 - "$ARTIFACTS/versions.txt" <<'PY' || fail "the Odoo image Python is older than 3.12"
import re
import sys

text = open(sys.argv[1], encoding='utf-8').read()
match = re.search(r'Python (\d+)\.(\d+)', text)
assert match, 'no Python version recorded'
assert (int(match.group(1)), int(match.group(2))) >= (3, 12), match.group(0)
PY
grep -qi 'with patched qt' "$ARTIFACTS/versions.txt" \
    || fail "wkhtmltopdf is missing patched Qt support"
PG_NUM="$(psql_scalar postgres 'SHOW server_version_num;')"
[[ "$PG_NUM" -ge 160000 && "$PG_NUM" -lt 170000 ]] || fail "PostgreSQL major is not 16 (version_num=$PG_NUM)"

run_odoo_tests() {
    local db="$1" logfile="$2" demo_flag="$3"
    set +e
    docker compose run --rm -T --no-deps web odoo \
        -d "$db" -i workforce_ops \
        --test-enable --test-tags=/workforce_ops --stop-after-init \
        "$demo_flag" --workers=0 --max-cron-threads=0 \
        --http-interface=0.0.0.0 --log-level=test \
        --log-handler=odoo.tests.stats:DEBUG \
        2>&1 | tee "$logfile"
    local rc=${PIPESTATUS[0]}
    set -e
    printf '%s\n' "$rc" > "${logfile}.exit"
    return "$rc"
}

verify_test_log() {
    local logfile="$1" label="$2" summary
    summary="$(grep -E '[0-9]+ failed, [0-9]+ error\(s\) of [0-9]+ tests when loading database' "$logfile" | tail -n 1 || true)"
    if [ -z "$summary" ]; then
        echo "[$label] missing Odoo test summary"
        return 1
    fi
    echo "[$label] $summary"
    if ! echo "$summary" | grep -Eq '[[:space:]]0 failed, 0 error\(s\) of [1-9][0-9]* tests'; then
        echo "[$label] test summary is not a clean nonzero run"
        return 1
    fi
    if grep -q 'Failed to initialize database' "$logfile"; then
        echo "[$label] database initialization failed"
        return 1
    fi
    return 0
}

REQUIRED_TESTS=(
    "workforce_ops.test_job_order.TestJobOrder.test_confirm_draft_job_order"
    "workforce_ops.test_placement.TestPlacement.test_filled_count_when_placed"
    "workforce_ops.test_placement.TestPlacement.test_worker_has_at_most_one_active_placement"
    "workforce_ops.test_worker.TestWorker"
    "workforce_ops.test_security.TestWorkforceSecurity"
    "workforce_ops.test_report.TestAssignmentLetter"
    "workforce_ops.test_http.TestWorkforceHttp.test_assignment_letter_pdf"
    "workforce_ops.test_demo.TestWorkforceDemo"
)

verify_required_tests() {
    local logfile="$1" missing=0 test_id
    for test_id in "${REQUIRED_TESTS[@]}"; do
        if grep -q "$test_id" "$logfile"; then
            echo "found: $test_id"
        else
            echo "MISSING: $test_id"
            missing=1
        fi
    done
    return "$missing"
}

check_module() {
    local db="$1" output
    output="$(psql_query "$db" "SELECT name || '=' || state FROM ir_module_module WHERE name IN ('workforce_ops','base_report_wkhtmltox') ORDER BY name;")"
    printf '[%s] module states:\n%s\n' "$db" "$output" | tee -a "$ARTIFACTS/module-checks.txt"
    echo "$output" | grep -qx 'workforce_ops=installed' || return 1
    echo "$output" | grep -qx 'base_report_wkhtmltox=installed' || return 1
    return 0
}

log "Gate 1: install without demo data and run tests"
if ! run_odoo_tests "$NO_DEMO_DB" "$NO_DEMO_LOG" --without-demo; then
    fail "no-demo installation or tests failed (see $NO_DEMO_LOG)"
fi
verify_test_log "$NO_DEMO_LOG" "no-demo" || fail "no-demo test summary check failed"
verify_required_tests "$NO_DEMO_LOG" || fail "required tests were not executed in the no-demo run"
check_module "$NO_DEMO_DB" || fail "required modules are not installed in $NO_DEMO_DB"
NO_DEMO_COUNT="$(psql_scalar "$NO_DEMO_DB" "SELECT count(*) FROM ir_model_data WHERE module = 'workforce_ops' AND name LIKE 'demo_%';")"
[ "$NO_DEMO_COUNT" = "0" ] || fail "demo records leaked into the no-demo database ($NO_DEMO_COUNT)"
printf '[%s] demo XML records: %s\n' "$NO_DEMO_DB" "$NO_DEMO_COUNT" | tee -a "$ARTIFACTS/module-checks.txt"

log "Gate 2: install with demo data and run tests"
if ! run_odoo_tests "$DEMO_DB" "$DEMO_LOG" --with-demo; then
    fail "demo installation or tests failed (see $DEMO_LOG)"
fi
verify_test_log "$DEMO_LOG" "demo" || fail "demo test summary check failed"
verify_required_tests "$DEMO_LOG" || fail "required tests were not executed in the demo run"
check_module "$DEMO_DB" || fail "required modules are not installed in $DEMO_DB"
DEMO_COUNT="$(psql_scalar "$DEMO_DB" "SELECT count(*) FROM ir_model_data WHERE module = 'workforce_ops' AND name LIKE 'demo_%';")"
[ "$DEMO_COUNT" = "13" ] || fail "expected 13 demo XML records, found $DEMO_COUNT"
printf '[%s] demo XML records: %s\n' "$DEMO_DB" "$DEMO_COUNT" | tee -a "$ARTIFACTS/module-checks.txt"
printf '[%s] job orders:\n' "$DEMO_DB" | tee -a "$ARTIFACTS/module-checks.txt"
psql_query "$DEMO_DB" "SELECT position_title || ' | ' || state || ' | filled=' || headcount_filled || ' | progress=' || round(progress::numeric, 2) FROM workforce_job_order ORDER BY id;" | tee -a "$ARTIFACTS/module-checks.txt"
printf '[%s] workers:\n' "$DEMO_DB" | tee -a "$ARTIFACTS/module-checks.txt"
psql_query "$DEMO_DB" "SELECT name || ' | ' || status FROM workforce_worker ORDER BY id;" | tee -a "$ARTIFACTS/module-checks.txt"

log "Gate 3: boot Odoo over HTTP and require a 200 login page"
export ODOO_DBFILTER='^workforce_ops_demo$'
docker compose up -d web
COOKIE_JAR="$(mktemp)"
HTTP_CODE="000"
for _attempt in $(seq 1 30); do
    HTTP_CODE="$(curl --silent --show-error \
        --cookie-jar "$COOKIE_JAR" --cookie "$COOKIE_JAR" \
        --output "$ARTIFACTS/web-login.html" --write-out '%{http_code}' \
        --connect-timeout 3 --max-time 10 \
        http://localhost:8069/web/login || true)"
    [ "$HTTP_CODE" = "200" ] && break
    sleep 2
done
rm -f "$COOKIE_JAR"
printf 'GET /web/login -> HTTP %s\n' "$HTTP_CODE" | tee "$ARTIFACTS/web-login-status.txt"
[ "$HTTP_CODE" = "200" ] || fail "Odoo did not serve /web/login with HTTP 200 (last status $HTTP_CODE)"
check_module "$DEMO_DB" || fail "module state changed after HTTP boot"

log "All gates passed"
printf 'Result: PASS\n' | tee -a "$ARTIFACTS/summary.txt"
