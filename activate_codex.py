"""用 IApplicationActivationManager 以“包身份”启动 Codex，并附带启动参数。

好处：进程带 package identity，任务栏/开始菜单用 MSIX 官方图标素材（清晰），
      同时 --remote-debugging-port 能生效，补丁照样注入。
"""
import ctypes
from ctypes import wintypes

CLSID_ApplicationActivationManager = "{45BA127D-10A8-46EA-8AB7-56EA9078943C}"
IID_IApplicationActivationManager = "{2E941141-7F97-4756-BA1D-9DECDE894A3D}"


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


def guid(s):
    g = GUID()
    ctypes.oledll.ole32.CLSIDFromString(s, ctypes.byref(g))
    return g


def activate(aumid, args, timeout_ms=0):
    ole32 = ctypes.windll.ole32
    ole32.CoInitializeEx(None, 2)  # STA；若当前线程已是 MTA 会失败，忽略即可
    p = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(ctypes.byref(guid(CLSID_ApplicationActivationManager)), None, 1,
                                ctypes.byref(guid(IID_IApplicationActivationManager)),
                                ctypes.byref(p))
    if hr != 0:
        return hr, 0
    # vtable: 0 QueryInterface,1 AddRef,2 Release,3 ActivateApplication,4 ActivateForFile,...
    vt = ctypes.cast(p, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    ActivateApplication = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                                             wintypes.LPCWSTR, wintypes.LPCWSTR,
                                             ctypes.c_int, ctypes.POINTER(wintypes.DWORD))(vt[3])
    pid = wintypes.DWORD(0)
    hr = ActivateApplication(p, aumid, args, 0, ctypes.byref(pid))
    release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vt[2])
    release(p)
    return hr, pid.value


if __name__ == "__main__":
    import sys
    aumid = "OpenAI.Codex_2p2nqsd0c76g0!App"
    args = sys.argv[1] if len(sys.argv) > 1 else ""
    hr, pid = activate(aumid, args)
    print(f"hr=0x{hr & 0xFFFFFFFF:08X} pid={pid}")
