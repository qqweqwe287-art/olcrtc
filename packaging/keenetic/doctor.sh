#!/bin/sh
# ai-generated: read-only Keenetic client diagnostics and optional SOCKS probe.
set -u

# shellcheck source=lib/common.sh
# shellcheck disable=SC1091 # runtime path exists only after bundle installation.
. /opt/lib/olcrtc-keenetic/lib/common.sh

probe_url=https://icanhazip.com
run_probe=yes
failures=0
warnings=0

# ai-generated: record a successful diagnostic check.
pass() {
    printf 'PASS  %s\n' "$*"
}

# ai-generated: record a diagnostic warning that does not make the package unsafe.
warn() {
    warnings=$((warnings + 1))
    printf 'WARN  %s\n' "$*"
}

# ai-generated: record a failed diagnostic check.
fail_check() {
    failures=$((failures + 1))
    printf 'FAIL  %s\n' "$*"
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --quick) run_probe=no; shift ;;
        --probe-url)
            [ "$#" -ge 2 ] || olc_die "--probe-url requires an HTTPS URL"
            probe_url=$2
            shift 2
            ;;
        *) olc_die "unknown option: $1" ;;
    esac
done

case "$(uname -m 2>/dev/null)" in
    aarch64|arm64) pass "architecture is ARM64" ;;
    *) fail_check "unsupported architecture: $(uname -m 2>/dev/null)" ;;
esac
if [ -d "$OLCRTC_PREFIX" ] && [ -w "$OLCRTC_PREFIX" ]; then
    pass "$OLCRTC_PREFIX is writable"
else
    fail_check "$OLCRTC_PREFIX is unavailable or read-only"
fi
if [ -x "$OLCRTC_BIN" ]; then
    pass "client binary is installed"
else
    fail_check "client binary is missing"
fi
if [ -s "$OLCRTC_CONFIG" ]; then
    pass "client configuration exists"
else
    fail_check "client configuration is missing"
fi
if [ -s "$OLCRTC_RELEASE" ]; then
    pass "release metadata exists"
else
    warn "release metadata is missing"
fi

if [ -s "$OLCRTC_BLOCKED" ]; then
    fail_check "supervisor is blocked after repeated early exits"
elif olc_pid_alive "$OLCRTC_RUNNER_PID" "run-client.sh"; then
    pass "supervisor process is alive"
else
    fail_check "supervisor process is not running"
fi

if olc_pid_alive "$OLCRTC_CHILD_PID" "$OLCRTC_BIN"; then
    pass "olcRTC child process is alive"
else
    fail_check "olcRTC child process is not running"
fi

if command -v python3 >/dev/null 2>&1; then
    if python3 - <<'PY'
# ai-generated: verify that the loopback SOCKS listener accepts TCP connections.
import socket

with socket.create_connection(("127.0.0.1", 8808), timeout=2):
    pass
PY
    then
        pass "SOCKS port 127.0.0.1:8808 accepts connections"
    else
        fail_check "SOCKS port 127.0.0.1:8808 is not ready"
    fi
else
    fail_check "python3 is missing"
fi

if [ "$run_probe" = yes ]; then
    case "$probe_url" in
        https://*) ;;
        *) fail_check "probe URL must use HTTPS"; probe_url= ;;
    esac
    if [ -n "$probe_url" ] && command -v curl >/dev/null 2>&1; then
        if result=$(curl -fsS --socks5-hostname 127.0.0.1:8808 --connect-timeout 10 \
            --max-time 30 "$probe_url" 2>/dev/null); then
            pass "SOCKS end-to-end probe succeeded: $result"
        else
            fail_check "SOCKS listener is up but the end-to-end probe failed"
        fi
    fi
fi

printf 'SUMMARY failures=%s warnings=%s\n' "$failures" "$warnings"
[ "$failures" -eq 0 ]
