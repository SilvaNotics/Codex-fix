"""用原版 Codex 桌面版启动，并在渲染进程挂载前把 Statsig 层参数 enable_i18n 打通。

不改任何文件：只是给原版 exe 加 --remote-debugging-port，启动后连 CDP，
在页面里注入补丁（getLayer("72216192").get("enable_i18n") -> true）。
配合 config.toml 里的 [desktop] localeOverride = "zh-CN" 即可得到中文界面。

用法：
    python codex_zh_launch.py        # 未运行 -> 启动原版并注入；已由本启动器启动 -> 只重新注入

版本自适应：每次运行都会重新解析 WindowsApps 下的 OpenAI.Codex_*（取最高版本），
App 更新后不用改脚本。若新版本改了开关实现，补丁会静默失效（界面回英文），不会损坏任何东西。
"""
import asyncio, glob, json, os, re, subprocess, time, traceback, urllib.request
import socket
import websockets

PORT = 0                      # 运行时决定：新启动用系统分配端口，已有实例用探测到的端口
PORT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cdp_port.txt")
LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "launch.log")


def log(msg):
    """pythonw 下没有控制台，出问题只能靠日志排查。"""
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + str(msg) + "\n")
    except Exception:
        pass


def find_exe():
    """取当前已注册的 MSIX 包目录（WindowsApps 不能列目录，只能问 Appx）。"""
    ps = ("$p = Get-AppxPackage -Name OpenAI.Codex | Sort-Object Version | Select-Object -Last 1; "
          "if ($p) { Join-Path $p.InstallLocation 'app\\ChatGPT.exe' }")
    try:
        out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=40, creationflags=0x08000000)
        p = (out.stdout or "").strip()
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    for root in dict.fromkeys([os.environ.get("ProgramFiles", r"C:\Program Files"),
                               os.environ.get("ProgramW6432", r"C:\Program Files")]):
        pat = os.path.join(root, "WindowsApps", "OpenAI.Codex_*", "app", "ChatGPT.exe")
        hits = glob.glob(pat)
        if hits:
            def ver(x):
                m = re.search(r"OpenAI\.Codex_([0-9.]+)_", x)
                return tuple(int(i) for i in m.group(1).split(".")) if m else (0,)
            return max(hits, key=ver)
    return None


EXE = find_exe()

PATCH = r"""
(() => {
  const LAYER = "72216192";
  // computer_use / browser 的 Statsig 开关（远端 gate，无登录时恒 false）
  const GATES = ["1506311413", "410065390", "410262010"];
  if (window.__zhApplied) { return "already"; }
  window.__zhApplied = true;
  let ns;
  function fakeGate(s) {
    return { name: s, value: true, ruleID: "local", ruleIDString: "local",
             details: { reason: "override" }, evaluationDetails: { reason: "override" } };
  }
  function installOverride(inst) {
    if (!inst || inst.__zhOA) return;
    inst.overrideAdapter = {
      getGateOverride: function (gate) {
        var n = gate && gate.name;
        if (GATES.indexOf(String(n)) >= 0) return fakeGate(String(n));
        return null;
      },
      getDynamicConfigOverride: function () { return null; },
      getExperimentOverride: function () { return null; },
      getLayerOverride: function () { return null; },
      getParameterStoreOverride: function () { return null; },
    };
    inst.__zhOA = true;
    try { inst._memoCache = {}; } catch (e) {}
  }
  function patchProto(p) {
    if (!p || p.__zhPatched || typeof p.get !== "function") return;
    const og = p.get;
    p.get = function (k, d) {
      if (this && this.name === LAYER && k === "enable_i18n") return true;
      return og.call(this, k, d);
    };
    p.__zhPatched = true;
  }
  function patchNs(v) {
    if (!v) return;
    try {
      const C = v.StatsigClient;
      if (C && C.prototype) {
        if (typeof C.prototype.getLayer === "function" && !C.prototype.__zhGL) {
          const ogL = C.prototype.getLayer;
          C.prototype.getLayer = function (name, fb, opts) {
            const l = ogL.call(this, name, fb, opts);
            try { l && patchProto(Object.getPrototypeOf(l)); } catch (e) {}
            return l;
          };
          C.prototype.__zhGL = true;
        }
        patchProto(C.prototype);
      }
      const inst = v.firstInstance;
      if (inst) installOverride(inst);
      if (inst && typeof inst.getLayer === "function" && !inst.__zh) {
        const ogI = inst.getLayer.bind(inst);
        inst.getLayer = function (name, fb, opts) {
          const l = ogI(name, fb, opts);
          if (name === LAYER && l && typeof l.get === "function" && !l.__zh) {
            const g = l.get.bind(l);
            l.get = function (k, d) { return k === "enable_i18n" ? true : g(k, d); };
            l.__zh = true;
          }
          return l;
        };
        inst.__zh = true;
      }
    } catch (e) {}
  }
  try {
    Object.defineProperty(window, "__STATSIG__", {
      configurable: true,
      get() { if (ns) patchNs(ns); return ns; },
      set(v) { ns = v; patchNs(v); },
    });
  } catch (e) {}
  const iv = setInterval(() => { if (ns) patchNs(ns); }, 2);
  setTimeout(() => clearInterval(iv), 120000);
})();
"""

