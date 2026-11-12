"""用原版 Codex 桌面版启动，并在渲染进程挂载前把 Statsig 层参数 enable_i18n 打通。

不改任何文件：只是给原版 exe 加 --remote-debugging-port，启动后连 CDP，
在页面里注入补丁（getLayer("72216192").get("enable_i18n") -> true）。
配合 config.toml 里的 [desktop] localeOverride = "zh-CN" 即可得到中文界面。

用法：
    python codex_zh_launch.py        # 未运行 -> 启动原版并注入；已由本启动器启动 -> 只重新注入

版本自适应：每次运行都会重新解析 WindowsApps 下的 OpenAI.Codex_*（取最高版本），
App 路径自动发现；更新后先检查补丁目标，再核验开关与真实导航，失败会报告而非静默成功。
"""
import asyncio, glob, json, os, re, subprocess, time, traceback, urllib.request
import websockets

PORT = 0                      # 运行时决定：新启动用系统分配端口，已有实例用探测到的端口
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(PROJECT_ROOT, "output")
LOG_DIR = os.path.join(OUTPUT, "logs")
BACKUP_DIR = os.path.join(OUTPUT, "backups")
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
PORT_FILE = os.path.join(LOG_DIR, "cdp_port.txt")
LOG = os.path.join(LOG_DIR, "launch.log")


def log(msg):
    """pythonw 下没有控制台，出问题只能靠日志排查。"""
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(time.strftime("[%Y-%m-%d %H:%M:%S] ") + str(msg) + "\n")
    except Exception:
        pass


def find_exe():
    """取当前已注册的 MSIX 包目录（WindowsApps 不能列目录，只能问 Appx）。"""
    global _FAM
    ps = ("$p = Get-AppxPackage -Name OpenAI.Codex | Sort-Object Version | Select-Object -Last 1; "
          "if ($p) { @{exe=(Join-Path $p.InstallLocation 'app\\ChatGPT.exe'); family=$p.PackageFamilyName} | ConvertTo-Json -Compress }")
    try:
        out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=40, creationflags=0x08000000)
        package = json.loads(out.stdout or "null")
        if out.returncode == 0 and isinstance(package, dict) and os.path.isfile(package.get("exe", "")):
            _FAM = package.get("family") or None
            return package["exe"]
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


EXE = None  # 延迟发现：导入模块/运行测试不应启动系统探测。
REQUIRED_GATES = ("1506311413", "410065390", "410262010", "3085093835")
ACTIVE_FEATURES = {"computer_use", "browser_use_external", "browser_use", "layout", "i18n"}
FEATURE_POLICY = {}
PATCH_VERSION = "layout-v1"
REPORT = os.path.join(LOG_DIR, "verification.json")


def verification_failures(state):
    """功能开关与真实导航同时成立才通过，不能只凭注入标记自证成功。"""
    failures = []
    keys = ["patched"]
    if "i18n" in ACTIVE_FEATURES:
        keys.append("enable_i18n")
    if "layout" in ACTIVE_FEATURES:
        keys.extend(("officialLayout", "navigation", "settingsEntry"))
    for key in keys:
        if state.get(key) is not True:
            failures.append(key)
    if "i18n" in ACTIVE_FEATURES and (not str(state.get("lang", "")).lower().startswith("zh") or state.get("cjk", 0) < 20):
        failures.append("chinese-rendering")
    for gate in REQUIRED_GATES:
        if state.get("gates", {}).get(gate) is not True:
            failures.append("gate:" + gate)
    return failures


def write_report(report, path=None):
    """不记录正文、账号或配置；原子替换，避免失败后残留上次成功报告。"""
    from pathlib import Path
    target = Path(path or REPORT)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)


def component_diagnostics():
    """Separate inventory from gate verification; never start tools or mutate config."""
    try:
        from runtime_diagnostics import collect
        return collect()
    except Exception as error:
        log("组件诊断不可用：" + type(error).__name__)
        return {"verification_scope": "local-inventory-not-tool-execution",
                "warnings": ["diagnostics-unavailable"], "status": "unavailable"}


