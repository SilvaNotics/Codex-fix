# 只需 Windows 自带的 Windows PowerShell 5.1 即可运行
# 用法：
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -NoRestart      # 不重启 explorer
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -SkipTaskbar    # 只建桌面快捷方式
[CmdletBinding()]
param(
    [switch]$SkipTaskbar,
    [switch]$NoRestart
)

$ErrorActionPreference = 'Stop'

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$vbs = Join-Path $dir 'start-codex.vbs'
$ico = Join-Path $dir 'assets\codex.ico'
$wscript = Join-Path $env:WINDIR 'System32\wscript.exe'
$appUserModelId = 'OpenAI.Codex_2p2nqsd0c76g0!App'

foreach ($f in @($vbs, $ico, (Join-Path $dir 'codex_zh_launch.py'), (Join-Path $dir 'repair_codex.py'), (Join-Path $dir 'runtime_diagnostics.py'), (Join-Path $dir 'activate_codex.py'))) {
    if (-not (Test-Path -LiteralPath $f)) { throw "缺少文件: $f" }
}

$shell = New-Object -ComObject WScript.Shell

# 给 .lnk 写 System.AppUserModel.ID。
# 注意：必须走 IShellLink -> IPropertyStore -> IPersistFile.Save，
# 用 SHGetPropertyStoreFromParsingName 直接写会把 target/args 弄丢。
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;

[ComImport, Guid("00021401-0000-0000-C000-000000000046")]
public class ShellLinkCoClass { }

[StructLayout(LayoutKind.Sequential)] public struct PROPERTYKEY { public Guid fmtid; public uint pid; }
[StructLayout(LayoutKind.Explicit)] public struct PROPVARIANT {
  [FieldOffset(0)] public ushort vt;
  [FieldOffset(8)] public IntPtr pwszVal;
}

[ComImport, Guid("886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IPropertyStore {
  void GetCount(out uint c);
  void GetAt(uint i, out PROPERTYKEY k);
  void GetValue(ref PROPERTYKEY k, out PROPVARIANT v);
  void SetValue(ref PROPERTYKEY k, ref PROPVARIANT v);
  void Commit();
}

[ComImport, Guid("0000010b-0000-0000-C000-000000000046"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IPersistFile {
  void GetClassID(out Guid clsid);
  void IsDirty();
  void Load([MarshalAs(UnmanagedType.LPWStr)] string f, uint mode);
  void Save([MarshalAs(UnmanagedType.LPWStr)] string f, bool remember);
  void SaveCompleted([MarshalAs(UnmanagedType.LPWStr)] string f);
  void GetCurFile([MarshalAs(UnmanagedType.LPWStr)] out string f);
}

public static class LnkAppUserModelId {
  public static void Set(string lnkPath, string aumid) {
    object o = new ShellLinkCoClass();
    IPersistFile pf = (IPersistFile)o;
    pf.Load(lnkPath, 2);                       // STGM_READWRITE：保留原 target/args/icon
    IPropertyStore ps = (IPropertyStore)o;
    PROPERTYKEY key = new PROPERTYKEY();
    key.fmtid = new Guid("9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3");  // PKEY_AppUserModel_ID
    key.pid = 5;
    PROPVARIANT pv = new PROPVARIANT();
    pv.vt = 31;                                // VT_LPWSTR
    pv.pwszVal = Marshal.StringToCoTaskMemUni(aumid);
    ps.SetValue(ref key, ref pv);
    ps.Commit();
    Marshal.FreeCoTaskMem(pv.pwszVal);
    pf.Save(lnkPath, true);
    Marshal.ReleaseComObject(o);
  }
}
'@

function Set-LnkAppUserModelId {
    param([string]$lnkPath, [string]$aumid)
    [LnkAppUserModelId]::Set($lnkPath, $aumid)
}

function New-CodexShortcut([string]$path) {
    if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Force }
    $s = $shell.CreateShortcut($path)
    $s.TargetPath = $wscript
    $s.Arguments = '"' + $vbs + '"'
    $s.WorkingDirectory = $dir
    $s.IconLocation = "$ico,0"
    $s.Description = 'Codex 桌面版（中文界面 + 电脑操控）'
    $s.WindowStyle = 7
    $s.Save()
    Write-Host "  已创建 $path"
}

Write-Host '[1/3] 桌面快捷方式'
New-CodexShortcut (Join-Path $shell.SpecialFolders('Desktop') 'Codex 中文.lnk')

if (-not $SkipTaskbar) {
    Write-Host '[2/3] 任务栏固定项'
    $pinDir = Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'
    $pin = Join-Path $pinDir 'Codex 中文.lnk'
    New-CodexShortcut $pin
    Set-LnkAppUserModelId -lnkPath $pin -aumid $appUserModelId
    Write-Host "  AUMID = $appUserModelId （保证运行时和固定项合并成一个图标）"
}

if (-not $NoRestart -and -not $SkipTaskbar) {
    Write-Host '[3/3] 重启 explorer 让固定项生效'
    Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    if (-not (Get-Process explorer -ErrorAction SilentlyContinue)) { Start-Process explorer.exe }
    Start-Sleep -Seconds 5
}

Write-Host ''
Write-Host '完成。双击桌面「Codex 中文」即可；从启动到界面渲染约 60~90 秒（中转超时所致）。'
