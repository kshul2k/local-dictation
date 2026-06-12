from __future__ import annotations

import argparse
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from urllib import error, request

from runtime_paths import LOG_DIR, ROOT_DIR, log_path, run_path


APP_NAME = "Local Dictation Cleanup"
SERVER_HEALTH_URL = "http://127.0.0.1:8765/health"
WATCHER_MUTEX_NAME = "Local\\LocalDictationOpenWhisprDbWatcher"
TRAY_MUTEX_NAME = "Local\\LocalDictationTrayMonitor"
DISABLED_FLAG_PATH = run_path("cleanup_disabled.flag")
LOG_PATH = log_path("tray_monitor.log")

POWERSHELL_EXE = (
    Path(os.environ.get("SystemRoot", r"C:\Windows"))
    / "System32"
    / "WindowsPowerShell"
    / "v1.0"
    / "powershell.exe"
)

START_STACK_SCRIPT = ROOT_DIR / "start_local_dictation_stack.ps1"
STOP_WATCHER_SCRIPT = ROOT_DIR / "stop_openwhispr_db_watcher.ps1"
STOP_SERVER_SCRIPT = ROOT_DIR / "stop_cleanup_server.ps1"

if sys.platform != "win32":
    raise SystemExit("The tray monitor only runs on Windows.")

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

for _handle_name in ("HICON", "HCURSOR", "HBRUSH", "HMENU", "HINSTANCE", "HMODULE"):
    if not hasattr(wintypes, _handle_name):
        setattr(wintypes, _handle_name, wintypes.HANDLE)

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(
    LRESULT,
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
)

WM_DESTROY = 0x0002
WM_COMMAND = 0x0111
WM_TIMER = 0x0113
WM_USER = 0x0400
WM_TRAYICON = WM_USER + 20
WM_RBUTTONUP = 0x0205
WM_LBUTTONDBLCLK = 0x0203

NIM_ADD = 0x00000000
NIM_MODIFY = 0x00000001
NIM_DELETE = 0x00000002
NIF_MESSAGE = 0x00000001
NIF_ICON = 0x00000002
NIF_TIP = 0x00000004

MF_STRING = 0x00000000
MF_GRAYED = 0x00000001
MF_SEPARATOR = 0x00000800

TPM_RIGHTBUTTON = 0x0002
TPM_BOTTOMALIGN = 0x0020
TPM_LEFTALIGN = 0x0000

IDI_APPLICATION = 32512
IDI_HAND = 32513
IDI_EXCLAMATION = 32515
IDI_ASTERISK = 32516

ERROR_ALREADY_EXISTS = 183
SYNCHRONIZE = 0x00100000

TIMER_ID = 1
TIMER_INTERVAL_MS = 5000
TRAY_ICON_ID = 1

ID_ENABLE = 1001
ID_DISABLE = 1002
ID_RESTART = 1003
ID_OPEN_LOGS = 1004
ID_EXIT = 1005


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
    ]


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HCURSOR),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
    ]


kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE
kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.CreateMutexW.restype = wintypes.HANDLE
kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
kernel32.OpenMutexW.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL

user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
user32.LoadIconW.restype = wintypes.HICON
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD,
    wintypes.LPCWSTR,
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.HMENU,
    wintypes.HINSTANCE,
    wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
]
user32.DefWindowProcW.restype = LRESULT
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_size_t, wintypes.LPCWSTR]
user32.TrackPopupMenu.argtypes = [
    wintypes.HMENU,
    wintypes.UINT,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HWND,
    wintypes.LPVOID,
]
user32.DestroyMenu.argtypes = [wintypes.HMENU]

shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL


def _make_int_resource(resource_id: int) -> wintypes.LPCWSTR:
    return ctypes.cast(ctypes.c_void_p(resource_id), wintypes.LPCWSTR)


def _creation_flags() -> int:
    return subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP


def log_event(message: str) -> None:
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with LOG_PATH.open("a", encoding="utf-8") as log_file:
        log_file.write(f"{timestamp} {message}\n")


