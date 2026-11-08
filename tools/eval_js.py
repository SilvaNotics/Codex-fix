"""在正在运行的 Codex 渲染进程里执行一段 JS（读 CDP 端口 9333）。

用法：python eval_js.py 文件.js     或     python eval_js.py -e "1+1"
"""
import asyncio, json, sys, urllib.request
import websockets

PORT = 9333


def wsurl():
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=5) as r:
        for t in json.load(r):
            if t.get("type") == "page" and t.get("url", "").startswith("app://"):
                return t["webSocketDebuggerUrl"]
    raise SystemExit("no app page")


async def main():
    if sys.argv[1] == "-e":
        expr = sys.argv[2]
    else:
        expr = open(sys.argv[1], encoding="utf-8").read()
    async with websockets.connect(wsurl(), max_size=64 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Runtime.evaluate",
                                  "params": {"expression": expr, "returnByValue": True,
                                             "awaitPromise": True}}))
        while True:
            m = json.loads(await asyncio.wait_for(ws.recv(), timeout=60))
            if m.get("id") == 1:
                r = m["result"]
                if "exceptionDetails" in r:
                    print("EXCEPTION:", json.dumps(r["exceptionDetails"], ensure_ascii=False)[:800])
                print(json.dumps(r["result"].get("value"), ensure_ascii=False))
                return


asyncio.run(main())
