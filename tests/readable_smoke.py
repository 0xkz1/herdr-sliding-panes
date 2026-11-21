#!/usr/bin/env python3
"""Verify real PTY widths with an isolated TUI; no agents or production panes.

Run: python3 tests/readable_smoke.py /absolute/path/to/herdr
"""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import sys
import tempfile
import termios
import time


def main():
    binary = str(Path(sys.argv[1]).resolve())
    with tempfile.TemporaryDirectory(prefix="herdr-readable-") as directory:
        root = Path(directory)
        config = root / "config/herdr"
        config.mkdir(parents=True)
        (config / "config.toml").write_text('''onboarding = false
[update]
version_check = false
manifest_check = false
[ui]
sidebar_start_collapsed = true
sidebar_collapsed_mode = "hidden"
mobile_width_threshold = 0
pane_borders = "always"
pane_gaps = true
prompt_new_workspace_name = false
prompt_new_tab_name = false
[ui.sound]
enabled = false
[terminal]
default_shell = "/bin/sh"
''')
        (root / "home").mkdir()
        (root / "runtime").mkdir(mode=0o700)
        env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(root / "home"),
               "XDG_RUNTIME_DIR": str(root / "runtime"), "LANG": "C.UTF-8"}
        env.update(XDG_CONFIG_HOME=str(root / "config"), XDG_STATE_HOME=str(root / "state"),
                   XDG_DATA_HOME=str(root / "data"), TERM="xterm-256color",
                   HERDR_CONFIG_PATH=str(config / "config.toml"))
        command = [binary, "--session", "readable-smoke"]
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 120, 0, 0))
        process = subprocess.Popen(command, env=env, cwd=root, stdin=slave,
                                   stdout=slave, stderr=slave, start_new_session=True)
        output = bytearray()

        def pump(seconds=.2):
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                if select.select([master], [], [], min(.05, end - time.monotonic()))[0]:
                    try:
                        data = os.read(master, 65536)
                    except OSError:
                        return
                    if not data:
                        return
                    output.extend(data)

        def api(*args):
            result = subprocess.run(command + list(args), env=env, cwd=root,
                                    capture_output=True, text=True, timeout=10, check=True)
            return json.loads(result.stdout)["result"]

        def widths(ids):
            result = {}
            for pid in ids:
                shell = api("pane", "process-info", "--pane", pid)["process_info"]["shell_pid"]
                fd = os.open(f"/proc/{shell}/fd/0", os.O_RDONLY | os.O_NOCTTY)
                try:
                    result[pid] = struct.unpack("HHHH", fcntl.ioctl(
                        fd, termios.TIOCGWINSZ, b"\0" * 8))[1]
                finally:
                    os.close(fd)
            return result

        try:
            for _ in range(40):
                pump()
                try:
                    panes = api("pane", "list")["panes"]
                    break
                except (subprocess.SubprocessError, json.JSONDecodeError, KeyError):
                    continue
            else:
                raise RuntimeError("isolated server did not start")
            if not panes:
                api("workspace", "create", "--cwd", str(root), "--label", "Width smoke")
                panes = api("pane", "list")["panes"]
            first = panes[0]["pane_id"]
            tab = panes[0]["tab_id"]
            os.write(master, b"\x02S")
            target = first
            for _ in range(6):
                target = api("pane", "split", "--pane", target, "--direction", "right",
                             "--ratio", "0.9", "--no-focus")["pane"]["pane_id"]
                pump()
            pump(.8)
            identities = {p["pane_id"]: p["terminal_id"] for p in api("pane", "list")["panes"]}
            before = widths(identities)
            assert min(before.values()) >= 45, before
            api("tab", "create", "--label", "Single pane", "--focus")
            pump(.8)
            hidden = widths(identities)
            assert hidden == before, (before, hidden)
            # A real client resize while this tab is hidden must preserve it.
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 40, 80, 0, 0))
            os.kill(process.pid, signal.SIGWINCH)
            pump(.6)
            assert widths(identities) == before
            api("tab", "focus", tab)
            pump(.8)
            narrow_host = widths(identities)
            assert min(narrow_host.values()) >= 45, narrow_host
            current = {p["pane_id"]: p["terminal_id"] for p in api("pane", "list")["panes"]}
            assert all(current[pid] == terminal for pid, terminal in identities.items())
            print(json.dumps({"panes": len(identities), "before": before, "hidden": hidden,
                              "host_80_columns": narrow_host, "terminal_ids_preserved": True}))
        finally:
            subprocess.run(command + ["session", "stop", "readable-smoke", "--json"],
                           env=env, cwd=root, capture_output=True, timeout=10)
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
            os.close(slave)
            os.close(master)


if __name__ == "__main__":
    main()
