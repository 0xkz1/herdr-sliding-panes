#!/usr/bin/env bash
set -euo pipefail
package_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="$(python3 "$package_dir/scripts/prepare.py" "$@")"
cd "$source_dir"
cargo build --locked --release --bin herdr --jobs "${CARGO_BUILD_JOBS:-2}"
python3 - <<'PY'
import os
from pathlib import Path
target = Path(os.environ.get("CARGO_TARGET_DIR", "target")).resolve()
print(f"Built: {target / 'release/herdr'}")
PY