class CdpSession:
    def __init__(self, ws):
        self.ws = ws
        self.sequence = 0

    async def call(self, method, params=None):
        self.sequence += 1
        request_id = self.sequence
        await self.ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        deadline = time.monotonic() + 15
        while True:
            message = json.loads(await asyncio.wait_for(self.ws.recv(), max(0.01, deadline - time.monotonic())))
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(f"CDP {method}: {message['error']}")
            return message.get("result", {})

    async def evaluate(self, expression):
        result = await self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True})
        if result.get("exceptionDetails"):
            raise RuntimeError("JavaScript: " + str(result["exceptionDetails"]))
        return result.get("result", {}).get("value")

PATCH = r"""
(() => {
  const LAYER = "72216192";
  // 只覆盖已验证的功能：CU / 两类浏览器操控 / 官方 rail 导航。
  // 国内无法连接 Statsig 时布局回退 legacy；无需伪造登录或修改 DOM/CSS。
  const GATES = ["1506311413", "410065390", "410262010", "3085093835"];
  if (window.__zhPatchVersion === "layout-v1") { return "already"; }
  window.__zhApplied = true;
  window.__zhPatchVersion = "layout-v1";
  let ns = window.__STATSIG__;
  function fakeGate(s) {
    return { name: s, value: true, ruleID: "local", ruleIDString: "local",
             details: { reason: "override" }, evaluationDetails: { reason: "override" } };
  }
  function installOverride(inst) {
    if (!inst || inst.__zhOA === "layout-v1") return;
    const previous = inst.overrideAdapter;
    const delegate = (method, args) => typeof previous?.[method] === "function"
      ? previous[method].apply(previous, args) : null;
    inst.overrideAdapter = {
      getGateOverride: function (gate, ...rest) {
        var n = gate && gate.name;
        if (GATES.indexOf(String(n)) >= 0) return fakeGate(String(n));
        return delegate("getGateOverride", [gate, ...rest]);
      },
      getDynamicConfigOverride: function (...args) { return delegate("getDynamicConfigOverride", args); },
      getExperimentOverride: function (...args) { return delegate("getExperimentOverride", args); },
      getLayerOverride: function (...args) { return delegate("getLayerOverride", args); },
      getParameterStoreOverride: function (...args) { return delegate("getParameterStoreOverride", args); },
    };
    inst.__zhOA = "layout-v1";
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
  const iv = setInterval(() => { if (ns) patchNs(ns); }, 100);
  setTimeout(() => clearInterval(iv), 120000);
})();
"""

STATE = r"""
(() => {
  const t = document.body.textContent || "";
  let ok = null, officialLayout = false;
  try {
    const c = window.__STATSIG__.firstInstance;
    ok = c.getLayer("72216192", {}).get("enable_i18n", false);
    officialLayout = c.getFeatureGate("3085093835").value === true;
  } catch (e) { ok = "no-client"; }
  const gates = {};
  for (const id of ["1506311413", "410065390", "410262010", "3085093835"]) {
    try { gates[id] = window.__STATSIG__.firstInstance.getFeatureGate(id).value === true; }
    catch (_) { gates[id] = false; }
  }
  const buttons = [...document.querySelectorAll("button")].filter(b => b.getClientRects().length > 0);
  const label = b => (b.textContent || "").trim();
  const navigation = ["首页", "探索"].every(s => buttons.some(b => label(b) === s));
  const settingsEntry = buttons.some(b => /个人资料|profile/i.test(b.getAttribute("aria-label") || ""));
  return JSON.stringify({ patched: window.__zhApplied === true, enable_i18n: ok, officialLayout, gates, navigation, settingsEntry, lang: document.documentElement.lang, cjk: (t.match(/[\u4e00-\u9fff]/g) || []).length, len: t.length });
})()
"""


PATCH_TEMPLATE = PATCH
STATE_TEMPLATE = STATE


