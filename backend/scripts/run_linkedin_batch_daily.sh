#!/bin/zsh

set -u

SCRIPT_DIR="${0:A:h}"
BACKEND_DIR="${SCRIPT_DIR:h}"
PROJECT_DIR="${BACKEND_DIR:h}"
RUN_DIR="${PROJECT_DIR}/import/linkedin_batch_scrape"
LOCK_DIR="${RUN_DIR}/daily-run.lock"
DAILY_LIMIT="${LINKEDIN_DAILY_LIMIT:-50}"
RUN_TIMEOUT_SECONDS="${LINKEDIN_DAILY_TIMEOUT_SECONDS:-4230}"

# launchd and cron both provide a minimal PATH.
export PATH="/usr/local/bin:/opt/homebrew/bin:${HOME}/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

mkdir -p "${RUN_DIR}/logs"
exec >> "${RUN_DIR}/logs/daily.stdout.log" 2>> "${RUN_DIR}/logs/daily.stderr.log"

if ! [[ "${RUN_TIMEOUT_SECONDS}" =~ ^[1-9][0-9]*$ ]]; then
  echo "LINKEDIN_DAILY_TIMEOUT_SECONDS must be a positive integer; got '${RUN_TIMEOUT_SECONDS}'." >&2
  exit 1
fi

TIMEOUT_BIN="$(command -v timeout || command -v gtimeout || true)"
if [[ -z "${TIMEOUT_BIN}" ]]; then
  echo "GNU timeout is required but was not found on PATH." >&2
  exit 1
fi

acquire_lock() {
  if mkdir "${LOCK_DIR}" 2>/dev/null; then
    echo "$$" > "${LOCK_DIR}/pid"
    return 0
  fi

  local existing_pid=""
  if [[ -f "${LOCK_DIR}/pid" ]]; then
    existing_pid="$(<"${LOCK_DIR}/pid")"
  fi
  if [[ -n "${existing_pid}" ]] && kill -0 "${existing_pid}" 2>/dev/null; then
    echo "LinkedIn batch scrape is already running with PID ${existing_pid}; skipping."
    return 1
  fi

  # The previous process died without running its EXIT trap.
  rm -f "${LOCK_DIR}/pid"
  rmdir "${LOCK_DIR}" 2>/dev/null || {
    echo "Could not remove stale lock directory ${LOCK_DIR}." >&2
    return 1
  }
  mkdir "${LOCK_DIR}" || return 1
  echo "$$" > "${LOCK_DIR}/pid"
}

release_lock() {
  rm -f "${LOCK_DIR}/pid"
  rmdir "${LOCK_DIR}" 2>/dev/null || true
}

if ! acquire_lock; then
  exit 0
fi
trap release_lock EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] Starting daily LinkedIn batch (limit=${DAILY_LIMIT}, timeout=${RUN_TIMEOUT_SECONDS}s)."

if ! command -v docker >/dev/null; then
  echo "docker is not installed or is not on PATH." >&2
  exit 1
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running; starting Docker Desktop."
  open -gj -a Docker
  for _ in {1..90}; do
    docker info >/dev/null 2>&1 && break
    sleep 2
  done
fi

if ! docker info >/dev/null 2>&1; then
  echo "Docker did not become ready within 180 seconds." >&2
  exit 1
fi

if docker container inspect kizuna-postgres >/dev/null 2>&1; then
  docker start kizuna-postgres >/dev/null
else
  docker compose --project-directory "${PROJECT_DIR}" up -d postgres
fi

for _ in {1..60}; do
  if docker exec kizuna-postgres pg_isready -U kizuna -d kizuna >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if ! docker exec kizuna-postgres pg_isready -U kizuna -d kizuna >/dev/null 2>&1; then
  echo "Kizuna Postgres did not become ready within 60 seconds." >&2
  exit 1
fi

cd "${BACKEND_DIR}"
"${TIMEOUT_BIN}" \
  --verbose \
  --signal=INT \
  --kill-after=30s \
  "${RUN_TIMEOUT_SECONDS}s" \
  uv run python scripts/batch_scrape_linkedin_profiles.py \
  --limit "${DAILY_LIMIT}" \
  --headless
run_status=$?
if [[ "${run_status}" -eq 124 || "${run_status}" -eq 137 ]]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] Daily LinkedIn batch exceeded ${RUN_TIMEOUT_SECONDS}s and was terminated." >&2
fi
echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] Daily LinkedIn batch exited with status ${run_status}."
exit "${run_status}"
