#!/bin/sh
set -eu
test "$(id -u)" = 10001
for missing in python3 tor sudo; do
  if command -v "$missing" >/dev/null 2>&1; then exit 1; fi
done
mkdir -p "$HOME/test-bin"
cat > "$HOME/test-bin/curl" <<'SH'
#!/bin/sh
set -eu
archive=''; out=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    https://github.com/rdzv/rdzv/releases/download/*) archive=${1##*/} ;;
    -o) shift; out=$1 ;;
  esac
  shift
done
test "$archive" = "rdzv-$RDZV_RELEASE-linux-$RDZV_ARCH.tar.gz"
test -n "$out"
cp "/release/$archive" "$out"
SH
chmod 700 "$HOME/test-bin/curl"
export PATH="$HOME/test-bin:$PATH"
sh /installer install
sh /installer install
sh /installer host --help >/dev/null
sh /installer join --help >/dev/null
test "$("$HOME/.local/bin/rdzv" --version)" = "Rendezvous $RDZV_VERSION"
ENV_DIR=$(cat "$HOME/.local/share/rendezvous/$RDZV_RELEASE-$RDZV_ARCH/environment")
printf 'Rootless installation verified: %s\n' "$RDZV_ARCH"
export PATH="$HOME/.local/bin:$PATH"
"$ENV_DIR/python/bin/python3" -I /tests/verify_portable_session.py
"$ENV_DIR/python/bin/python3" -I /tests/verify_agent_session.py
"$ENV_DIR/python/bin/python3" -I /tests/verify_host_controls.py
