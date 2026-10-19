#!/bin/sh
# Run with `sh install.sh` on both desktop and Termux.
set -eu

editable=false
case "${1:-}" in
    --dev) editable=true ;;
    -h|--help)
        printf '%s\n' 'Usage: sh install.sh [--dev]' \
            'Install ytxt in a private virtual environment; --dev uses editable source.' \
            'Overrides: PYTHON, YTXT_HOME, YTXT_BIN_DIR.'
        exit 0
        ;;
    '') ;;
    *) printf 'Unknown option: %s\n' "$1" >&2; exit 2 ;;
esac
if [ "$#" -gt 1 ]; then
    printf '%s\n' 'Usage: sh install.sh [--dev]' >&2
    exit 2
fi

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
python_command=${PYTHON:-python3}
venv_dir=${YTXT_HOME:-"$HOME/.local/share/ytxt"}/venv
if [ -n "${TERMUX_VERSION:-}" ] || [ "${PREFIX:-}" = /data/data/com.termux/files/usr ]; then
    default_bin_dir=${PREFIX:?Termux PREFIX is not set}/bin
else
    default_bin_dir=$HOME/.local/bin
fi
bin_dir=${YTXT_BIN_DIR:-"$default_bin_dir"}

if ! command -v "$python_command" >/dev/null 2>&1; then
    printf 'Python not found: %s\n' "$python_command" >&2
    printf '%s\n' 'Install Python 3.10–3.14 (Termux: pkg install python python-pip).' >&2
    exit 1
fi
"$python_command" -c 'import sys; sys.exit(0 if (3, 10) <= sys.version_info[:2] < (3, 15) else "ytxt requires Python 3.10–3.14")'

if [ ! -x "$venv_dir/bin/python" ]; then
    if ! "$python_command" -m venv "$venv_dir"; then
        printf '%s\n' 'Could not create the virtual environment.' \
            'Debian/Ubuntu: sudo apt install python3-venv' \
            'Termux: pkg install python python-pip' >&2
        exit 1
    fi
fi

if [ "$editable" = true ]; then
    "$venv_dir/bin/python" -m pip install --upgrade --editable "$repo_dir"
else
    "$venv_dir/bin/python" -m pip install --upgrade "$repo_dir"
fi

mkdir -p "$bin_dir"
# Keep the previous standalone script available when migrating an existing device.
if [ -e "$bin_dir/ytxt" ] && [ ! -L "$bin_dir/ytxt" ]; then
    backup="$bin_dir/ytxt.backup.$(date +%Y%m%d%H%M%S).$$"
    mv "$bin_dir/ytxt" "$backup"
    printf 'Previous command backed up to: %s\n' "$backup"
fi
ln -sf "$venv_dir/bin/ytxt" "$bin_dir/ytxt"
printf 'Installed: %s\n' "$bin_dir/ytxt"
case ":$PATH:" in
    *":$bin_dir:"*) ;;
    *) printf 'Add this folder to your shell PATH: %s\n' "$bin_dir" ;;
esac
"$bin_dir/ytxt" --version