def configure_features(asar):
    """Rediscover every launch; unsupported/ambiguous roles pass through to vendor defaults."""
    import hashlib
    from repair_codex import discover, renderer_sources, ROLES
    global PATCH, STATE, REQUIRED_GATES, ACTIVE_FEATURES, FEATURE_POLICY, PATCH_VERSION
    found, _ = discover(renderer_sources(asar))
    FEATURE_POLICY = {role: {"mode": "override" if role in found else "official-default",
                              "id": found.get(role),
                              "reason": "unique-structural-match" if role in found else
                                        "missing-or-ambiguous-structure; not proof of feature removal"}
                      for role in ROLES}
    FEATURE_POLICY["guardian_approval"].update({
        "verification_scope": "rollout-gate-only",
        "official_publication": "not-probed",
        "menu_visibility": "not-probed",
        "risk_review_service": "not-probed",
        "note": "Existing instances may await official republication; gate=true does not prove menu availability.",
    })
    ACTIVE_FEATURES = set(found)
    REQUIRED_GATES = tuple(found[role] for role in ROLES if role != "i18n" and role in found)
    PATCH_VERSION = "policy-v3-" + hashlib.sha256(json.dumps(found, sort_keys=True).encode()).hexdigest()[:16]
    gates = json.dumps(list(REQUIRED_GATES))
    PATCH = re.sub(r'const GATES = \[.*?\];', lambda _: 'const GATES = ' + gates + ';', PATCH_TEMPLATE)
    PATCH = re.sub(r'const LAYER = "\d+";', lambda _: 'const LAYER = ' + json.dumps(found.get("i18n", "")) + ';', PATCH)
    PATCH = PATCH.replace('"layout-v1"', json.dumps(PATCH_VERSION))
    STATE = re.sub(r'for \(const id of \[.*?\]\)', lambda _: 'for (const id of ' + gates + ')', STATE_TEMPLATE)
    STATE = STATE.replace('"72216192"', json.dumps(found.get("i18n", "")))
    STATE = STATE.replace('"3085093835"', json.dumps(found.get("layout", "")))
    for role, policy in FEATURE_POLICY.items():
        log(role + ": " + policy["mode"] + " (" + policy["reason"] + ")")
    return FEATURE_POLICY


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


def devtools_files(fam):
    """候选路径全部检查，不因父目录存在而认定端口文件就在那里。"""
    local = os.environ.get("LOCALAPPDATA", "")
    base = os.path.join(local, "Packages", fam, "LocalCache")
    return [
        os.path.join(base, "Roaming", "Codex", "web", "Codex", "DevToolsActivePort"),
        os.path.join(base, "Roaming", "Codex", "DevToolsActivePort"),
        os.path.join(os.environ.get("APPDATA", ""), "Codex", "web", "Codex", "DevToolsActivePort"),
        os.path.join(os.path.expanduser("~"), ".codex", "DevToolsActivePort"),
    ]


def read_devtools_port(path):
    try:
        with open(path, encoding="utf-8") as f:
            first = f.readline().strip()
        return int(first) if first.isdigit() and 0 < int(first) < 65536 else None
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
    for path in devtools_files(fam):
        p = read_devtools_port(path)
        if p:
            cands.append(p)
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


def kill_codex():
    """结束当前所有 Codex 进程（必须带 /T，否则子进程会留着并继承调试端口句柄 → 僵尸监听）。"""
    try:
        subprocess.run(["taskkill", "/F", "/T", "/IM", "ChatGPT.exe"],
                       capture_output=True, creationflags=0x08000000)
    except Exception:
        pass
    for _ in range(6):
        time.sleep(2)
        if not codex_running():
            return True
    return not codex_running()


CONFIG = os.path.join(os.path.expanduser("~"), ".codex", "config.toml")
NEED_PLUGINS = ["computer-use@openai-bundled", "chrome@openai-bundled"]