def run_powershell(script_path: Path, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    command = [
        str(POWERSHELL_EXE),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
    ]
    return subprocess.run(
        command,
        cwd=ROOT_DIR,
        text=True,
        capture_output=True,
        timeout=timeout,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )


def launch_powershell(script_path: Path) -> None:
    command = [
        str(POWERSHELL_EXE),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT_DIR,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=_creation_flags(),
    )
    log_event(f"launch_script script={script_path.name} pid={process.pid}")


def is_server_running() -> bool:
    try:
        with request.urlopen(SERVER_HEALTH_URL, timeout=0.75) as response:
            return response.status == 200
    except (OSError, error.URLError):
        return False


def is_mutex_present(name: str) -> bool:
    handle = kernel32.OpenMutexW(SYNCHRONIZE, False, name)
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return False


def is_watcher_running() -> bool:
    return is_mutex_present(WATCHER_MUTEX_NAME)


def is_disabled() -> bool:
    return DISABLED_FLAG_PATH.exists()


@dataclass(frozen=True)
class CleanupStatus:
    state: str
    server_running: bool
    watcher_running: bool
    disabled: bool

    @property
    def label(self) -> str:
        labels = {
            "running": "Running",
            "partial": "Partial",
            "disabled": "Disabled",
            "stopped": "Stopped",
        }
        return labels.get(self.state, self.state.title())

    @property
    def tooltip(self) -> str:
        return f"{APP_NAME}: {self.label}"


def get_cleanup_status() -> CleanupStatus:
    disabled = is_disabled()
    server_running = is_server_running()
    watcher_running = is_watcher_running()
    if disabled:
        state = "disabled"
    elif server_running and watcher_running:
        state = "running"
    elif server_running or watcher_running:
        state = "partial"
    else:
        state = "stopped"
    return CleanupStatus(
        state=state,
        server_running=server_running,
        watcher_running=watcher_running,
        disabled=disabled,
    )


def acquire_single_instance_mutex() -> wintypes.HANDLE | None:
    ctypes.set_last_error(0)
    handle = kernel32.CreateMutexW(None, True, TRAY_MUTEX_NAME)
    last_error = ctypes.get_last_error()
    if not handle:
        raise ctypes.WinError(last_error)
    if last_error == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return None
    return handle


def enable_cleanup() -> None:
    try:
        DISABLED_FLAG_PATH.unlink(missing_ok=True)
    except OSError as exc:
        log_event(f"enable_remove_disabled_flag_failed error={exc!r}")
    launch_powershell(START_STACK_SCRIPT)
    log_event("enable_requested")


def disable_cleanup() -> None:
    DISABLED_FLAG_PATH.write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    for script_path in (STOP_WATCHER_SCRIPT, STOP_SERVER_SCRIPT):
        try:
            result = run_powershell(script_path)
            stdout = result.stdout.strip().replace("\n", " | ")
            stderr = result.stderr.strip().replace("\n", " | ")
            log_event(
                f"disable_script script={script_path.name} returncode={result.returncode} "
                f"stdout={stdout!r} stderr={stderr!r}"
            )
        except Exception as exc:
            log_event(f"disable_script_failed script={script_path.name} error={exc!r}")
    log_event("disable_requested")


def restart_cleanup() -> None:
    disable_cleanup()
    time.sleep(0.5)
    enable_cleanup()
    log_event("restart_requested")


class TrayMonitor:
    def __init__(self, start_on_launch: bool) -> None:
        self.start_on_launch = start_on_launch
        self.hinstance = kernel32.GetModuleHandleW(None)
        self.class_name = "LocalDictationCleanupTrayWindow"
        self.wndproc = WNDPROC(self._wndproc)
        self.hwnd: wintypes.HWND | None = None
        self.current_state = ""
        self.icons = {
            "running": user32.LoadIconW(None, _make_int_resource(IDI_ASTERISK)),
            "partial": user32.LoadIconW(None, _make_int_resource(IDI_EXCLAMATION)),
            "disabled": user32.LoadIconW(None, _make_int_resource(IDI_HAND)),
            "stopped": user32.LoadIconW(None, _make_int_resource(IDI_HAND)),
        }

    def run(self) -> int:
        self._create_window()
        if self.start_on_launch and not is_disabled():
            enable_cleanup()
        self._add_or_update_icon(force=True)
        user32.SetTimer(self.hwnd, TIMER_ID, TIMER_INTERVAL_MS, None)
        log_event("tray_monitor_started")

        message = MSG()
        while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(message))
            user32.DispatchMessageW(ctypes.byref(message))
        return 0

    def _create_window(self) -> None:
        wndclass = WNDCLASSW()
        wndclass.lpfnWndProc = self.wndproc
        wndclass.hInstance = self.hinstance
        wndclass.lpszClassName = self.class_name
        atom = user32.RegisterClassW(ctypes.byref(wndclass))
        if not atom and ctypes.get_last_error() != ERROR_ALREADY_EXISTS:
            raise ctypes.WinError(ctypes.get_last_error())

        hwnd = user32.CreateWindowExW(
            0,
            self.class_name,
            APP_NAME,
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            self.hinstance,
            None,
        )
        if not hwnd:
            raise ctypes.WinError(ctypes.get_last_error())
        self.hwnd = hwnd

    def _icon_for_status(self, status: CleanupStatus) -> wintypes.HICON:
        return self.icons.get(status.state) or self.icons["stopped"]

    def _add_or_update_icon(self, force: bool = False) -> None:
        status = get_cleanup_status()
        if not force and status.state == self.current_state:
            return
        self.current_state = status.state

        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = TRAY_ICON_ID
        data.uFlags = NIF_ICON | NIF_TIP
        data.hIcon = self._icon_for_status(status)
        data.szTip = status.tooltip[:127]
        if force:
            data.uFlags |= NIF_MESSAGE
            data.uCallbackMessage = WM_TRAYICON
            shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data))
        else:
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(data))

    def _delete_icon(self) -> None:
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self.hwnd
        data.uID = TRAY_ICON_ID
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))

    def _show_menu(self) -> None:
        status = get_cleanup_status()
        menu = user32.CreatePopupMenu()
        if not menu:
            return

        self._append_menu(menu, MF_STRING | MF_GRAYED, 0, f"Status: {status.label}")
        self._append_menu(
            menu,
            MF_STRING | (MF_GRAYED if status.state == "running" else 0),
            ID_ENABLE,
            "Enable cleanup",
        )
        self._append_menu(
            menu,
            MF_STRING | (MF_GRAYED if status.state == "disabled" else 0),
            ID_DISABLE,
            "Disable cleanup",
        )
        self._append_menu(menu, MF_STRING, ID_RESTART, "Restart cleanup")
        self._append_menu(menu, MF_SEPARATOR, 0, "")
        self._append_menu(menu, MF_STRING, ID_OPEN_LOGS, "Open logs")
        self._append_menu(menu, MF_STRING, ID_EXIT, "Exit tray")

        point = POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(self.hwnd)
        user32.TrackPopupMenu(
            menu,
            TPM_LEFTALIGN | TPM_BOTTOMALIGN | TPM_RIGHTBUTTON,
            point.x,
            point.y,
            0,
            self.hwnd,
            None,
        )
        user32.DestroyMenu(menu)

    @staticmethod
    def _append_menu(menu: wintypes.HMENU, flags: int, item_id: int, text: str) -> None:
        user32.AppendMenuW(menu, flags, item_id, text)

    def _handle_command(self, command_id: int) -> None:
        if command_id == ID_ENABLE:
            enable_cleanup()
        elif command_id == ID_DISABLE:
            disable_cleanup()
        elif command_id == ID_RESTART:
            restart_cleanup()
        elif command_id == ID_OPEN_LOGS:
            os.startfile(LOG_DIR)  # type: ignore[attr-defined]
        elif command_id == ID_EXIT:
            user32.DestroyWindow(self.hwnd)
            return
        self._add_or_update_icon(force=True)

    def _wndproc(
        self,
        hwnd: wintypes.HWND,
        message: int,
        wparam: wintypes.WPARAM,
        lparam: wintypes.LPARAM,
    ) -> int:
        if message == WM_TRAYICON:
            if int(lparam) in {WM_RBUTTONUP, WM_LBUTTONDBLCLK}:
                self._show_menu()
            return 0
        if message == WM_COMMAND:
            self._handle_command(int(wparam) & 0xFFFF)
            return 0
        if message == WM_TIMER:
            self._add_or_update_icon()
            return 0
        if message == WM_DESTROY:
            self._delete_icon()
            user32.KillTimer(hwnd, TIMER_ID)
            user32.PostQuitMessage(0)
            log_event("tray_monitor_exited")
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)


