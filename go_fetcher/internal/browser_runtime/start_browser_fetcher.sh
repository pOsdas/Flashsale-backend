#!/usr/bin/env bash
set -Eeuo pipefail

log() {
  printf '[browser-runtime] %s\n' "$*" >&2
}

is_true() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

BROWSER_DISPLAY="${BROWSER_DISPLAY:-:99}"
BROWSER_CDP_HOST="${BROWSER_CDP_HOST:-127.0.0.1}"
BROWSER_CDP_PORT="${BROWSER_CDP_PORT:-9222}"
BROWSER_PROFILE_DIR="${BROWSER_PROFILE_DIR:-/data/browser-profile}"
BROWSER_WINDOW_SIZE="${BROWSER_WINDOW_SIZE:-1400,900}"
BROWSER_LANGUAGE="${BROWSER_LANGUAGE:-ru-RU}"
BROWSER_START_TIMEOUT_SECONDS="${BROWSER_START_TIMEOUT_SECONDS:-90}"
BROWSER_RUNTIME_DIR="${BROWSER_RUNTIME_DIR:-/tmp/browser-runtime}"
BROWSER_LOG_PATH="${BROWSER_LOG_PATH:-${BROWSER_RUNTIME_DIR}/chrome.log}"
XVFB_LOG_PATH="${XVFB_LOG_PATH:-${BROWSER_RUNTIME_DIR}/xvfb.log}"
WINDOW_MANAGER_LOG_PATH="${WINDOW_MANAGER_LOG_PATH:-${BROWSER_RUNTIME_DIR}/openbox.log}"
CDP_VERSION_PATH="${BROWSER_RUNTIME_DIR}/cdp-version.json"
APP_PORT="${APP_PORT:?APP_PORT is required}"
APP_MODULE="${APP_MODULE:?APP_MODULE is required}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-1}"
GUNICORN_THREADS="${GUNICORN_THREADS:-1}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-120}"

export DISPLAY="${BROWSER_DISPLAY}"
export LANG="${LANG:-ru_RU.UTF-8}"
export LC_ALL="${LC_ALL:-ru_RU.UTF-8}"

mkdir -p \
  "${BROWSER_PROFILE_DIR}" \
  "${BROWSER_RUNTIME_DIR}" \
  "$(dirname "${BROWSER_LOG_PATH}")" \
  "$(dirname "${XVFB_LOG_PATH}")" \
  "$(dirname "${WINDOW_MANAGER_LOG_PATH}")"

rm -f \
  "${BROWSER_PROFILE_DIR}/SingletonCookie" \
  "${BROWSER_PROFILE_DIR}/SingletonLock" \
  "${BROWSER_PROFILE_DIR}/SingletonSocket"

CHROME_BIN="${BROWSER_EXECUTABLE_PATH:-}"
if [[ -z "${CHROME_BIN}" ]]; then
  for candidate in \
    /usr/bin/google-chrome-stable \
    /usr/bin/google-chrome \
    /opt/google/chrome/google-chrome; do
    if [[ -x "${candidate}" ]]; then
      CHROME_BIN="${candidate}"
      break
    fi
  done
fi

if [[ -z "${CHROME_BIN}" || ! -x "${CHROME_BIN}" ]]; then
  log "Google Chrome executable was not found"
  exit 1
fi

XVFB_PID=""
WINDOW_MANAGER_PID=""
CHROME_PID=""
APP_PID=""

terminate_process() {
  local pid="${1:-}"
  local name="${2:-process}"

  if [[ -z "${pid}" ]] || ! kill -0 "${pid}" 2>/dev/null; then
    return
  fi

  log "Stopping ${name}, pid=${pid}"
  kill -TERM "${pid}" 2>/dev/null || true

  for _ in $(seq 1 50); do
    if ! kill -0 "${pid}" 2>/dev/null; then
      return
    fi
    sleep 0.1
  done

  kill -KILL "${pid}" 2>/dev/null || true
}

cleanup() {
  local exit_code="${1:-0}"
  trap - EXIT INT TERM

  terminate_process "${APP_PID}" "Gunicorn"
  terminate_process "${CHROME_PID}" "Google Chrome"
  terminate_process "${WINDOW_MANAGER_PID}" "Openbox"
  terminate_process "${XVFB_PID}" "Xvfb"

  exit "${exit_code}"
}

trap 'cleanup 130' INT
trap 'cleanup 143' TERM
trap 'cleanup $?' EXIT

DISPLAY_NUMBER="${BROWSER_DISPLAY#:}"
DISPLAY_NUMBER="${DISPLAY_NUMBER%%.*}"
rm -f "/tmp/.X${DISPLAY_NUMBER}-lock"
rm -rf "/tmp/.X11-unix/X${DISPLAY_NUMBER}"

XVFB_SCREEN_SIZE="${BROWSER_WINDOW_SIZE/,/x}x24"

log "Starting Xvfb on ${BROWSER_DISPLAY} with ${XVFB_SCREEN_SIZE}"
Xvfb "${BROWSER_DISPLAY}" \
  -screen 0 "${XVFB_SCREEN_SIZE}" \
  -nolisten tcp \
  -ac \
  >"${XVFB_LOG_PATH}" 2>&1 &
XVFB_PID=$!