STATE = r"""
(() => {
  const t = document.body.innerText || "";
  let ok = null;
  try { ok = window.__STATSIG__.firstInstance.getLayer("72216192", {}).get("enable_i18n", false); } catch (e) { ok = "no-client"; }
  return JSON.stringify({ patched: window.__zhApplied === true, enable_i18n: ok, lang: document.documentElement.lang, cjk: (t.match(/[\u4e00-\u9fff]/g) || []).length, len: t.length });
})()
"""


def http_json(path, timeout=2):
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=timeout) as r:
        return json.load(r)


def cdp_alive(port, timeout=1.0):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=timeout) as r:
            json.load(r)
        return True
    except Exception:
        return False


def pick_port():
    """挑一个能用的 CDP 端口（退路用）。

    坑：上一轮应用被强杀后，监听套接字可能被某个继承了句柄的子进程占着（netstat 里
    OwningProcess 指向一个已退出的 PID），此时端口既连不上、又 bind 不了。
    只认「CDP 有应答」或「能 bind」，其余一律跳过并顺延。
    """
    for p in range(9333, 9351):
        if cdp_alive(p):
            return p
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    return None


_FAM = None


def pkg_family():
    """包族名（带哈希的那个），用来定位 MSIX 的 LocalCache 目录。"""
    global _FAM
    if _FAM is None:
        try:
            ps = ("(Get-AppxPackage -Name OpenAI.Codex | Sort-Object Version | Select-Object -Last 1)"
                  ".PackageFamilyName")
            _FAM = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                                  capture_output=True, text=True, timeout=40,
                                  creationflags=0x08000000).stdout.strip()
        except Exception:
            _FAM = ""
    return _FAM


def devtools_file(fam):
    """Chromium 用 --remote-debugging-port=0 启动时，会把真实端口写进 DevToolsActivePort。"""
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Packages", fam, "LocalCache")
    cands = [
        os.path.join(base, "Roaming", "Codex", "web", "Codex", "DevToolsActivePort"),
        os.path.join(base, "Roaming", "Codex", "DevToolsActivePort"),
        os.path.join(os.path.expanduser("~"), ".codex", "DevToolsActivePort"),
    ]
    for c in cands:
        if os.path.isdir(os.path.dirname(c)):
            return c
    return cands[0]


def read_devtools_port(path):
    try:
        with open(path, encoding="utf-8") as f:
            first = f.readline().strip()
        return int(first) if first.isdigit() and int(first) > 0 else None
    except Exception:
        return None


def has_app_page(port, timeout=1.0):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=timeout) as r:
            targets = json.load(r)
        return any(t.get("type") == "page" and t.get("url", "").startswith("app://")
                   for t in targets)
    except Exception:
        return False


def find_existing_cdp():
    """已经有一个带调试端口的实例在跑 → 返回它的端口（优先上次记录 / DevToolsActivePort）。"""
    cands = []
    try:
        with open(PORT_FILE, encoding="utf-8") as f:
            cands.append(int(f.read().strip()))
    except Exception:
        pass
    fam = pkg_family()
    if fam:
        p = read_devtools_port(devtools_file(fam))
        if p:
            cands.append(p)
    cands += list(range(9333, 9351))
    seen = set()
    for p in cands:
        if p in seen:
            continue
        seen.add(p)
        if has_app_page(p):
            return p
    return None


