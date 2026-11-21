#!/usr/bin/env python3
"""Exercise the patched TUI in a disposable, isolated Herdr session."""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import struct
import subprocess
import sys
import termios
import tempfile
import time

binary = Path(sys.argv[1]).resolve()
root = Path(tempfile.mkdtemp(prefix='hslide-'))
root.mkdir(parents=True, exist_ok=True)
config = root / 'config' / 'herdr'
config.mkdir(parents=True, exist_ok=True)
(config / 'config.toml').write_text('''onboarding = false
[update]
version_check = false
manifest_check = false
[ui]
sidebar_start_collapsed = true
sidebar_collapsed_mode = "hidden"
mobile_width_threshold = 0
pane_borders = "always"
pane_gaps = false
prompt_new_workspace_name = false
prompt_new_tab_name = false
[ui.sound]
enabled = false
[terminal]
default_shell = "/bin/sh"
''')
(root / 'home').mkdir()
(root / 'runtime').mkdir(mode=0o700)
env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(root / 'home'),
       'XDG_RUNTIME_DIR': str(root / 'runtime'), 'LANG': 'C.UTF-8'}
env.update(XDG_CONFIG_HOME=str(root / 'config'), XDG_STATE_HOME=str(root / 'state'),
           XDG_DATA_HOME=str(root / 'data'), TERM='xterm-256color')
session = 'sliding-smoke'
cmd = [str(binary), '--session', session]
master, slave = pty.openpty()
slave_path = os.ttyname(slave)
fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 28, 120, 0, 0))
process = subprocess.Popen(cmd, env=env, stdin=slave, stdout=slave, stderr=slave,
                           start_new_session=True, cwd=root)
os.close(slave)
output = bytearray()
results = {}

def pump(seconds=0.2):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if select.select([master], [], [], min(0.1, deadline - time.monotonic()))[0]:
            try:
                data = os.read(master, 65536)
            except OSError:
                return
            if not data:
                return
            output.extend(data)

def api(*args):
    result = subprocess.run(cmd + list(args), env=env, capture_output=True, text=True, timeout=8)
    if result.returncode:
        raise RuntimeError(f'{args[0]} {args[1]} failed: {result.stderr[-500:]}')
    return json.loads(result.stdout)

def layout(pane):
    return api('pane', 'layout', '--pane', pane)['result']['layout']

def await_width(pane, width):
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        pump()
        view = layout(pane)
        if view['area']['width'] == width:
            return view
    raise AssertionError(f'expected width {width}, received {view["area"]}')