def ensure_config(active_features=None):
    """CC Switch 切换供应商时会用自己那份最小模板整份覆盖 config.toml，
    把 [desktop] localeOverride / 插件 enabled / marketplace 一起冲掉。
    这里在启动前按需把这些项补回来（幂等；改动前备份；改完先做 TOML 校验）。"""
    try:
        with open(CONFIG, encoding="utf-8") as f:
            src = f.read()
    except FileNotFoundError:
        return "没有 config.toml，跳过"
    orig = src
    active = ACTIVE_FEATURES if active_features is None else set(active_features)
    plugins = []
    if "computer_use" in active:
        plugins.append(NEED_PLUGINS[0])
    if active & {"browser_use", "browser_use_external"}:
        plugins.append(NEED_PLUGINS[1])
    fixes = []

    import tomllib
    parsed = tomllib.loads(src)  # 原配置非法时立即停止，不在损坏的配置上继续修补。
    # Explicit user opt-outs are permissions, not missing configuration.
    plugins = [plug for plug in plugins
               if parsed.get("plugins", {}).get(plug, {}).get("enabled") is not False]
    if "i18n" in active and parsed.get("desktop", {}).get("localeOverride") != "zh-CN":
        desktop = re.search(r"(?ms)^\[desktop\][ \t]*(?:#[^\n]*)?\n(.*?)(?=^\[|\Z)", src)
        if desktop:
            body = desktop.group(1)
            if re.search(r"(?m)^[ \t]*localeOverride[ \t]*=", body):
                body = re.sub(r"(?m)^[ \t]*localeOverride[ \t]*=.*$", 'localeOverride = "zh-CN"', body, count=1)
            else:
                body = 'localeOverride = "zh-CN"\n' + body
            src = src[:desktop.start(1)] + body + src[desktop.end(1):]
        else:
            src = src.rstrip("\n") + '\n\n[desktop]\nlocaleOverride = "zh-CN"\n'
        fixes.append("localeOverride=zh-CN")

    for plug in plugins:
        hdr = '[plugins."%s"]' % plug
        m = re.search(r"(?ms)^" + re.escape(hdr) + r"[ \t]*(?:#[^\n]*)?\n(.*?)(?=^\[|\Z)", src)
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
    if plugins and "openai-bundled" not in parsed.get("marketplaces", {}) and os.path.isdir(mp):
        src = (src.rstrip("\n") + "\n\n[marketplaces.openai-bundled]\nsource_type = \"local\"\n"
               "source = '\\\\?\\" + mp + "'\n")
        fixes.append("marketplaces.openai-bundled 补回")

    if src == orig:
        if re.search(r"(?m)^\s*requires_openai_auth\s*=\s*true\s*$", src):
            return "配置完好，无需修补（注意：requires_openai_auth = true，启动后可能停在登录页）"
        return "配置完好，无需修补"

    tomllib.loads(src)

    with open(os.path.join(BACKUP_DIR, "config.toml.bak-codexzh"), "w", encoding="utf-8", newline="\n") as f:
        f.write(orig)
    temporary = CONFIG + ".tmp-codexzh"
    with open(temporary, "w", encoding="utf-8", newline="\n") as f:
        f.write(src)
    os.replace(temporary, CONFIG)
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


