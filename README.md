# Codex 桌面版中文化 / 电脑操控解锁启动器

> 一个 Windows 启动器：**不改动 Codex 安装目录里的任何字节**，让官方 Codex 桌面版显示中文界面，并打开 Computer Use（电脑操控 / Chrome / 应用内浏览器）的远端开关。
>
> 实测环境：`OpenAI.Codex 26.1103.4239.0`（MSIX，x64，Chrome 157 / Electron 40）。

---

## 一、它解决的是什么问题

### 1. 界面调不成中文：卡在远端开关，不是配置问题

Codex 的语言包本来就随应用装在 `app.asar` 里（`/locales/zh-CN.json`、`zh-TW`、`zh-HK` 都在）。界面语言不走 `config.toml`，而是走 Statsig 的一个 layer：

```js
x = Ou("72216192");            // getLayer(layerId)
M = x?.get("enable_i18n", !1)  // 默认 false —— 这就是开关
```

而 layer `72216192` 只在**登录成功后**由 `POST /wham/statsig/bootstrap` 下发。使用第三方中转、或处于未登录状态时，这一串请求会鉴权失败（实测返回）：

```
432 Workspace routing is unavailable
```

于是 layer 根本不存在 → `messages = undefined` → UI 静默回落到英文，**不报错、不提示**。所以把 `[desktop] localeOverride` 改成 `zh-CN` / `ja-JP` 都没用（已实测对照过）。

### 2. Computer Use 不可用：三层限制

| 层 | 条件 | 说明 |
|---|---|---|
| 1 主进程 | `CODEX_ELECTRON_ENABLE_WINDOWS_COMPUTER_USE=1` | 没有它，主进程根本不准备 CU 管道 |
| 2 运行时/插件 | `computer-use@openai-bundled` 插件 `enabled = true` | 少一段插件配置就没有入口 |
| 3 渲染层 Statsig gate | `1506311413`（电脑操控）、`410065390`（Chrome）、`410262010`（浏览器） | 无登录态恒为 `false`，UI 里那几项直接不显示 |

本脚本把三层一起补齐。

---

## 二、做法：靠调试端口在“首帧之前”注入

```
快捷方式
  └─ wscript.exe  →  start-codex.vbs          （无黑框，动态找 Python）
       └─ pythonw.exe  →  codex_zh_launch.py
            ├─ ensure_config()                 → 检查/补回 config.toml 必要段落
            ├─ ActivateApplication(AUMID, "--remote-debugging-port=9333")
            │      └─ 官方 Codex 以「包身份」启动（任务栏用官方图标），端口打开
            └─ CDP WebSocket
                 ├─ Page.addScriptToEvaluateOnNewDocument(PATCH)   ← 先挂到页面
                 └─ Runtime.evaluate(PATCH)                        ← 再对当前页面生效
```

`PATCH` 做两件事：

1. 包裹 Statsig 的 `getLayer`，让 `getLayer("72216192").get("enable_i18n")` 恒为 `true` → 中文界面立刻生效（provider 第一次渲染就拿到 `messages`）。
2. 设置 `StatsigClient.overrideAdapter.getGateOverride` 并清空 `_memoCache`，让三个 CU gate 返回 `true`。

关键点：**必须在页面挂载前注入**。页面渲染完再改 `getLayer`、发 `$emt` 事件、改窗口大小、触发 `visibilitychange` 都试过——全部无效，因为 i18n 的 `messages` 在 provider 初始化那一刻就定型了。

---

## 三、目录结构

```
codex-zh/
├── codex_zh_launch.py     # 主启动器：版本自适应找 exe、AppX 激活、CDP 注入、config 自愈
├── activate_codex.py      # IApplicationActivationManager 的 ctypes 封装（带参数按包身份启动）
├── start-codex.vbs        # 快捷方式入口：动态定位 pythonw，隐藏窗口运行，失败弹中文提示
├── install.ps1            # 一键创建「桌面快捷方式 + 任务栏固定项」
├── assets/
│   ├── codex.ico          # 多尺寸图标（16/20/.../256），源自 MSIX 包内官方素材
│   └── icon-source-256.png
└── tools/                 # 调试用小工具（不影响启动）
    ├── eval_js.py         # 对运行中的页面执行一段 JS
    └── cdp_shot.py        # 通过 CDP 截图
```

