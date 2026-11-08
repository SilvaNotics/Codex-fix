' 启动 Codex 中文版（隐藏窗口）。
' 目的：不把 Python 路径写死 —— Hermes 重装/升级后 installs 下的哈希目录会变，
' 写死就会双击无反应且没有任何提示。这里运行时动态找 pythonw。
Option Explicit
Dim fso, sh, base, logFile, script, pyw, py, f, g, instDir, envDir, line

Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")

base     = fso.GetParentFolderName(WScript.ScriptFullName)   ' 脚本所在目录，跟着仓库走
logFile  = base & "\vbs.log"
script   = base & "\codex_zh_launch.py"
pyw      = ""

' 1) Hermes 托管的 venv（当前实际使用的那个）：installs\<id>\environments\<id>\venv
instDir = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%\hermes\installs")
If fso.FolderExists(instDir) Then
    For Each f In fso.GetFolder(instDir).SubFolders
        envDir = f.Path & "\environments"
        If fso.FolderExists(envDir) Then
            For Each g In fso.GetFolder(envDir).SubFolders
                If fso.FileExists(g.Path & "\venv\Scripts\pythonw.exe") Then
                    pyw = g.Path & "\venv\Scripts\pythonw.exe"
                End If
            Next
        End If
    Next
End If

' 2) 退路：传统安装的 pythonw / python
If pyw = "" Then
    pyw = FindOnPath("pythonw.exe")
End If
If pyw = "" Then
    py = FindOnPath("python.exe")
    If py <> "" Then pyw = py
End If

If pyw = "" Then
    Log "找不到可用的 Python（Hermes venv 不在 %LOCALAPPDATA%\hermes\installs 下，PATH 里也没有）"
    MsgBox "找不到 Python，无法启动 Codex 中文版。" & vbCrLf & vbCrLf & _
           "请先打开一次 Hermes（它会重建自带 Python），或重新安装 Hermes。", 16, "Codex 中文"
    WScript.Quit 1
End If

Log "使用 Python: " & pyw
sh.Run """" & pyw & """ """ & script & """", 0, False

' ---------- 子过程 ----------
Sub Log(msg)
    On Error Resume Next
    Dim t
    Set t = fso.OpenTextFile(logFile, 8, True)
    t.WriteLine Now & "  " & msg
    t.Close
End Sub

Function FindOnPath(exeName)
    Dim p, arr, d
    FindOnPath = ""
    p = sh.ExpandEnvironmentStrings("%PATH%")
    arr = Split(p, ";")
    For Each d In arr
        If d <> "" Then
            If fso.FileExists(fso.BuildPath(d, exeName)) Then
                FindOnPath = fso.BuildPath(d, exeName)
                Exit Function
            End If
        End If
    Next
End Function
