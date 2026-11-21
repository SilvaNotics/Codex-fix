# Codex-fix：Windows Codex 中文化与功能开关启动器

在不修改官方 Codex 安装文件的前提下，通过启动时的运行时注入，启用已识别的中文界面、电脑操控、浏览器操控与官方导航布局开关。

**这是官方桌面版的辅助启动器，不是独立客户端，不提供账号、模型 API 或云端权限。**

已验证安装包：`OpenAI.Codex 26.1103.4239.0` 与 `26.1103.7773.0`（Windows MSIX，x64）；后者已做安装包结构匹配检查，SSH / Appshots 完整任务仍需实际使用验证。新版兼容性以实际扫描和核验结果为准。

`26.1117.3838.0` 已通过本机安装包结构扫描。扫描器可识别新版 SSH/WSL 共用的远程连接开关和响应式 Mini 布局选择器。应用内浏览器与外部 Chrome 分别使用各自的插件配置。

## 1. 功能与限制

| 项目 | 本项目的作用 |
| --- | --- |
| 中文界面 | 覆盖已识别的语言开关，按需补充中文配置 |
| 电脑操控 / Chrome / 应用内浏览器 | 配合主进程环境、插件配置与渲染层开关启用入口 |
| 官方导航布局 | 明确匹配时启用官方组件，不修改 DOM/CSS |
| SSH / WSL 连接设置 | 补齐结构明确匹配的远程连接入口开关，保留本地主机与工作模式限制 |
| 应用快照（Appshots） | 补齐通用与 Windows rollout 开关，保留管理员策略和原生 helper 能力检查 |
| 彩带特效 | 匹配 `toys` 总开关；保留 `confettiEnabled` 用户设置，不自动播放；此总开关也包含音频可视化，但保留其用户设置 |
| 听写 | 匹配输入框听写与全局听写 rollout；保留 ChatGPT 登录、麦克风权限、宿主和服务端限制，不自动开麦，不覆盖实时语音开关 |
| 宠物新版布局 | 动态匹配 `pets_layout` 双分支选择器，启用官方 Mini 新版设置布局；不是新增入口，不更改宠物显示偏好，不覆盖云端同步或 PIP 开关 |
| 帮我批准（Auto-review） | 动态匹配 `guardian_approval` 的官方 gate→featureKey 映射；保留当前权限模式、工作区要求和执行层风险审查，不覆盖默认选用该模式的独立开关 |
| 更新适配 | 每次启动扫描安装包，按功能独立匹配；无法识别的项交回官方默认 |
| 核验报告 | 输出有效覆盖项的检查结果与回退原因 |

新增项在 `26.1106.6628.0` 安装包通过结构扫描，并通过离线 Python / Node 补丁测试：彩带总门 `1485025891`，听写 `4100906017`，全局听写额外门 `1244621283`，宠物新版布局 `1532120159`。每次启动重新定位，不固定依赖这些 ID。Node 测试验证生成补丁的 gate 覆盖、原适配器委托与偏好不变；听写认证/媒体约束仅由合成结构匹配测试覆盖，未执行官方听写函数，不以手写布尔表达式代替真实听写验证。尚未在真实界面验证彩带播放、听写转录或 Mini 布局呈现；运行时 gate 核验不代表端到端服务可用。


注意：

- 不绕过登录、工作区身份、订阅、额度或云端权限。`Workspace routing is unavailable` 不能靠本地开关修复。
- 开启入口不代表任务已端到端可用。模型、网络、Node REPL 和 Windows 沙箱仍可能独立出错。
- 不保证任意未来版本都能适配；无法识别不等于功能被移除，也不会猜测开关 ID。
- 通过本项目入口启动才会执行补丁。从开始菜单打开官方入口不会自动注入。

## 2. 准备与启动

### 2.1 环境要求

- Windows 10/11 x64。
- **MSIX / Microsoft Store 版官方 Codex**，能通过 `Get-AppxPackage -Name OpenAI.Codex` 找到。
- **Python 3.11+**，并在同一解释器环境中安装 **`websockets`**。
- Windows 自带的 Windows PowerShell 5.1 与 Windows Script Host。


