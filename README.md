# Herdr Sliding Panes

[![CI](https://github.com/0xkz1/herdr-sliding-panes/actions/workflows/ci.yml/badge.svg)](https://github.com/0xkz1/herdr-sliding-panes/actions/workflows/ci.yml)

Keep Herdr panes on a wide horizontal surface and scroll the viewport instead
of squeezing every pane into the visible terminal. A bottom overview bar shows
pane positions, agent labels, the focused pane and the current scroll position.

Herdrのペインを横に広い仮想領域へ配置し、横スクロールで移動する改修です。
下部に配置・エージェント名・現在位置のインジケーターを表示します。

This repository contains a **source patchset for Herdr v0.9.5**, build helpers and
tests. It is not an installable Herdr plugin and is not an official release.

## What it adds

- A client-local horizontal viewport over Herdr's existing tiled pane surface.
- Horizontal wheel/trackpad scrolling, Shift+wheel, and a clickable bottom rail.
- Automatic reveal when focus moves to an off-screen pane.
- Pane badges and focused-pane information in the bottom overview bar.
- Mouse, selection, links and graphics coordinates adjusted for the viewport.
- Saved per-endpoint on/off preference; no protocol version change.
- Readable width floors when space permits, and retained PTY widths for hidden
  tabs so changing the visible tab does not collapse their terminals.

Turning the mode off restores the ordinary viewport. Existing terminals and
their conversation state stay attached to their running processes.

## Build

Requirements: Git, Python 3, Rust **1.99.1**, Zig **0.16.0**, a C compiler and the
normal native dependencies required by upstream Herdr. Linux is the validated
platform for this patchset; macOS and Windows have not been validated here.

```sh
git clone https://github.com/0xkz1/herdr-sliding-panes.git
cd herdr-sliding-panes
./scripts/build.sh
```

The helper checks out upstream **v0.9.5**, verifies commit
`2ecf19a92fc3a7fff75b6ce3655ef04f4625ec01`, checks the patch's SHA-256 and applies
it. The built binary is `.build/herdr/target/release/herdr` by default.
`ZIG=/path/to/zig` selects a Zig executable; `CARGO_TARGET_DIR` and
`CARGO_BUILD_JOBS` are respected. Build parallelism defaults to two jobs.

The helpers never install a binary, replace your existing Herdr executable,
restart a server or migrate sessions. Try the binary in a separate named session:

```sh
.build/herdr/target/release/herdr --session sliding-demo
```

For an existing clean checkout of the exact upstream revision:

```sh
./scripts/build.sh --source /path/to/herdr-v0.9.5
```

Preparation refuses a different base or unrelated local edits. Re-running it on
the exact prepared patch is supported. Upstream `herdr update` installs an
upstream binary, which does not preserve this patchset.

## Controls

With Herdr's default prefix, press **Ctrl+B**, release both keys, then
**Shift+S** (uppercase `S`) to toggle Sliding Panes. If your prefix is different,
use that prefix followed by uppercase `S`. The global menu also contains
**sliding panes**.

- Scroll horizontally over the pane area, or hold Shift while scrolling vertically.
- Scroll over the bottom bar to pan the viewport.
- Click the rail to jump to a position.
- Use normal pane-focus controls to reveal the selected pane.

The preference is saved per endpoint in Herdr's `client-shell` state directory.
It defaults to off when the saved setting is absent. The bottom bar is visible
while the mode is on.

## Tests

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
./scripts/test.sh
./scripts/build.sh
python3 tests/sliding_smoke.py .build/herdr/target/release/herdr
python3 tests/readable_smoke.py .build/herdr/target/release/herdr
```

Rust tests cover viewport geometry, focus reveal, scrolling bounds, clipped
input/selection/graphics, persistence and pane-width behavior. The Linux smoke
tests launch disposable servers and PTYs with isolated home/config/state/data
directories. They exercise real scrolling, resizing, reconnects and hidden-tab
PTY widths without touching existing sessions. Temporary output remains under
the system temporary directory for inspection.

## Scope and limits

- The patch is pinned to **v0.9.5**; applying it to newer releases is untested.
- The virtual surface is bounded by Herdr's geometry limits, including a
  4096-column cap. It is not an unbounded canvas.
- Split-divider dragging keeps the virtual surface width fixed and changes the
  existing BSP split ratios. Independent per-pane canvas expansion is not provided.
- The width floor also affects ordinary tiled layouts when the surface has
  enough room: it reserves 49 outer columns per horizontal leaf while keeping
  preferred split ratios. It cannot guarantee readable widths on every geometry.
- Workspace sidebar grouping, personal agent aliases, routing, account settings
  and unrelated local server patches are excluded.
- This repository provides source and build instructions, not prebuilt binaries.

## Attribution

Built on [Herdr](https://github.com/herdrdev/herdr). The scrolling-tiling idea also
appears in projects such as [niri](https://github.com/YaLTeR/niri) and
[PaperWM](https://github.com/paperwm/PaperWM); this project implements that
interaction within Herdr's TUI.

Apache-2.0; see [LICENSE](LICENSE) and [NOTICE](NOTICE).