---

## 四、依赖

- Windows 10/11 x64，且 Codex 是通过 **MSIX / Microsoft Store** 安装的（脚本用 `Get-AppxPackage -Name OpenAI.Codex` 找安装目录）。
- Python 3.9+。
- **Python 包：`websockets`**（唯一第三方依赖，用来连 CDP）。
  - 装好 `websockets` 的任意 Python 3.9+ 都可以；入口脚本会自动在常见安装位置和 `PATH` 里查找 `pythonw.exe`。
- 不需要管理员权限，不需要改系统设置。

---

## 五、安装

```powershell
# 在本目录执行；会创建桌面快捷方式 + 任务栏固定项（后者带 AUMID，运行时与原版合并成一个图标）
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

可选参数：

| 参数 | 作用 |
|---|---|
| `-NoRestart` | 不改完就重启 explorer（固定项要重启资源管理器才会出现在任务栏） |
| `-SkipTaskbar` | 只建桌面快捷方式 |

手动做法（等价）：快捷方式目标填
`C:\Windows\System32\wscript.exe`，参数填 `"<本目录>\start-codex.vbs"`。
任务栏固定项还要额外写 `System.AppUserModel.ID = OpenAI.Codex_2p2nqsd0c76g0!App`（`install.ps1` 已处理），否则会出现「固定项一个图标 + 运行中一个图标」。

### 为什么图标用 `assets\codex.ico`

任务栏按钮的图标来自**运行中的进程**：直接 `Popen(ChatGPT.exe)` 起的进程没有包身份，只能用 exe 内嵌的 32×32 小图标，放到 96px 就是糊的。
本脚本改用 AppX 激活，进程带包身份，任务栏自动使用 MSIX 官方素材（`Square44x44Logo.targetsize-*`），清晰。
`codex.ico` 是用同一套官方 PNG 重新拼的多尺寸 ico，只用于快捷方式/固定项本身。

---

## 六、使用与日志

正常情况：双击桌面快捷方式（或点任务栏固定项）→ 界面中文。

```
launch.log   启动器日志：配置修补结果、AppX 激活 hr/pid、启动方式、结束
vbs.log      入口日志：这一层选了哪个 Python
```

**注意启动速度**：应用启动时会先等远端请求超时，从进程起来到真正渲染出界面可能需要几十秒（期间只有一个居中的 logo，`document.body.textContent` 长度 < 20）。不要误判为卡死。

其它入口：

```bash
# 对已运行的实例执行 JS（调试用）
python tools/eval_js.py -e 'document.title'