使用独立 Python 时，将其加入 PATH，并用实际解释器路径安装依赖、检查环境：

```powershell
# 替换为真实路径，不要指向 WindowsApps 的商店占位程序
& 'C:\实际路径\python.exe' -m pip install websockets
& 'C:\实际路径\python.exe' -c "import sys, websockets; print(sys.version); print(sys.executable)"
```

当前 VBS 入口优先查找 Hermes venv，其次查找 PATH 中的 `pythonw.exe` / `python.exe`。确保入口实际选中的解释器具备依赖。VBS 中“打开或安装 Hermes”的提示不是唯一解决办法，独立 Python 同样可用。

### 2.2 下载完整项目

下载仓库 ZIP 并完整解压，或使用 Git 克隆。保留根目录与 `scripts/` 的相对位置，不要只复制一个入口文件。

解压后直接双击根目录 `CLICKME.cmd`：自动检查并修复 VBS 编码，然后通过 `scripts/start-codex.vbs` 启动 Python 启动器。其余程序集中在 `scripts/`，不要单独移动。

> **跨电脑编码提醒：** VBS 提示“未结束的字符串常量 / 800A0409”时，先按第 5.1 节检查编码。无需为此重装 Codex、调整沙箱或修改系统区域设置。

### 2.3 启动

确认 Codex 没有正在执行的任务，直接双击 **`CLICKME.cmd`** 即可，不需要打开终端。编码检查通过后调用隐藏窗口的 VBS 入口；不会自动安装 Python 或依赖。

项目按需使用，不创建桌面快捷方式或任务栏固定项，不设置自定义图标，也不重启 Explorer。旧版的 `-SkipTaskbar` / `-NoRestart` 安装参数已移除。也可直接双击 `scripts/start-codex.vbs`。

也可直接用自有 Python 启动，绕过 VBS 的解释器查找：

```powershell
& 'C:\实际路径\python.exe' .\scripts\codex_zh_launch.py
```

### 2.4 本地配置与缓存

启动器补充的语言和插件配置会保存在本地，官方客户端也可能保留自身缓存。后续从官方入口启动时，若所需功能仍正常，可继续日常使用；功能回退或更新后需要重新适配时，再运行 `CLICKME.cmd`。

本项目注入的功能开关覆盖只存在于当前 Codex 进程内存中，不会写入官方安装包，也没有“使用固定次数后永久生效”的机制。本地配置或缓存存在，不保证完全退出并重启后仍保留全部覆盖效果。

## 3. 日常使用与结果检查

| 当前状态 | 启动器行为 |
|---|---|
| Codex 未运行 | 启动官方应用，获取随机调试端口后注入并核验 |
| 已有可连接的调试实例 | 连接现有实例，执行所需注入与核验 |
| 已有不带调试端口的实例 | 结束原进程树，再通过项目入口重启 |
| 旧补丁运行中且策略指纹变化 | 重启应用，清除旧内存覆盖后应用新策略 |

**启动器可能关闭并重启 Codex，请先结束或保存正在执行的任务。** 不要在任务中运行修复入口或反复双击启动器。

启动受官方远端请求影响，可能在 logo 页面停留几十秒。持续无进展时请查日志。

启动扫描使用语义锚点限定正则搜索范围，仍扫描所有渲染 JS 以检测歧义，不缓存固定 gate ID；组件函数体（含空结果）仅在当前 chunk 内复用，全局听写能力锚点在出现首个媒体候选时惰性扫描一次，保留证据顺序、offset 和重复项。包路径与包族名合并为一次系统查询。SDK 赋值/读取仍立即触发补丁，兜底轮询由 2ms 调为 100ms，减少渲染进程空转。匹配耗时不代表完整启动耗时。

### SSH 与应用快照的前提

