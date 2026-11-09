"""Manual integration: quits Codex, checks port release, restarts it.

Run only when no task is active in Codex. No credentials or chat text collected.
"""
import asyncio
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import websockets

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('launcher', ROOT / 'codex_zh_launch.py')
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)

def port_free(port):
    with socket.socket() as sock:
        if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False

async def close_browser(port):
    with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/version', timeout=3) as response:
        url = json.load(response)['webSocketDebuggerUrl']
    async with websockets.connect(url, close_timeout=2) as ws:
        await ws.send(json.dumps({'id': 1, 'method': 'Browser.close'}))
        try:
            await asyncio.wait_for(ws.recv(), 3)
        except (websockets.ConnectionClosed, TimeoutError):
            pass

def run():
    results = []
    for mode in ['graceful', 'process-tree']:
        subprocess.run([sys.executable, str(ROOT/'codex_zh_launch.py')], check=True, timeout=200)
        report = json.loads((ROOT/'verification.json').read_text(encoding='utf-8'))
        assert report['status'] == 'passed'
        port = report['port']
        assert not port_free(port), 'live app must own port'
        if mode == 'graceful':
            asyncio.run(close_browser(port))
            time.sleep(2)
            # Codex keeps a background process when all windows close.
            # Record this separately from an actual process exit.
            print(json.dumps(dict(exit='window-only', port=port,
                                  codex_running=launcher.codex_running(),
                                  port_held=not port_free(port))), flush=True)
            assert launcher.kill_codex(), 'background app did not exit'
        else:
            assert launcher.kill_codex(), 'process tree did not exit'
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not port_free(port):
            time.sleep(0.5)
        released = port_free(port)
        running = launcher.codex_running()
        row = dict(exit=mode, port=port, exclusive_rebind=released, codex_running=running)
        results.append(row)
        print(json.dumps(row), flush=True)
        assert released and not running, 'port or process remained after full exit'
        # Verify-only must fail without restarting a closed app.
        check = subprocess.run([sys.executable, str(ROOT/'codex_zh_launch.py'), '--verify-only'], timeout=60)
        assert check.returncode != 0
        assert json.loads((ROOT/'verification.json').read_text(encoding='utf-8'))['status'] == 'failed'
    subprocess.run([sys.executable, str(ROOT/'codex_zh_launch.py')], check=True, timeout=200)
    print(json.dumps({'results': results, 'final_restart': 'passed'}))

if __name__ == '__main__':
    run()
