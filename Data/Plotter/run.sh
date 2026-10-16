#!/bin/sh
# Launch the rsplot UI. Inside a Flatpak sandbox (e.g. Flatpak VS Code) the
# command is re-run on the host so that the host's TeX Live is usable.
cd "$(dirname "$0")" || exit 1
exec tools/host.sh python -m rsplot.ui.app "$@"