def print_status_once() -> int:
    status = get_cleanup_status()
    print(
        json.dumps(
            {
                "state": status.state,
                "server_running": status.server_running,
                "watcher_running": status.watcher_running,
                "disabled": status.disabled,
            },
            sort_keys=True,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Dictation Cleanup tray monitor.")
    parser.add_argument("--no-start", action="store_true", help="show the tray without starting cleanup")
    parser.add_argument("--status-once", action="store_true", help="print current status and exit")
    parser.add_argument("--enable", action="store_true", help="start cleanup and exit")
    parser.add_argument("--disable", action="store_true", help="stop cleanup and exit")
    parser.add_argument("--restart", action="store_true", help="restart cleanup and exit")
    args = parser.parse_args()

    if args.enable:
        enable_cleanup()
        return 0
    if args.disable:
        disable_cleanup()
        return 0
    if args.restart:
        restart_cleanup()
        return 0
    if args.status_once:
        return print_status_once()

    mutex_handle = acquire_single_instance_mutex()
    if mutex_handle is None:
        log_event("tray_monitor_already_running")
        return 0

    try:
        monitor = TrayMonitor(start_on_launch=not args.no_start)
        return monitor.run()
    finally:
        kernel32.CloseHandle(mutex_handle)


if __name__ == "__main__":
    raise SystemExit(main())