sleep 0.5
if ! kill -0 "${XVFB_PID}" 2>/dev/null; then
  log "Xvfb failed to start"
  cat "${XVFB_LOG_PATH}" >&2 || true
  exit 1
fi

log "Starting Openbox window manager"
openbox --sm-disable >"${WINDOW_MANAGER_LOG_PATH}" 2>&1 &
WINDOW_MANAGER_PID=$!

sleep 0.5
if ! kill -0 "${WINDOW_MANAGER_PID}" 2>/dev/null; then
  log "Openbox failed to start"
  cat "${WINDOW_MANAGER_LOG_PATH}" >&2 || true
  exit 1
fi

CHROME_ARGS=(
  "--remote-debugging-address=${BROWSER_CDP_HOST}"
  "--remote-debugging-port=${BROWSER_CDP_PORT}"
  "--user-data-dir=${BROWSER_PROFILE_DIR}"
  "--window-size=${BROWSER_WINDOW_SIZE}"
  "--lang=${BROWSER_LANGUAGE}"
  "--no-first-run"
  "--no-default-browser-check"
  "--password-store=basic"
  "--disable-session-crashed-bubble"
  "--disable-search-engine-choice-screen"
)

if is_true "${BROWSER_DISABLE_SANDBOX:-false}"; then
  CHROME_ARGS+=("--no-sandbox" "--disable-setuid-sandbox")
fi

if is_true "${BROWSER_DISABLE_DEV_SHM_USAGE:-false}"; then
  CHROME_ARGS+=("--disable-dev-shm-usage")
fi

if [[ -n "${BROWSER_PROXY_SERVER:-}" ]]; then
  CHROME_ARGS+=("--proxy-server=${BROWSER_PROXY_SERVER}")
fi

if [[ -n "${BROWSER_PROXY_BYPASS_LIST:-}" ]]; then
  CHROME_ARGS+=("--proxy-bypass-list=${BROWSER_PROXY_BYPASS_LIST}")
fi

if [[ -n "${BROWSER_EXTRA_ARGS:-}" ]]; then
  # BROWSER_EXTRA_ARGS is controlled by deployment configuration.
  # shellcheck disable=SC2206
  EXTRA_ARGS=( ${BROWSER_EXTRA_ARGS} )
  CHROME_ARGS+=("${EXTRA_ARGS[@]}")
fi

CHROME_ARGS+=("about:blank")

log "Starting external Google Chrome: cdp=http://${BROWSER_CDP_HOST}:${BROWSER_CDP_PORT}, profile=${BROWSER_PROFILE_DIR}"
"${CHROME_BIN}" "${CHROME_ARGS[@]}" >"${BROWSER_LOG_PATH}" 2>&1 &
CHROME_PID=$!

CDP_VERSION_URL="http://${BROWSER_CDP_HOST}:${BROWSER_CDP_PORT}/json/version"
START_DEADLINE=$((SECONDS + BROWSER_START_TIMEOUT_SECONDS))

while (( SECONDS < START_DEADLINE )); do
  if ! kill -0 "${CHROME_PID}" 2>/dev/null; then
    log "Google Chrome exited before CDP became ready"
    cat "${BROWSER_LOG_PATH}" >&2 || true
    exit 1
  fi

  if curl --fail --silent --show-error \
    --max-time 2 \
    "${CDP_VERSION_URL}" \
    >"${CDP_VERSION_PATH}"; then
    log "Google Chrome CDP is ready"
    break
  fi

  sleep 0.5
done

if ! curl --fail --silent --show-error \
  --max-time 2 \
  "${CDP_VERSION_URL}" \
  >"${CDP_VERSION_PATH}"; then
  log "Google Chrome CDP did not become ready in ${BROWSER_START_TIMEOUT_SECONDS}s"
  cat "${BROWSER_LOG_PATH}" >&2 || true
  exit 1
fi

log "Starting Gunicorn: module=${APP_MODULE}, port=${APP_PORT}"
gunicorn \
  --bind "0.0.0.0:${APP_PORT}" \
  --workers "${GUNICORN_WORKERS}" \
  --threads "${GUNICORN_THREADS}" \
  --timeout "${GUNICORN_TIMEOUT}" \
  "${APP_MODULE}" &
APP_PID=$!

APP_EXIT_CODE=0

while true; do
  if ! kill -0 "${APP_PID}" 2>/dev/null; then
    set +e
    wait "${APP_PID}"
    APP_EXIT_CODE=$?
    set -e
    log "Gunicorn exited with code ${APP_EXIT_CODE}"
    break
  fi

  if ! kill -0 "${CHROME_PID}" 2>/dev/null; then
    log "Google Chrome exited unexpectedly"
    cat "${BROWSER_LOG_PATH}" >&2 || true
    APP_EXIT_CODE=1
    break
  fi

  if ! kill -0 "${WINDOW_MANAGER_PID}" 2>/dev/null; then
    log "Openbox exited unexpectedly"
    cat "${WINDOW_MANAGER_LOG_PATH}" >&2 || true
    APP_EXIT_CODE=1
    break
  fi

  if ! kill -0 "${XVFB_PID}" 2>/dev/null; then
    log "Xvfb exited unexpectedly"
    cat "${XVFB_LOG_PATH}" >&2 || true
    APP_EXIT_CODE=1
    break
  fi

  sleep 1
done

cleanup "${APP_EXIT_CODE}"