- SSH 入口仍要求本地主机及合适的工作模式；实际连接需要本机 OpenSSH、有效的主机配置和远端认证。`~/.ssh/config` 缺失不是 rollout 开关失败，不会自动替用户创建连接。
- Appshots 仍受 `configRequirements/read` 返回的 `allowAppshots` 管理策略约束。Windows 还需要官方 capture helper / transport 和 `windows_appshots_v2` 能力；缺失时保持不可用，不绕过保护。
- 补丁保留并委托官方已有的 `overrideAdapter` 方法，不再丢弃其他 gate、experiment、layer 的覆盖。正常网络返回的非白名单配置保持原有行为。
- 不设置生产版不支持的 Dev-only 环境覆盖，也不启用语音屏幕上下文等额外用户开关。SSH / Appshots 的 gate 核验通过不代表已完成远程登录或截图任务。

### 宠物入口与 Mini 的区别（26.1106.6628.0，静态代码核对）

- 设置可见性在 `webview/assets/async/160740.8d93ddc2e4.js`：`case"pets"` 先检查 `pyyZ.t(SPnB.mZ)`，否则返回 `visible:eX`；`eX` 来自 `eFn4.ph`，不是宠物专用 Statsig gate。
- `739301.37a39f26d6.js` 的 `eFn4.ph` 是 Codex 本地或 Work 云端/本地任一访问状态为 `allowed`。本地访问由宿主支持、认证/账号/计划、工作区策略等共同决定；非 ChatGPT 认证也有官方本地访问路径，不应为了宠物改认证或强开工作区权限。
- `SPnB.mZ` 是 FedRAMP 工作区状态；`pyyZ.t` 调用 `UgZO.I()`，当前包内该函数恒为 `false`，故此版本该隐藏分支不生效。这不保证未来版本仍然如此。
- `566048.88ccc86b80.js` 中 `eX` 读取 `1532120159`，true 分支渲染 `eY` Mini 新版布局，false 分支渲染 `eS` 旧宠物布局；两者均有 `eb` 宠物集合。没有独立入口 gate **不等于没有布局 gate**。本项目将这一布局开关纳入动态覆盖，不以附近数字猜测 ID。
- 扫描必须解析选择器引用的两支函数：新版含 `settings.pets.visibility` 并引用含 `settings.mini.show/hide` 的按钮组件，旧版含 `slug:"pets"`，两支引用同一宠物集合组件（含 `collectionSection` / `onCreateStart` / `onCreateCloudPet`）。结构缺失、重复函数名、候选 ID 歧义或跨角色冲突时，仅该项回退 `official-default`，不阻断其他功能。组件边界解析不是完整 JS 解析器：函数体内遇到字符串/注释之外的 `/`（正则字面量或除法）保守拒绝，不让正则中的花括号跨函数借用标记；当前包仍可匹配。
- `2635985366` 在该设置组件中只控制 Mini 的“始终显示 / 按需显示”偏好行（另受 SDK 状态限制），不是布局选择器，不新增覆盖。`1532120159` 也供官方 `useMiniLanguage` 使用；覆盖会影响同 ID 的官方调用，不能宣称只影响一个组件。补丁不写 `petVisible` / `petVisibility`，不自动显示宠物，也不覆盖云宠物开关。
- 用户可先打开**设置 → 宠物**选择内置宠物；个人资料菜单也包含**显示宠物 / 显示 Mini**切换项。Mini 版设置另有显示按钮和可编辑快捷键（`openAvatarOverlay`）。具体中文标签随语言包变化；这些路径来自代码，尚未在当前运行窗口点击验证。若设置项不见，应先检查官方 Codex/Work 访问状态，不用修复入口强开无关 gate。
- 账户托管宠物在 `994233.a0764414ec.js` 使用账号及 `/pets/{pet_id}` 等官方接口；本地内置宠物选择与云端创建、分享、同步不是同一种能力。网络、真实登录和工作区要求仍需满足。

报告使用 `pets_layout` 区分布局与入口；匹配成功标为 `override`，否则 `official-default`，两者均不代表已验证桌面浮窗。此次只读扫描真实安装包并执行离线测试，未启动、关闭或重启 Codex，也未对运行窗口注入。

### 帮我批准：入口与风险审查分别核验