try:
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        pump()
        try:
            state = api('api', 'snapshot')['result']
            break
        except (RuntimeError, json.JSONDecodeError):
            pass
    else:
        raise RuntimeError('isolated server did not become ready')
    panes = api('pane', 'list')['result']['panes']
    if not panes:
        created = api('workspace', 'create', '--label', 'Sliding smoke', '--cwd', str(root))['result']
        first = created['root_pane']['pane_id']
    else:
        first = panes[0]['pane_id']
    second = api('pane', 'split', '--pane', first, '--direction', 'right', '--ratio', '0.333', '--no-focus')['result']['pane']['pane_id']
    third = api('pane', 'split', '--pane', second, '--direction', 'right', '--no-focus')['result']['pane']['pane_id']
    pump(0.8)
    normal = await_width(first, 120)
    results['normal_columns'] = normal['area']['width']
    ids_before = sorted(pane['pane_id'] for pane in normal['panes'])
    terminals_before = {p['pane_id']: p['terminal_id'] for p in api('pane', 'list')['result']['panes']}
    shell_pids_before = {pid: api('pane', 'process-info', '--pane', pid)['result']['process_info']['shell_pid']
                         for pid in ids_before}
    os.write(master, b'\x02S')
    wide = await_width(first, 288)
    pump(0.6)
    assert b'SLIDE' in output, 'TUI did not render its sliding control'
    results['sliding_columns'] = wide['area']['width']
    results['pane_columns'] = [pane['rect']['width'] for pane in wide['panes']]
    # Scroll a real SGR mouse wheel right. Terminal output confirms a local repaint.
    before = len(output)
    os.write(master, b'\x1b[<67;10;10M')
    pump(0.5)
    assert len(output) > before, 'horizontal wheel did not repaint'
    results['horizontal_wheel_repaint'] = True
    # The first divider is at virtual column 96. The wheel moved the viewport
    # eight columns, so its visible column is 88 (SGR coordinates are one-based).
    split = wide['splits'][0]
    divider = round(split['rect']['width'] * split['ratio'])
    start = divider - 8 + 1
    os.write(master, f'\x1b[<0;{start};10M'.encode())
    os.write(master, f'\x1b[<32;{start + 12};10M'.encode())
    pump(0.5)
    dragged = layout(first)
    # Divider dragging retains Herdr's BSP semantics on a fixed virtual surface.
    expected = (divider + 12) / wide['area']['width']
    assert dragged['area'] == wide['area'], (wide['area'], dragged['area'])
    assert dragged['panes'][0]['rect']['width'] == divider + 12
    assert abs(dragged['splits'][0]['ratio'] - expected) < 0.001, (
        'scrolled divider drag did not resize', dragged['splits'])
    # A final release at a new position must be applied even between drag ticks.
    os.write(master, f'\x1b[<0;{start + 20};10m'.encode())
    pump(0.5)
    resized = layout(first)
    final_ratio = (divider + 20) / wide['area']['width']
    assert resized['area'] == wide['area']
    assert [p['rect']['width'] for p in resized['panes']] == [116, 86, 86]
    assert abs(resized['splits'][0]['ratio'] - final_ratio) < 0.001
    results['scrolled_split_drag'] = {
        'initial_ratio': split['ratio'],
        'drag_ratio': dragged['splits'][0]['ratio'],
        'release_ratio': resized['splits'][0]['ratio'],
    }
    api('pane', 'focus', '--pane', first, '--direction', 'right')
    pump(0.6)
    assert layout(first)['focused_pane_id'] == second
    api('pane', 'focus', '--pane', second, '--direction', 'right')
    pump(0.6)
    assert layout(first)['focused_pane_id'] == third
    results['focus_moves_to_third'] = True
    # Divider ratios, terminal IDs and shell processes survive a client reconnect.
    os.write(master, b'\x02q')
    pump(0.3)
    process.wait(timeout=5)
    slave = os.open(slave_path, os.O_RDWR)
    process = subprocess.Popen(cmd, env=env, stdin=slave, stdout=slave, stderr=slave,
                               start_new_session=True, cwd=root)
    os.close(slave)
    reconnected = await_width(first, resized['area']['width'])
    assert [s['ratio'] for s in reconnected['splits']] == [s['ratio'] for s in resized['splits']]
    assert {p['pane_id']: p['terminal_id'] for p in api('pane', 'list')['result']['panes']} == terminals_before
    assert {pid: api('pane', 'process-info', '--pane', pid)['result']['process_info']['shell_pid']
            for pid in ids_before} == shell_pids_before
    results['split_ratios_and_processes_survive_reconnect'] = True
    os.write(master, b'\x02S')
    restored = await_width(first, 120)
    assert sorted(pane['pane_id'] for pane in restored['panes']) == ids_before
    assert [split['ratio'] for split in restored['splits']] == [split['ratio'] for split in resized['splits']]
    results['normal_restored_and_ids_preserved'] = True
    os.write(master, b'\x02q')
    pump(0.6)
    process.wait(timeout=5)
    assert process.returncode == 0
    results['client_exit'] = process.returncode
    results['artifacts'] = str(root)
    (root / 'result.json').write_text(json.dumps(results, indent=2))
    print(json.dumps(results))
finally:
    (root / 'client.ansi').write_bytes(output)
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=5)
    subprocess.run([str(binary), 'session', 'stop', session, '--json'], env=env, capture_output=True, timeout=8)
    os.close(master)
