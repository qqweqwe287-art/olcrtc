#!/bin/sh
# ai-generated: BusyBox-compatible client supervisor with child-aware health.
set -u

# shellcheck source=lib/common.sh
# shellcheck disable=SC1091 # runtime path exists only after bundle installation.
. /opt/lib/olcrtc-keenetic/lib/common.sh

stopping=0
child_pid=
quick_failures=0

# shellcheck disable=SC2317,SC2329 # invoked by EXIT trap.
# ai-generated: remove only PID state owned by this supervisor.
cleanup_runner() {
    rm -f "$OLCRTC_CHILD_PID"
}

# shellcheck disable=SC2317,SC2329 # invoked by signal traps.
# ai-generated: forward termination to the real olcRTC child.
stop_runner() {
    stopping=1
    if [ -n "$child_pid" ]; then
        kill -TERM "$child_pid" 2>/dev/null || true
    fi
}

trap stop_runner TERM INT HUP
trap cleanup_runner EXIT

rm -f "$OLCRTC_BLOCKED" "$OLCRTC_CHILD_PID"
olc_rotate_log "$OLCRTC_CLIENT_LOG"

while [ "$stopping" -eq 0 ]; do
    started=$(date +%s)
    "$OLCRTC_BIN" "$OLCRTC_CONFIG" >>"$OLCRTC_CLIENT_LOG" 2>&1 &
    child_pid=$!
    printf '%s\n' "$child_pid" >"$OLCRTC_CHILD_PID"
    wait "$child_pid"
    code=$?
    ended=$(date +%s)
    runtime=$((ended - started))
    child_pid=
    rm -f "$OLCRTC_CHILD_PID"
    [ "$stopping" -ne 0 ] && break

    if [ "$runtime" -ge 60 ]; then
        quick_failures=0
    else
        quick_failures=$((quick_failures + 1))
    fi
    if [ "$quick_failures" -ge 5 ]; then
        printf '%s\n' "client exited too quickly 5 times; inspect $OLCRTC_CLIENT_LOG" >"$OLCRTC_BLOCKED"
        printf '%s\n' "supervisor blocked after repeated early exits" >>"$OLCRTC_CLIENT_LOG"
        exit "$code"
    fi

    delay=$((2 << quick_failures))
    [ "$delay" -le 60 ] || delay=60
    printf '%s\n' "client exit=$code runtime=${runtime}s restart_in=${delay}s" >>"$OLCRTC_CLIENT_LOG"
    sleep "$delay" &
    child_pid=$!
    wait "$child_pid" 2>/dev/null || true
    child_pid=
done

exit 0
