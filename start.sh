#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
printf 'Abra http://127.0.0.1:8000 no navegador. Ctrl+C encerra o servidor.\n'
exec .venv/bin/python -m seabirds "$@"