# 截图（调试用）
python tools/cdp_shot.py shot.png
```

---

## 七、更新与配置管理

- **版本自适应**：`find_exe()` 每次运行都用 `Get-AppxPackage` 取当前已注册版本，App 升级后不用改脚本。
- **零文件改动**：`app.asar` / `chrome.dll` 一个字节都没动，MSIX 完整性与签名不受影响，可以正常自动更新。
- **更新后的风险**：如果新版本改了 Statsig layer/gate 的 ID 或 SDK 结构，补丁会**静默失效**（界面回英文、CU 入口消失），但不会损坏任何文件。届时改 `codex_zh_launch.py` 里的 `LAYER` / `GATES` 常量即可。
- **第三方配置切换工具会把 `~/.codex/config.toml` 整份覆盖**（常见于在多个中转/供应商之间来回切的工具），冲掉 `[desktop] localeOverride`、`[plugins.*] enabled`、`[marketplaces.*]`。`ensure_config()` 在每次启动前按需补回：
  - `[desktop] localeOverride = "zh-CN"`
  - `[plugins."computer-use@openai-bundled"] enabled = true`
  - `[plugins."chrome@openai-bundled"] enabled = true`
  - `[marketplaces.openai-bundled]`（目录存在时才补）

  幂等；改动前备份 `config.toml.bak-codexzh`；写前用 `tomllib` 校验。**不碰** `model_provider` / `base_url` / `requires_openai_auth` / token。

---

## 八、故障排查

| 现象 | 原因 / 处理 |
|---|---|
| 双击快捷方式没反应 | 看 `vbs.log`：多半是找不到 Python（会弹框提示）；或 `launch.log` 里 `AppX 激活失败` |
| 弹出「Codex 已经在运行，但不是通过本启动器启动的」 | 之前用开始菜单/任务栏原版图标起过一个实例且还活着。**完全退出 Codex**（含托盘/后台进程）再启动 |
| 界面仍是英文 | 看 `launch.log` 的 `补丁生效` 行；若 `enable_i18n: true` 但没中文，等久一点（渲染慢）；若 gate 补丁整体失效，说明新版改了 ID |
| 任务栏出现两个图标 | 固定项没写 AUMID。删掉重新跑 `install.ps1` |
| 任务栏图标糊 | 说明这次是回退路径（`启动方式: popen`）起的，没有包身份。看 `launch.log` |
| 设置里没有「电脑操控」 | 三个 gate 没打开，或插件没启用（`ensure_config()` 日志会写修补了什么） |

---

## 九、已知限制（本地绕不过去）

- **云端功能**：工作区、插件市场、额度/用量等依赖 `chatgpt.com` 登录态，`/wham/*` 恒 432，无法本地伪造。
- **「始终允许的应用」列表为空**：app tools 来自 `cua_repl` 通道，`authStatus=unsupported`（未登录），需要真实登录。
- **从开始菜单启动原版图标仍是英文**：微软的 AppX 激活参数由系统写死，用户侧没有注入点。所以本方案只保证「桌面快捷方式 / 任务栏固定项」这两个入口。

---

## 十、卸载与回滚

1. 删掉桌面快捷方式、任务栏固定项（右键 → 从任务栏取消固定）、`Startup` 里若有同名项一并删除。
2. Codex 安装目录：本来就是零改动，无需恢复。
3. `config.toml` 若被 `ensure_config()` 改过，恢复备份即可：
   ```powershell
   Copy-Item "$HOME\.codex\config.toml.bak-codexzh" "$HOME\.codex\config.toml"
   ```

---

## 十一、实现备注（踩过的坑）

- **不能改 `app.asar`**：`WindowsApps` 目录 ACL 拒绝写入；即使拿到管理员权限改掉，Electron 的 asar 完整性 fuse（`EnableEmbeddedAsarIntegrityValidation`）会让改过的副本直接崩溃：
  `Failed to validate block while ending ASAR file stream: 1`。所以走「原版 + 运行时注入」。
- **`ActivateApplication` 必须在独立线程调**：asyncio 的 Proactor 已初始化 COM，事件循环线程里初始化 STA 会冲突（`RPC_E_CHANGED_MODE`）。代码里用 `asyncio.to_thread(spawn_app)`。
- **`ctypes.windll` 而不是 `oledll`**：`oledll` 会把 `CoInitializeEx` 的返回码变成异常，导致激活静默失败。
- **改 Statsig gate 只有一条可行路**：`client.overrideAdapter = { getGateOverride... }` + 清 `_memoCache`。实例上 `getFeatureGate` 是不可配置的类字段（赋值静默无效、`defineProperty` 抛错），`prototype._getFeatureGateImpl` 也被构造时闭包捕获，都试过无效。
- **读页面文本用 `textContent`**：这个应用经常 `document.body.innerText === ""`，用它判断会误以为白屏。
- **写 `.lnk` 的 AUMID 要用 `IShellLink → IPropertyStore → IPersistFile.Save`**：拿 `SHGetPropertyStoreFromParsingName` 直接写会把快捷方式的 target/args 弄丢。

---

## 许可 / 免责

个人自用工具，与 OpenAI 无关联。它不修改、不重新分发 Codex 的任何文件，也不包含任何密钥或账号配置（`config.toml` 里的凭据不会进入本仓库）。
