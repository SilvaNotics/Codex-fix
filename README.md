# Codex-fix：Windows Codex 中文化与功能开关启动器

在不修改官方 Codex 安装文件的前提下，通过启动时的运行时注入，启用已识别的中文界面、电脑操控、浏览器操控与官方导航布局开关。

**这是官方桌面版的辅助启动器，不是独立客户端，不提供账号、模型 API 或云端权限。**

已验证安装包：`OpenAI.Codex 26.1103.4239.0`（Windows MSIX，x64）。新版兼容性以实际扫描和核验结果为准。

## 1. 功能与限制

| 项目 | 本项目的作用 |
|---|---|
| 中文界面 | 覆盖已识别的语言开关，按需补充中文配置 |
| 电脑操控 / Chrome / 应用内浏览器 | 配合主进程环境、插件配置与渲染层开关启用入口 |
| 官方导航布局 | 明确匹配时启用官方组件，不修改 DOM/CSS |
| 更新适配 | 每次启动扫描安装包，按功能独立匹配；无法识别的项交回官方默认 |
| 核验报告 | 输出有效覆盖项的检查结果与回退原因 |

注意：

- 不绕过登录、工作区身份、订阅、额度或云端权限。`Workspace routing is unavailable` 不能靠本地开关修复。
- 开启入口不代表任务已端到端可用。模型、网络、Node REPL 和 Windows 沙箱仍可能独立出错。
- 不保证任意未来版本都能适配；无法识别不等于功能被移除，也不会猜测开关 ID。
- 通过本项目入口启动才会执行补丁。从开始菜单打开官方入口不会自动注入。

## 2. 安装与首次启动

### 2.1 环境要求

- Windows 10/11 x64。
- **MSIX / Microsoft Store 版官方 Codex**，能通过 `Get-AppxPackage -Name OpenAI.Codex` 找到。
- **Python 3.11+**，并在同一解释器环境中安装 **`websockets`**。
- Windows 自带的 Windows PowerShell 5.1 与 Windows Script Host。

**不需要安装 Hermes，不需要修改系统区域设置，也不要求默认以管理员身份运行。** Hermes 自带 Python 只是可选来源。

使用独立 Python 时，将其加入 PATH，并用实际解释器路径安装依赖、检查环境：

```powershell
# 替换为真实路径，不要指向 WindowsApps 的商店占位程序
& 'C:\实际路径\python.exe' -m pip install websockets
& 'C:\实际路径\python.exe' -c "import sys, websockets; print(sys.version); print(sys.executable)"
```

当前 VBS 入口优先查找 Hermes venv，其次查找 PATH 中的 `pythonw.exe` / `python.exe`。确保入口实际选中的解释器具备依赖。VBS 中“打开或安装 Hermes”的提示不是唯一解决办法，独立 Python 同样可用。

### 2.2 下载完整项目

下载仓库 ZIP 并完整解压，或使用 Git 克隆。保留脚本与 `assets` 的相对位置，不要只复制一个 VBS 文件。

在包含 `install.ps1`、`start-codex.vbs` 和 `codex_zh_launch.py` 的目录打开 PowerShell。

> **跨电脑编码提醒：** 安装器出现 `using System` 解析错误，或 VBS 提示“未结束的字符串常量 / 800A0409”时，先按第 5.1 节转换编码。无需为此重装 Codex、调整沙箱或修改系统区域设置。

### 2.3 创建快捷方式

确认 Codex 没有正在执行的任务，然后运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

默认创建桌面快捷方式和任务栏目录中的快捷方式，并重启 Explorer。任务栏是否立即显示固定项也受 Windows 版本与策略影响。

| 参数 | 用途 |
|---|---|
| `-SkipTaskbar` | 只创建桌面快捷方式，不处理任务栏，也不重启 Explorer |
| `-NoRestart` | 创建快捷方式，但不自动重启 Explorer |

