"""Small Windows adapter for finding desktop icons Pikita can actually see."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
import random

import pygame
import win32gui
import win32ui
from win32com.shell import shell, shellcon

LVM_FIRST = 0x1000
LVM_GETITEMCOUNT = LVM_FIRST + 4
LVM_GETITEMPOSITION = LVM_FIRST + 16
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04
GA_ROOT = 2


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


@dataclass(frozen=True)
class DesktopIcon:
    center: tuple[int, int]
    image: pygame.Surface


class DesktopIcons:
    """Read Explorer's icon coordinates; never treats hidden icons as food."""

    def __init__(self) -> None:
        self._user = ctypes.windll.user32
        self._kernel = ctypes.windll.kernel32
        self._user.FindWindowExW.restype = wintypes.HWND
        self._user.SendMessageW.restype = ctypes.c_ssize_t
        self._user.WindowFromPoint.restype = wintypes.HWND
        self._user.GetAncestor.restype = wintypes.HWND
        self._kernel.OpenProcess.restype = wintypes.HANDLE
        self._kernel.VirtualAllocEx.restype = ctypes.c_void_p

    def choose_visible(
        self,
        near: tuple[int, int] | None = None,
        monitor: tuple[int, int, int, int] | None = None,
    ) -> DesktopIcon | None:
        list_view = self._desktop_list_view()
        if not list_view:
            return None
        count = self._user.SendMessageW(list_view, LVM_GETITEMCOUNT, 0, 0)
        if count <= 0:
            return None
        candidates = list(range(count))
        if near is None:
            random.shuffle(candidates)
        else:
            candidates.sort(key=lambda index: self._distance_to_item(list_view, index, near))
        for index in candidates[:12]:
            point = self._item_position(list_view, index)
            center = (point[0] + 16, point[1] + 16) if point is not None else None
            if (
                point is None
                or (monitor is not None and not self._point_in_monitor(center, monitor))
                or not self._is_desktop_at(list_view, point)
            ):
                continue
            surface = self._shell_icon(index)
            if surface is not None:
                return DesktopIcon((point[0] + 16, point[1] + 16), surface)
        return None

    @staticmethod
    def _point_in_monitor(point: tuple[int, int], monitor: tuple[int, int, int, int]) -> bool:
        return monitor[0] <= point[0] < monitor[2] and monitor[1] <= point[1] < monitor[3]

    def _distance_to_item(self, list_view, index: int, near: tuple[int, int]) -> float:
        point = self._item_position(list_view, index)
        if point is None:
            return float("inf")
        return (point[0] - near[0]) ** 2 + (point[1] - near[1]) ** 2

    @staticmethod
    def _shell_icon(index: int) -> pygame.Surface | None:
        """Get transparent icon pixels from the Windows Shell, not a screenshot."""
        folders = [os.path.join(os.path.expanduser("~"), "Desktop")]
        public_desktop = os.path.join(os.environ.get("PUBLIC", r"C:\\Users\\Public"), "Desktop")
        if os.path.isdir(public_desktop):
            folders.append(public_desktop)
        paths = [os.path.join(folder, name) for folder in folders if os.path.isdir(folder)
                 for name in sorted(os.listdir(folder)) if name.lower() != "desktop.ini"]
        if not paths:
            return None
        try:
            result = shell.SHGetFileInfo(
                paths[index % len(paths)], 0, shellcon.SHGFI_ICON | shellcon.SHGFI_LARGEICON
            )
            icon = result[1][0]
            icon_info = win32gui.GetIconInfo(icon)
            bitmap = win32ui.CreateBitmapFromHandle(icon_info[4])
            info = bitmap.GetInfo()
            pixels = bitmap.GetBitmapBits(True)
            return pygame.image.frombuffer(
                pixels, (info["bmWidth"], info["bmHeight"]), "BGRA"
            ).copy()
        except (OSError, win32gui.error):
            return None
        finally:
            if "icon" in locals():
                win32gui.DestroyIcon(icon)
            if "icon_info" in locals():
                win32gui.DeleteObject(icon_info[3])
                win32gui.DeleteObject(icon_info[4])

    def _desktop_list_view(self):
        progman = self._user.FindWindowW("Progman", None)
        def_view = self._user.FindWindowExW(progman, None, "SHELLDLL_DefView", None)
        if not def_view:
            worker = None
            while True:
                worker = self._user.FindWindowExW(None, worker, "WorkerW", None)
                if not worker:
                    return None
                def_view = self._user.FindWindowExW(worker, None, "SHELLDLL_DefView", None)
                if def_view:
                    break
        return self._user.FindWindowExW(def_view, None, "SysListView32", None)

    def _item_position(self, list_view, index: int) -> tuple[int, int] | None:
        process_id = wintypes.DWORD()
        self._user.GetWindowThreadProcessId(list_view, ctypes.byref(process_id))
        process = self._kernel.OpenProcess(
            PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE, False, process_id.value
        )
        if not process:
            return None
        remote = self._kernel.VirtualAllocEx(
            process, None, ctypes.sizeof(_Point), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE
        )
        try:
            if not remote or not self._user.SendMessageW(list_view, LVM_GETITEMPOSITION, index, remote):
                return None
            point = _Point()
            read = ctypes.c_size_t()
            if not self._kernel.ReadProcessMemory(
                process, remote, ctypes.byref(point), ctypes.sizeof(point), ctypes.byref(read)
            ):
                return None
            if not self._user.ClientToScreen(list_view, ctypes.byref(point)):
                return None
            return point.x, point.y
        finally:
            if remote:
                self._kernel.VirtualFreeEx(process, remote, 0, MEM_RELEASE)
            self._kernel.CloseHandle(process)

    def _is_desktop_at(self, list_view, point: tuple[int, int]) -> bool:
        top_window = self._user.WindowFromPoint(_Point(*point))
        return self._user.GetAncestor(top_window, GA_ROOT) == self._user.GetAncestor(list_view, GA_ROOT)