`26.1106.6628.0` 的官方执行功能映射为 `{gateName:"3902016271",featureKey:"guardian_approval"}`。扫描器按这对字段定位，ID 变化后重新匹配；缺失、歧义或跨角色冲突时回退官方默认。该 gate 被纳入现有 PATCH 的白名单，不硬编码到启动流程。

菜单使用 `guardian-approvals`；中文说明为“仅对检测到的风险操作请求批准”。它不是完全访问权限：官方转换逻辑选择 `on-request` 与 `guardian_subagent`，并保留沙箱/权限配置。`1597774583` 是默认选用此模式的另一开关，本项目不覆盖它，也不自动写 `approvals_reviewer`、`approval_policy` 或切换当前选择。

注意此功能比纯渲染开关多一条状态链：官方发布流程检查 SDK evaluations 与当前用户匹配，再把 `defaultEnableFeatures.guardian_approval` 发布到主进程，菜单从该状态读取。仅 `getFeatureGate(...).value=true` 不能证明菜单或执行功能已启用，也不能证明风险审查模型可用。旧修复在 evaluations 失效且 Statsig 不可达时仍会缺少菜单项。

启动器优先核验官方发布；未就绪时，在当前渲染进程增加本地功能默认值，只合并 `guardian_approval=true` 到菜单读取的派生状态与执行适配器读取的功能默认值。安装前确认主进程分配结果与当前 SDK 用户一致，用户或 SDK 实例变化后覆盖失效。此路径不调用 `refreshValuesAsync()`，启用入口无需 Statsig 连通或开启代理；不改写 evaluations、身份、哈希、官方发布事件或其他功能值。模块按结构发现，结构缺失或歧义时报告失败，不依赖固定 chunk/module ID。

报告中该项标明 `verification_scope=rollout-gate-and-effective-local-default`。官方路径为 `status=ready`；本地路径为 `status=ready-local`、`local_override=passed`，同时如实保留 `identity_valid` 与 `official_publication` 的官方检查结果。`--verify-only` 只读取现有状态，不安装覆盖或刷新评估。自动报告中的 `menu_visibility`、`risk_review_service` 仍为 `not-probed`，不能把功能默认值通过当成真实风险审查请求成功。

显式 `features.guardian_approval=false`、受管理的权限要求及官方权限转换仍然生效，不自动切换当前模式或批准操作。风险审查模型仍通过实际配置的服务运行，须另行验证。2026-11-17 在 `26.1111.2228.0` 运行实例验证了菜单与执行功能默认值，并在桌面权限菜单实际看到“帮我批准”；离线测试覆盖无刷新、无官方发布时的本地启用、其他功能值保留与用户变化后失效。未提交风险审查请求。

### 组件诊断：MCP、插件与操控权限分开看

启动核验报告新增 `components`，只读检查本地 bundled / primary-runtime 插件清单、配置启用状态和静态 `node_repl` 路径。`loaded: not-probed` 表示没有执行工具，不能用清单存在证明服务器已加载。扩展、Office 加载项与应用托管 MCP 的运行状态同样标为未探测，不以用户开关推断安装成功。

可在不重启 Codex、不注入补丁、不修改配置的情况下独立诊断：

```powershell
& 'C:\实际路径\python.exe' .\scripts\runtime_diagnostics.py
```

- 官方 `codex_app` / `cua_repl` 与用户配置的 MCP 列表不是同一层；诊断不重复注册应用托管服务器。
- 文档类 primary-runtime 插件缺失时报告 `primary-runtime-plugins-incomplete-use-official-sync`，由官方联网同步流程处理，不伪造资源或直接强制安装。
- 静态 `node_repl` 的命令/Node/CLI 路径缺失时报告告警。普通启动会精确清理其 `env` 下的 `SKY_CUA_NATIVE_PIPE` / `SKY_CUA_NATIVE_PIPE_DIRECTORY` 会话引用，写前创建 `config.toml.bak-session-*` 备份，校验除这两项外的 TOML 数据不变；不删除 MCP 服务器或其他环境变量，不输出管道值。独立诊断和 `--verify-only` 保持只读。
- 启动器尊重插件显式 `enabled = false`，不再将用户关闭的插件强制打开；缺失项仍按已有兼容逻辑补充。
- 不修改认证、浏览器扩展、Office 加载项或电脑操控授权；组件告警不冒充 gate 核验失败，也不因 `passed` 被当成已解决。

