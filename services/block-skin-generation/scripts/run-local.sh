#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
service_dir="$(cd "$script_dir/.." && pwd)"
venv_dir="$service_dir/.venv"

if [[ ! -x "$venv_dir/bin/python" ]]; then
  echo "Local environment missing. Run scripts/bootstrap.sh first." >&2
  exit 1
fi

cd "$service_dir"
export HF_HOME="${HF_HOME:-$service_dir/.cache/huggingface}"
export PYTORCH_ENABLE_MPS_FALLBACK=1
exec "$venv_dir/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8012