async def main(verify_only=False):
    global PORT, EXE
    EXE = await asyncio.to_thread(find_exe)
    if not EXE:
        raise RuntimeError("没找到 OpenAI.Codex 安装目录")
    await asyncio.to_thread(configure_features, os.path.join(os.path.dirname(EXE), "resources", "app.asar"))
    if not verify_only:
        from runtime_diagnostics import repair_session_config
        cleanup = repair_session_config(CONFIG)
        if cleanup['changed']:
            log('已清理 node_repl 持久化会话引用；备份：' + cleanup['backup'])
        log(ensure_config(ACTIVE_FEATURES))
    existing = await asyncio.to_thread(find_existing_cdp)
    if existing and not verify_only:
        PORT = existing
        target = await asyncio.to_thread(page_ws)
        if target:
            async with websockets.connect(target, close_timeout=3) as probe:
                version = await CdpSession(probe).evaluate("window.__zhPatchVersion || null")
            if version and version != PATCH_VERSION:
                # Old prototype wrappers cannot safely be unpatched in-place.
                if not await asyncio.to_thread(kill_codex):
                    raise RuntimeError("策略变化，必须完全退出 Codex 才能恢复官方默认行为")
                existing = None
    if existing:
        PORT = existing
        log(f"连接已有 Codex 调试端口 {PORT}")
    elif verify_only:
        raise RuntimeError("没有可核验的 Codex 调试实例；请先通过启动器打开")
    else:
        if await asyncio.to_thread(codex_running):
            log("无调试端口的实例：结束进程树后重新启动")
            if not await asyncio.to_thread(kill_codex):
                raise RuntimeError("无法结束 Codex，请手动完全退出后重试")
        paths = devtools_files(await asyncio.to_thread(pkg_family))
        for path in [PORT_FILE, *paths]:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
        PORT = 0
        log("启动方式: " + await asyncio.to_thread(spawn_app))
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            for path in paths:
                p = read_devtools_port(path)
                if p and await asyncio.to_thread(cdp_alive, p):
                    PORT = p
                    break
            if PORT:
                break
            await asyncio.sleep(0.5)
        if not PORT:
            raise RuntimeError("120 秒内未找到真实调试端口；不再猜测未监听的固定端口")
    save_port(PORT)
    url = None
    for _ in range(200):
        url = await asyncio.to_thread(page_ws)
        if url:
            break
        await asyncio.sleep(0.2)
    if not url:
        raise RuntimeError("找不到 Codex 页面目标")
    async with websockets.connect(url, max_size=64 * 1024 * 1024, close_timeout=3) as ws:
        rpc = CdpSession(ws)
        await rpc.call("Page.enable")
        if not verify_only:
            await rpc.call("Page.addScriptToEvaluateOnNewDocument", {"source": PATCH})
            await rpc.evaluate(PATCH)
        deadline = time.monotonic() + (5 if verify_only else 120)
        state = {}
        while time.monotonic() < deadline:
            state = json.loads(await rpc.evaluate(STATE) or "{}")
            failures = verification_failures(state)
            if not failures:
                write_report({"status": "passed", "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                              "app_path": EXE, "port": PORT, "state": state, "features": FEATURE_POLICY,
                              "components": await asyncio.to_thread(component_diagnostics),
                              "verification_scope": "active-overrides-only"})
                log("核验通过：" + json.dumps(state, ensure_ascii=False))
                return
            await asyncio.sleep(1)
        write_report({"status": "failed", "port": PORT, "state": state,
                      "components": await asyncio.to_thread(component_diagnostics),
                      "failures": verification_failures(state)})
        raise RuntimeError("核验失败：" + ", ".join(verification_failures(state)) +
                           "；可能为新版兼容性变化，请查看 verification.json")


def entry():
    import argparse
    import ctypes
    parser = argparse.ArgumentParser(description="Codex 中文/CU/官方导航启动与核验")
    parser.add_argument("--verify-only", action="store_true", help="只读核验，不注入、不修配置、不启动应用")
    options = parser.parse_args()
    # 命名 mutex 防止重复点击并发启动；句柄退出时关闭，不依赖遗留 pid 文件。
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateMutexW(None, False, "Local\\CodexZhLauncher")
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    if ctypes.get_last_error() == 183:
        kernel.CloseHandle(handle)
        log("已有启动器正在执行，本次退出")
        return 0
    try:
        write_report({"status": "checking", "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                      "components": {"status": "pending"}})
        log("---- 开始核验 ----")
        asyncio.run(main(options.verify_only))
        log("---- 结束（CDP 客户端已断开，无常驻守卫） ----")
        return 0
    except Exception as error:
        log("失败: " + repr(error) + "\n" + traceback.format_exc())
        # 保留 main 写入的详细失败状态；其他异常也不能残留 passed。
        try:
            with open(REPORT, encoding="utf-8") as stream:
                report = json.load(stream)
            report.update(status="failed", error=str(error))
            write_report(report)
        except Exception:
            pass
        if not options.verify_only:
            ctypes.windll.user32.MessageBoxW(None, str(error), "Codex 启动/兼容性核验失败", 0x10)
        return 1
    finally:
        kernel.CloseHandle(handle)


if __name__ == "__main__":
    raise SystemExit(entry())