### 日志与报告

以下文件统一保存在项目的 `output/logs/`；各类备份统一保存在 `output/backups/`（可能含个人配置，不要分享或上传）。

| 文件 | 内容 |
|---|---|
| `vbs.log` | VBS 入口选中的 Python |
| `launch.log` | 配置补充、应用启动、CDP 连接与核验过程 |
| `verification.json` | `checking` / `passed` / `failed`，以及各功能覆盖或回退情况 |
| `repair-report.json` | 修复工具扫描证据与处理结果 |
| `cdp_port.txt` | 调试端口缓存；只是文本，不会占用端口 |

`output/`、`output/logs/`、`output/backups/` 均通过 `.gitkeep` 保留；Git 只跟踪占位文件，不提交日志、报告或配置备份。

**`passed` 仅表示本次有效覆盖项通过核验。** 某功能为 `official-default` 不意味着已启用；报告也不证明实际操控任务、沙箱或云服务可用。

## 4. Codex 更新后的检测与修复

先通过项目入口正常启动。启动器每次扫描当前安装包，不需要手填开关 ID。

若功能没有恢复，且没有正在执行的任务，可双击：

```text
repair-codex.cmd
```

普通修复会先检查 VBS 编码，再寻找 Python 3.11+ 与 `websockets`。随后扫描安装包并调用启动器核验，必要时可能重启 Codex。已有启动器正在运行时，修复会等待它完成，再对同一安装包核验并读取本次结果。

终端的扫描清单与启动核验清单按同一顺序列出全部功能。前者统计结构命中，后者统计完成运行时核验的覆盖项。`repair-report.json` 分别将两阶段结果写入 `scan_features` 和 `features`。

### 自动适配规则

- 中文、电脑操控、两类浏览器操控与布局按功能独立匹配。
- 唯一且结构明确的匹配生成运行时覆盖。
- 结构缺失、候选歧义或跨功能 ID 冲突时，该项使用 `official-default`，既不强制开启，也不强制关闭。
- 回退项不新增对应语言或插件配置；已有用户配置不擅自删除。
- SDK/CDP 整体异常或安装包损坏仍明确报错，不以回退掩盖失败。
- 已知结构内的 ID / 混淆变量改名可适配；功能实现、打包结构或 SDK 行为大改仍需人工处理。
- `repair-report.json` 在全部已登记项通过核验时写 `passed`。部分覆盖通过时写 `partial`，并列出 `defaulted_features`。零项命中时写 `failed`，返回非零退出码，直接结束修复。

只扫描并生成报告，跳过 VBS 编码修复和应用启动：

```powershell
.\repair-codex.cmd --scan-only
```

对已有实例只做核验，不注入、不改配置、不启动或重启应用（会更新核验报告）：

```powershell
& 'C:\实际路径\python.exe' .\scripts\codex_zh_launch.py --verify-only
```

工具使用本项目的脚本与 output 目录；启动及修复可能按需补充用户 Codex 配置。源码仓库与部署副本不会自动同步。当前动态策略不改启动器源码；仅兼容旧启动器的源码修复分支会生成 `.bak-repair-*` 备份。

## 5. 故障排查

### 5.1 VBS 启动入口的编码兼容性

**典型情况：同一项目在一台电脑正常，另一台电脑的 `start-codex.vbs` 提示“未结束的字符串常量 / 800A0409”。**

包含中文的 UTF-8 无 BOM 脚本可能在不同系统代码页下被传统 Windows Script Host 错误解码。`start-codex.vbs` 应使用 **UTF-16 LE 带 BOM**，不要保存为 UTF-8 BOM。源码截断或引号损坏也会产生相同症状。

#### 自动检查与修复