def save_port(p):
    try:
        with open(PORT_FILE, "w", encoding="utf-8") as f:
            f.write(str(p))
    except Exception:
        pass


def page_ws():
    try:
        targets = http_json("/json/list")
    except Exception:
        return None
    for t in targets:
        if t.get("type") == "page" and t.get("url", "").startswith("app://"):
            return t["webSocketDebuggerUrl"]
    return None


def codex_running():
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "(Get-Process ChatGPT -ErrorAction SilentlyContinue | Measure-Object).Count"],
            capture_output=True, text=True, timeout=20, creationflags=0x08000000)
        return int((out.stdout or "0").strip() or 0) > 0
    except Exception:
        return False


CONFIG = os.path.join(os.path.expanduser("~"), ".codex", "config.toml")
NEED_PLUGINS = ["computer-use@openai-bundled", "chrome@openai-bundled"]


def ensure_config():
    """CC Switch 切换供应商时会用自己那份最小模板整份覆盖 config.toml，
    把 [desktop] localeOverride / 插件 enabled / marketplace 一起冲掉。
    这里在启动前按需把这些项补回来（幂等；改动前备份；改完先做 TOML 校验）。"""
    try:
        with open(CONFIG, encoding="utf-8") as f:
            src = f.read()
    except FileNotFoundError:
        return "没有 config.toml，跳过"
    orig = src
    fixes = []

    if not re.search(r"(?m)^\s*localeOverride\s*=", src):
        if re.search(r"(?m)^\[desktop\]\s*$", src):
            src = re.sub(r"(?m)^(\[desktop\]\s*)$", r'\1\nlocaleOverride = "zh-CN"', src, count=1)
        else:
            src = src.rstrip("\n") + '\n\n[desktop]\nlocaleOverride = "zh-CN"\n'
        fixes.append("localeOverride=zh-CN")

    for plug in NEED_PLUGINS:
        hdr = '[plugins."%s"]' % plug
        m = re.search(r"(?ms)^" + re.escape(hdr) + r"\s*\n(.*?)(?=^\[|\Z)", src)
        if not m:
            src = src.rstrip("\n") + "\n\n" + hdr + "\nenabled = true\n"
            fixes.append(plug + " 整段缺失->补回")
            continue
        body = m.group(1)
        if re.search(r"(?m)^\s*enabled\s*=", body):
            new_body = re.sub(r"(?m)^\s*enabled\s*=.*$", "enabled = true", body, count=1)
        else:
            new_body = "enabled = true\n" + body
        if new_body != body:
            src = src[:m.start(1)] + new_body + src[m.end(1):]
            fixes.append(plug + " -> enabled=true")

    mp = os.path.join(os.path.expanduser("~"), ".codex", ".tmp", "bundled-marketplaces", "openai-bundled")
    if "[marketplaces.openai-bundled]" not in src and os.path.isdir(mp):
        src = (src.rstrip("\n") + "\n\n[marketplaces.openai-bundled]\nsource_type = \"local\"\n"
               "source = '\\\\?\\" + mp + "'\n")
        fixes.append("marketplaces.openai-bundled 补回")

    if src == orig:
        if re.search(r"(?m)^\s*requires_openai_auth\s*=\s*true\s*$", src):
            return "配置完好，无需修补（注意：requires_openai_auth = true，启动后可能停在登录页）"
        return "配置完好，无需修补"

    try:
        import tomllib
        tomllib.loads(src)
    except Exception as e:
        return "修补后的 TOML 校验失败，未写入: %r" % (e,)

    with open(CONFIG + ".bak-codexzh", "w", encoding="utf-8", newline="\n") as f:
        f.write(orig)
    with open(CONFIG, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    return "已修补: " + ", ".join(fixes)


def spawn_app():
    """优先用 AppX 激活启动（进程带包身份 → 任务栏/开始菜单用 MSIX 官方图标素材，清晰），
    同时把 --remote-debugging-port 作为激活参数传进去。失败则回退为直接起 exe。"""
    try:
        import importlib.util
        here = os.path.dirname(os.path.abspath(__file__))
        spec = importlib.util.spec_from_file_location("activate_codex",
                                                      os.path.join(here, "activate_codex.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fam = pkg_family()
        if fam:
            hr, pid = mod.activate(fam + "!App", f"--remote-debugging-port={PORT}")
            log(f"AppX 激活 hr=0x{hr & 0xFFFFFFFF:08X} pid={pid}")
            if hr == 0 and pid:
                return "activation"
    except Exception:
        log("AppX 激活失败，回退直接启动:\n" + traceback.format_exc())
    env = dict(os.environ, CODEX_ELECTRON_ENABLE_WINDOWS_COMPUTER_USE="1")
    subprocess.Popen([EXE, f"--remote-debugging-port={PORT}"], env=env, close_fds=True)
    return "popen"


async def main():
    global PORT
    if not EXE:
        raise SystemExit("没找到 OpenAI.Codex 安装目录（WindowsApps 下无 OpenAI.Codex_*）")

    log(ensure_config())

    launched = False
    existing = await asyncio.to_thread(find_existing_cdp)
    if existing:
        PORT = existing
        log(f"已有实例带调试端口 {PORT}，直接注入")
    else:
        if codex_running():
            raise SystemExit(
                "Codex 已经在运行，但不是通过本启动器启动的（没有调试端口）。\n"
                "请先完全退出 Codex（连同托盘图标/后台进程），再运行本启动器。")

        # 新启动：让系统分配端口（--remote-debugging-port=0），
        # 这样即使旧实例被强杀后留下「僵尸监听」，也不会撞端口。
        fam = await asyncio.to_thread(pkg_family)
        dev = devtools_file(fam) if fam else None
        if dev:
            try:
                os.remove(dev)          # 删掉上一轮遗留，避免读到旧端口
            except OSError:
                pass
        PORT = 0
        how = await asyncio.to_thread(spawn_app)
        log("启动方式: " + how)
        launched = True

        got = None
        for i in range(240):
            if dev:
                got = read_devtools_port(dev)
                if got:
                    break
            if i and i % 20 == 0:
                log(f"等待 DevToolsActivePort ... 第 {i // 2} 秒")
            await asyncio.sleep(0.5)
        if got:
            PORT = got
            log(f"系统分配调试端口 {PORT}")
        else:
            log("没等到 DevToolsActivePort，退回固定端口段探测")
            PORT = await asyncio.to_thread(pick_port) or 0
            if not PORT:
                raise SystemExit("找不到可用调试端口")
            log(f"使用调试端口 {PORT}")
    save_port(PORT)

    if not cdp_alive(PORT):
        for i in range(240):
            if cdp_alive(PORT):
                break
            if i and i % 20 == 0:
                log(f"等待调试端口 {PORT} ... 第 {i // 2} 秒")
            await asyncio.sleep(0.5)
        else:
            raise SystemExit(f"调试端口 {PORT} 在 120 秒内没起来（应用可能启动失败）")

    url = None
    for _ in range(200):
        url = page_ws()
        if url:
            break
        await asyncio.sleep(0.2)
    if not url:
        raise SystemExit("找不到页面目标")

    async with websockets.connect(url, max_size=64 * 1024 * 1024) as ws:
        await ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
        await ws.recv()
        await ws.send(json.dumps({"id": 2, "method": "Page.addScriptToEvaluateOnNewDocument", "params": {"source": PATCH}}))
        await ws.recv()
        await ws.send(json.dumps({"id": 3, "method": "Runtime.evaluate", "params": {"expression": PATCH, "returnByValue": True}}))
        await ws.recv()
        print("已启动原版 Codex 并注入" if launched else "Codex 已在运行，已注入")

        for i in range(60):
            await asyncio.sleep(1)
            await ws.send(json.dumps({"id": 100 + i, "method": "Runtime.evaluate", "params": {"expression": STATE, "returnByValue": True}}))
            while True:
                m = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
                if m.get("id") == 100 + i:
                    raw = m["result"]["result"].get("value") or "{}"
                    v = json.loads(raw)
                    if v.get("enable_i18n") is True and v.get("cjk", 0) > 20:
                        print("补丁生效，界面已是中文：", json.dumps(v, ensure_ascii=False))
                        return
                    break
        print("注入完成（30 秒内未确认中文渲染）")


try:
    log("---- 启动器开始运行 ----")
    asyncio.run(main())
    log("---- 结束 ----")
except BaseException as e:
    log("失败: " + repr(e) + "\n" + traceback.format_exc())
    raise

