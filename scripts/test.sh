#!/usr/bin/env bash
set -euo pipefail
package_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="$(python3 "$package_dir/scripts/prepare.py" "$@")"
cd "$source_dir"
cargo fmt --all -- --check
for filter in sliding layout::tests server::headless::tests input::mouse::tests kitty_graphics::surface::tests; do
    cargo test --locked --bin herdr --jobs "${CARGO_BUILD_JOBS:-2}" "$filter" -- --test-threads=2
done