例如，只安装桌面入口：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -SkipTaskbar
```

### 2.4 启动

双击桌面的 **Codex 中文**，或直接双击 `start-codex.vbs`。

也可直接用自有 Python 启动，绕过 VBS 的解释器查找：

```powershell
& 'C:\实际路径\python.exe' .\codex_zh_launch.py
```

## 3. 日常使用与结果检查

| 当前状态 | 启动器行为 |
|---|---|
| Codex 未运行 | 启动官方应用，获取随机调试端口后注入并核验 |
| 已有可连接的调试实例 | 连接现有实例，执行所需注入与核验 |
| 已有不带调试端口的实例 | 结束原进程树，再通过项目入口重启 |
| 旧补丁运行中且策略指纹变化 | 重启应用，清除旧内存覆盖后应用新策略 |

**启动器可能关闭并重启 Codex，请先结束或保存正在执行的任务。** 不要在任务中运行修复入口或反复双击启动器。

启动受官方远端请求影响，可能在 logo 页面停留几十秒。持续无进展时请查日志。

### 日志与报告

以下文件保存在启动器所在目录：

| 文件 | 内容 |
|---|---|
| `vbs.log` | VBS 入口选中的 Python |
| `launch.log` | 配置补充、应用启动、CDP 连接与核验过程 |
| `verification.json` | `checking` / `passed` / `failed`，以及各功能覆盖或回退情况 |
| `repair-report.json` | 修复工具扫描证据与处理结果 |
| `cdp_port.txt` | 调试端口缓存；只是文本，不会占用端口 |

**`passed` 仅表示本次有效覆盖项通过核验。** 某功能为 `official-default` 不意味着已启用；报告也不证明实际操控任务、沙箱或云服务可用。

## 4. Codex 更新后的检测与修复

先通过项目入口正常启动。启动器每次扫描当前安装包，不需要手填开关 ID。

若功能没有恢复，且没有正在执行的任务，可双击：

```text
repair-codex.cmd
```

它寻找 Python 3.11+ 与 `websockets`，扫描安装包并调用启动器检查；必要时可能重启 Codex。它不是保证修好所有新版的工具。

### 自动适配规则

- 中文、电脑操控、两类浏览器操控与布局按功能独立匹配。
- 唯一且结构明确的匹配生成运行时覆盖。
- 结构缺失、候选歧义或跨功能 ID 冲突时，该项使用 `official-default`，既不强制开启，也不强制关闭。
- 回退项不新增对应语言或插件配置；已有用户配置不擅自删除。
- SDK/CDP 整体异常或安装包损坏仍明确报错，不以回退掩盖失败。
- 已知结构内的 ID / 混淆变量改名可适配；功能实现、打包结构或 SDK 行为大改仍需人工处理。

只扫描，不启动应用：

```powershell
& 'C:\实际路径\python.exe' './repair_codex.py' --scan-only
```

对已有实例只做核验，不注入、不改配置、不启动或重启应用（会更新核验报告）：

```powershell
& 'C:\实际路径\python.exe' .\codex_zh_launch.py --verify-only
```

工具仅操作所在目录。源码仓库与部署副本不会自动同步。当前动态策略不改启动器源码；仅兼容旧启动器的源码修复分支会生成 `.bak-repair-*` 备份。

## 5. 故障排查

### 5.1 脚本编码兼容性：PowerShell 与 VBScript

**典型情况：同一项目在一台电脑正常，另一台电脑还没启动 Codex 就报语法错误。**

| 入口 | 可能看到的报错 |
|---|---|
| `install.ps1` | `using System`、`using 语句必须出现在…之前`、`MissingUsingStatementDirective`，随后大量括号错误 |
| `start-codex.vbs` | “未结束的字符串常量”，错误代码 `800A0409` |

包含中文的 UTF-8 无 BOM 脚本可能在不同系统代码页下被错误解码。Windows PowerShell 5.1 与传统 Windows Script Host 的编码处理不同，推荐格式为：

- **PS1：UTF-8 带 BOM。**
- **VBS：UTF-16 LE 带 BOM。不要把 VBS 也统一保存为 UTF-8 BOM。**

已有跨电脑使用者反馈，转换两个入口后恢复正常。**不是所有同类错误都由编码造成**，源码截断或引号损坏也会产生相同症状。

#### 一次修复两个入口

在项目目录打开 PowerShell，执行以下命令。它先备份，再将仓库下载的原始 UTF-8 文件转换成兼容格式；重复执行不覆盖首份备份。

```powershell
# install.ps1 -> UTF-8 with BOM
$p = (Resolve-Path .\install.ps1).Path
if (-not (Test-Path -LiteralPath "$p.encoding.bak")) {
    Copy-Item -LiteralPath $p -Destination "$p.encoding.bak"
}
$text = [System.IO.File]::ReadAllText($p, [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText(
    $p, $text, (New-Object System.Text.UTF8Encoding($true))
)

# start-codex.vbs -> UTF-16 LE with BOM
$p = (Resolve-Path .\start-codex.vbs).Path
if (-not (Test-Path -LiteralPath "$p.encoding.bak")) {
    Copy-Item -LiteralPath $p -Destination "$p.encoding.bak"
}
$text = [System.IO.File]::ReadAllText($p, [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText(
    $p, $text, [System.Text.Encoding]::Unicode
)
```

然后重新运行安装器，再从项目入口启动：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

注意：

- `ReadAllText` 会识别已有 BOM，因此命令也可处理已正确转换的文件。
- 文件若已经错误解码并保存，转码无法找回丢失的字符；请重新下载原文件后再操作。
- 管理员权限、`ExecutionPolicy Bypass`、关闭沙箱均不能修复源码解析错误，无需更改系统 UTF-8 区域设置。
- 转换后仍报错时，请提供实际出错的原文件、行号和 Windows / PowerShell 版本，不要只提供截图。
- 撤销转换：将对应 `.encoding.bak` 复制回原文件。
- 本节是手动修复方法，不代表仓库入口已经自动转码。

### 5.2 其他问题

| 现象 | 优先检查 |
|---|---|
| 双击入口没反应 | 排除 VBS 编译错误，再看 `vbs.log` 的解释器路径与 `launch.log` |
| 找不到 Python / `No module named websockets` | 安装真实 Python，在入口实际选择的解释器中安装依赖；WindowsApps 商店占位程序不算可用解释器 |
| 界面英文 / 布局没变化 | 检查 `verification.json` 对应功能是覆盖、回退还是失败，再看日志 |
| 没有电脑操控入口 | 检查功能匹配、插件配置与主进程环境；入口存在不代表任务权限完整 |
| 长时间等待 `DevToolsActivePort` | 检查应用是否启动、是否回退为 `popen`；无任务时完全退出后重试 |
| 任务栏两个图标 / 图标模糊 | 检查快捷方式 AUMID 与启动方式；`popen` 回退没有正常 AppX 包身份 |
| `Workspace routing is unavailable` | 检查真实账号、工作区与官方服务网络；本项目不伪造云端权限 |
| “始终允许的应用”列表为空 | 检查 app tools / `cua_repl` 与账号状态；`authStatus=unsupported` 不能靠界面开关解决 |
| REPL 内核退出 / `windows sandbox failed` | 检查 Codex 自身 REPL 与沙箱日志；这是运行时问题，不能凭本项目的 `passed` 判断已修复 |

## 6. 卸载与回滚

1. 删除项目创建的桌面快捷方式和任务栏固定项。
2. **完全退出 Codex**，再从官方入口启动，清除进程内覆盖。只关闭窗口可能仍在后台运行。
3. 官方 `app.asar`、`chrome.dll` 等安装文件未被修改，无需恢复官方包。
4. 如需撤销配置补充，参考 `%USERPROFILE%\.codex\config.toml.bak-codexzh`。**先备份当前配置并比较差异，不要直接覆盖，以免丢失后续新增的模型或供应商设置。**

启动器按需补充中文、已识别的插件与本地 marketplace 配置，写前备份并校验 TOML；不改模型供应商、API 地址或 token。备份是配置写入前的快照，不保证是首次安装前的原始配置。

## 7. 实现与开发说明

### 启动流程

```text
桌面快捷方式 / start-codex.vbs
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
├── codex_zh_launch.py       # 启动、动态策略、CDP 注入、配置补充与核验
├── activate_codex.py        # AppX 激活封装
├── start-codex.vbs          # 隐藏窗口启动入口
├── install.ps1             # 创建快捷方式与设置 AUMID
├── repair-codex.cmd         # 双击检测修复入口
├── repair-entry.ps1         # 查找并验证 Python 环境
├── repair_codex.py          # 结构匹配与兼容旧版的修复工具
├── assets/                 # 快捷方式图标
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
- 快捷方式 AUMID 通过 `IShellLink -> IPropertyStore -> IPersistFile.Save` 写入，保留 target、args 与 icon。
- 发布到其他电脑前检查中文入口编码：PS1 用 UTF-8 BOM，VBS 用 UTF-16 LE BOM。

## 免责声明

个人自用工具，与 OpenAI 无关联。不修改、不重新分发官方 Codex 安装文件；仓库不应包含账号配置、密钥或对话数据。请自行评估运行时功能覆盖与调试端口带来的风险。
