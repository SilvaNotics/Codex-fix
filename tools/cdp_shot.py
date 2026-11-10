"""通过 CDP 截取 Codex 渲染页面（不依赖窗口前台状态）。用法：python cdp_shot.py out.png"""
import asyncio, base64, json, os, sys, urllib.request
import websockets


def _port():
    here = os.path.dirname(os.path.abspath(__file__))
    for cand in (os.path.join(here, "..", "output", "logs", "cdp_port.txt"),):
        try:
            with open(cand, encoding="utf-8") as fh:
                return int(fh.read().strip())
        except Exception:
            continue
    return 9333


PORT = _port()


def wsurl():
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=5) as r:
        for t in json.load(r):
            if t.get("type") == "page" and t.get("url", "").startswith("app://"):
                return t["webSocketDebuggerUrl"]
    raise SystemExit("no app page")


async def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "shot.png"
    async with websockets.connect(wsurl(), max_size=64 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": 9, "method": "Page.bringToFront"}))
        await ws.recv()
        await asyncio.sleep(0.8)
        await ws.send(json.dumps({"id": 1, "method": "Page.captureScreenshot",
                                  "params": {"format": "png", "captureBeyondViewport": False}}))
        while True:
            m = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            if m.get("id") == 1:
                open(out, "wb").write(base64.b64decode(m["result"]["data"]))
                print("SAVED", out)
                return


asyncio.run(main())
