#!/bin/sh
set -eu

test_dir=$(mktemp -d)
cleanup() {
    if [ -s "$test_dir/pid" ]; then
        kill "$(cat "$test_dir/pid")" 2>/dev/null || true
    fi
    rm -rf -- "$test_dir"
}
trap cleanup EXIT INT TERM

fake_app="$test_dir/powersifu-app"
cat >"$fake_app" <<'EOF'
#!/bin/sh
if [ "${1:-}" = "--hold" ]; then
    printf '%s\n' "$$" >"$POWERSIFU_TEST_PID"
    exec sleep 30
else
    printf '%s\n' "$*"
fi
EOF
chmod 0755 "$fake_app"

foreground_output=$(POWERSIFU_APP_EXEC="$fake_app" ./bin/powersifu --foreground --version)
[ "$foreground_output" = "--version" ]

POWERSIFU_TEST_PID="$test_dir/pid" POWERSIFU_APP_EXEC="$fake_app" ./bin/powersifu --hold
attempt=0
while [ ! -s "$test_dir/pid" ] && [ "$attempt" -lt 50 ]; do
    sleep 0.02
    attempt=$((attempt + 1))
done
[ -s "$test_dir/pid" ]
kill -0 "$(cat "$test_dir/pid")"
