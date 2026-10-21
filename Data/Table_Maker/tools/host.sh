#!/bin/sh
# Run a command with rsplot's venv and both packages importable, on the host
# (works from inside Flatpak too, so the host TeX Live is available).
cd "$(dirname "$0")/.." || exit 1
PLOTTER="$(cd ../Plotter && pwd)"
PP="$PWD:$PLOTTER"
if [ -f /.flatpak-info ] && command -v flatpak-spawn >/dev/null 2>&1; then
    exec flatpak-spawn --host --directory="$PWD" \
        --env=PYTHONPATH="$PP" --env=PATH="$PLOTTER/.venv/bin:/usr/local/bin:/usr/bin:/bin" "$@"
fi
PYTHONPATH="$PP" PATH="$PLOTTER/.venv/bin:$PATH" exec "$@"