`CLICKME.cmd` 和普通 `repair-codex.cmd` 共用同一编码检查。严格解码 UTF-8（有无 BOM 均可）和带 BOM 的 UTF-16 LE，并将有效的脚本统一为 UTF-16 LE BOM。已有正确编码时保持原样。解码失败时保留原文件并停止。首次转换备份保存在 `output/backups/start-codex.vbs.bak-encoding`。

若 Windows `config.toml` 带 UTF-8 BOM，启动器会先解析并校验 TOML，备份原始字节，再写回 UTF-8 无 BOM。

文件若已被错误解码并保存，转码不能找回丢失字符，请重新下载。仍有语法错误时请提供具体文件、行号与系统版本。

### 5.2 页面目标不存在或启动前退出

Windows 启动器会将 **Windows `CODEX_HOME` 内已存在的模型目录文件**改为 `./相对路径`，写前备份并校验 TOML。WSL 独立连接读取发行版用户自己的配置，其中 `model_catalog_json` 应指向 WSL 可访问的文件。用 [WSL 迁移入口](#54-迁移到独立的-wsl-连接)生成对应的挂载路径。

页面等待按实际时间限时。应用退出时启动器会立即报告配置或启动错误。

### 5.3 其他问题

| 现象 | 优先检查 |
|---|---|
| 双击入口没反应 | 排除 VBS 编译错误，再看 `vbs.log` 的解释器路径与 `launch.log` |
| 找不到 Python / `No module named websockets` | 安装真实 Python，在入口实际选择的解释器中安装依赖；WindowsApps 商店占位程序不算可用解释器 |
| 界面英文 / 布局没变化 | 检查 `verification.json` 对应功能是覆盖、回退还是失败，再看日志 |
| 没有电脑操控入口 | 检查功能匹配、插件配置与主进程环境；入口存在不代表任务权限完整 |
| 长时间等待 `DevToolsActivePort` | 检查应用是否启动、是否回退为 `popen`；无任务时完全退出后重试 |
| `Workspace routing is unavailable` | 检查真实账号、工作区与官方服务网络；本项目不伪造云端权限 |
| “始终允许的应用”列表为空 | 检查 app tools / `cua_repl` 与账号状态；`authStatus=unsupported` 不能靠界面开关解决 |
| REPL 内核退出 / `windows sandbox failed` | 检查 Codex 自身 REPL 与沙箱日志；这是运行时问题，不能凭本项目的 `passed` 判断已修复 |

### 5.4 迁移到独立的 WSL 连接

1. 双击 **`MOVE_TO_WSL.cmd`**，输入发行版编号。脚本会列出目标默认用户、`~/.codex/config.toml` 和转换后的模型目录路径。
2. 输入 `yes` 确认合并。现有 WSL 配置会备份到同目录的 `config.toml.bak-move-to-wsl-*`。配置会重新格式化，原注释保留在备份中。
3. 在 Codex 的连接设置中重连该 WSL 发行版。Windows 上切换 CC Switch 供应商后，重新运行脚本以更新 WSL 的供应商配置。

迁移需要 Windows Python 3.11+ 和目标发行版的 `python3`。也可在 PowerShell 指定发行版先预检：

```powershell
.\MOVE_TO_WSL.cmd --distro Ubuntu --dry-run
```

脚本读取 Windows `CODEX_HOME`（默认 `%USERPROFILE%\.codex`）实际生效的配置。当前 CC Switch 端点、模型和写入供应商表的 token 会一同迁移。相对模型目录先按 Windows 配置目录解析，再通过所选发行版的 `wslpath` 转换并验证。例如 `./cc-switch-model-catalog.json` 可继续引用 `/mnt/c/Users/<Windows用户>/.codex/cc-switch-model-catalog.json`。

现有 WSL 桌面、插件、钩子和同名 MCP 设置会保留。CC Switch 数据库和 ChatGPT 登录资料留在原宿主。旧版仅含 API Key 的 `auth.json` 在自定义供应商需要它时可写入空白目标。使用 `env_key`、Windows localhost 代理或宿主专用命令时，需要在 WSL 连接环境中提供对应配置。

## 6. 卸载与回滚

1. 停止使用项目入口；旧版曾创建的桌面快捷方式和任务栏固定项可手动删除，当前版本不再创建。
2. **完全退出 Codex**，再从官方入口启动，清除进程内覆盖。只关闭窗口可能仍在后台运行。
3. 官方 `app.asar`、`chrome.dll` 等安装文件未被修改，无需恢复官方包。
4. 如需撤销配置补充，参考 `output/backups/config.toml.bak-codexzh`。**先备份当前配置并比较差异，不要直接覆盖，以免丢失后续新增的模型或供应商设置。**

启动器按需补充中文、已识别的插件与本地 marketplace 配置，写前备份并校验 TOML；不改模型供应商、API 地址或 token。备份是配置写入前的快照，不保证是首次安装前的原始配置。

## 7. 实现与开发说明

### 启动流程

```text
CLICKME.cmd（检查 VBS 编码）
  -> scripts/start-codex.vbs
  -> 查找 pythonw.exe / python.exe
  -> codex_zh_launch.py
     -> 定位当前 MSIX 安装包，只读扫描 ASAR
     -> 按功能生成策略，按需补配置
     -> 复用调试实例，或通过 AppX 包身份启动官方应用
     -> --remote-debugging-port=0，由系统分配回环端口
     -> 从 DevToolsActivePort 读取实际端口
     -> 通过 CDP 注册首帧前脚本，并对当前页面应用补丁
     -> 核验有效覆盖项，写报告并退出
```

中文资源由官方提供，启用与否还受远端 layer 控制。电脑操控涉及主进程环境、插件与渲染层 gate。布局使用官方组件，不改 DOM/CSS，不伪造服务端响应。

未登录或使用第三方 provider 不等于完全无法获取远端配置；官方存在多条初始化路径。远端配置获取失败与需要工作区身份的云端请求失败，应分别排查。

### 文件结构

```text
Codex-fix/
├── CLICKME.cmd              # 编码检查后直接启动
├── repair-codex.cmd         # 双击检测修复入口
├── README.md
├── scripts/                # Python / PowerShell / VBS 运行脚本
│   ├── start-codex.vbs
│   ├── repair-entry.ps1
│   ├── codex_zh_launch.py
│   ├── activate_codex.py
│   ├── repair_codex.py
│   └── runtime_diagnostics.py
├── output/                 # .gitkeep 保留目录，运行产物由 Git 忽略
│   ├── logs/               # 日志、核验报告、端口缓存与修复锁
│   └── backups/            # 编码、源码与配置备份
└── tools/                  # 自动化测试与调试工具
```

### 测试

开发环境需要 Python、`websockets`；自动化测试还需要 PATH 中有 Node.js：

```powershell
& 'C:\实际路径\python.exe' -m unittest discover -s tools -p 'test_*.py' -v
```

以下手工集成测试会关闭并重启 Codex，**仅在无任务运行时执行**：

```powershell
& 'C:\实际路径\python.exe' .\tools\check_port_lifecycle.py
```

### 维护注意事项

- 不改官方包：MSIX ACL 与 Electron ASAR 完整性校验可能阻止或拒绝修改。
- 不固定 CDP 端口，不扫描其他端口兜底；读取不到实际端口就明确失败。
- 启动器只是 CDP 客户端，不监听 TCP、不常驻。客户端退出不等于 Codex 调试端口关闭，不要将端口暴露给不可信网络或程序。
- 重启需结束完整进程树；窗口关闭后后台存活，不能直接判断为端口泄漏。
- AppX 激活在独立线程执行，避免 asyncio 初始化 COM 后与 STA 冲突。
- 发布到其他电脑前检查 VBS 启动入口编码：使用 UTF-16 LE BOM。

## 免责声明

个人自用工具，与 OpenAI 无关联。不修改、不重新分发官方 Codex 安装文件；仓库不应包含账号配置、密钥或对话数据。请自行评估运行时功能覆盖与调试端口带来的风险。
