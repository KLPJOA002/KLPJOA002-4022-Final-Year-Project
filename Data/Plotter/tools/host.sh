#!/bin/sh
# Run a command with the project venv on the host (works from inside Flatpak too).
cd "$(dirname "$0")/.." || exit 1
if [ -f /.flatpak-info ] && command -v flatpak-spawn >/dev/null 2>&1; then
    exec flatpak-spawn --host --directory="$PWD" \
        --env=PYTHONPATH="$PWD" --env=PATH="$PWD/.venv/bin:/usr/local/bin:/usr/bin:/bin" "$@"
fi
PYTHONPATH="$PWD" PATH="$PWD/.venv/bin:$PATH" exec "$@"
