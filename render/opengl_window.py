"""OpenGL desktop renderer with an alpha channel OBS can preserve."""

import ctypes
import json
from array import array
from ctypes import wintypes
import math
from pathlib import Path
import random
import time

import pygame
from OpenGL.GL import (
    GL_BLEND,
    GL_COLOR_BUFFER_BIT,
    GL_LINEAR,
    GL_MODELVIEW,
    GL_ONE,
    GL_ONE_MINUS_SRC_ALPHA,
    GL_PROJECTION,
    GL_QUADS,
    GL_RGBA,
    GL_SRC_ALPHA,
    GL_TEXTURE_2D,
    GL_TEXTURE_MAG_FILTER,
    GL_TEXTURE_MIN_FILTER,
    GL_UNSIGNED_BYTE,
    glBegin,
    glBindTexture,
    glBlendFuncSeparate,
    glClear,
    glClearColor,
    glDeleteTextures,
    glEnable,
    glEnd,
    glGenTextures,
    glLoadIdentity,
    glMatrixMode,
    glOrtho,
    glTexCoord2f,
    glTexImage2D,
    glTexParameteri,
    glVertex2f,
    glViewport,
)
from pygame.locals import DOUBLEBUF, OPENGL

from input.events import FrameInput
from pet.intent import PetIntent, Sound
from render.renderer import Renderer

TARGET_HEIGHT = 600
FPS = 60
BACKGROUND = (0.075, 0.085, 0.12)
DRAG_THRESHOLD = 6
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_POPUP = 0x80000000
ULW_ALPHA = 0x2
AC_SRC_ALPHA = 0x1
PM_REMOVE = 0x0001
WM_KEYDOWN = 0x0100
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONDOWN = 0x0204
WM_RBUTTONUP = 0x0205
WM_MOUSEMOVE = 0x0200


def _normalize(name: str) -> str:
    return name.removesuffix(".png").replace(" ", "").lower()


def _squish_from_drag(
    start: tuple[int, int], current: tuple[int, int], size: tuple[int, int]
) -> tuple[float, float]:
    """Turn a drag toward the sprite's center into axis-specific compression."""
    start_x, start_y = start
    x, y = current
    center_x, center_y = size[0] / 2, size[1] / 2
    from_center_x = start_x - center_x
    from_center_y = start_y - center_y
    # Each axis is independent, so a diagonal pull produces a diagonal squish.
    inward_x = abs(from_center_x) - abs(x - center_x)
    inward_y = abs(from_center_y) - abs(y - center_y)
    return (
        max(0.0, min(1.0, inward_x / max(abs(from_center_x), 1))),
        max(0.0, min(1.0, inward_y / max(abs(from_center_y), 1))),
    )


def _walk_offset(walking: bool, seconds: float) -> tuple[float, float]:
    """A small gait that gives a static sprite a sense of weight and motion."""
    if not walking:
        return 0.0, 0.0
    step = math.sin(seconds * 11.0)
    return step * 9.0, -abs(step) * 11.0


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _Size(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class _BlendFunction(ctypes.Structure):
    _fields_ = [
        ("blend_op", ctypes.c_byte),
        ("blend_flags", ctypes.c_byte),
        ("source_constant_alpha", ctypes.c_byte),
        ("alpha_format", ctypes.c_byte),
    ]


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint), ("width", ctypes.c_long), ("height", ctypes.c_long),
        ("planes", ctypes.c_ushort), ("bit_count", ctypes.c_ushort),
        ("compression", ctypes.c_uint), ("size_image", ctypes.c_uint),
        ("x_pels_per_meter", ctypes.c_long), ("y_pels_per_meter", ctypes.c_long),
        ("clr_used", ctypes.c_uint), ("clr_important", ctypes.c_uint),
    ]


class _BitmapInfo(ctypes.Structure):
    _fields_ = [("header", _BitmapInfoHeader), ("colors", ctypes.c_uint * 1)]


class _Msg(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND), ("message", ctypes.c_uint),
        ("w_param", wintypes.WPARAM), ("l_param", wintypes.LPARAM),
        ("time", ctypes.c_uint), ("point", _Point),
    ]


class _WindowClass(ctypes.Structure):
    _fields_ = [
        ("style", ctypes.c_uint), ("window_proc", ctypes.c_void_p),
        ("class_extra", ctypes.c_int), ("window_extra", ctypes.c_int),
        ("instance", wintypes.HINSTANCE), ("icon", wintypes.HANDLE),
        ("cursor", wintypes.HANDLE), ("background", wintypes.HANDLE),
        ("menu_name", wintypes.LPCWSTR), ("class_name", wintypes.LPCWSTR),
    ]


class OpenGLWindow(Renderer):
    def __init__(self, assets_dir: Path):
        self._settings_path = assets_dir.parent / "settings.json"
        settings = self._load_settings()
        pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=512)
        pygame.init()
        pygame.display.gl_set_attribute(pygame.GL_ALPHA_SIZE, 8)

        pngs = sorted(assets_dir.glob("*.png"))
        if not pngs:
            raise FileNotFoundError(f"No .png sprites found in {assets_dir}")

        sample = pygame.image.load(str(pngs[0]))
        scale = TARGET_HEIGHT / sample.get_height()
        self._width = round(sample.get_width() * scale)
        self._height = TARGET_HEIGHT
        # Opaque mode is an ordinary window, complete with a title bar to drag.
        pygame.display.set_mode((self._width, self._height), OPENGL | DOUBLEBUF)
        pygame.display.set_caption("Pocket Pikita")

        self._hwnd = pygame.display.get_wm_info()["window"]
        self._gl_hwnd = self._hwnd
        self._configure_win32()
        self._always_on_top = bool(settings.get("always_on_top", True))
        self._desktop_transparent = False
        self._overlay_hwnd = None
        self._overlay_class_name = None
        self._native_events: list[tuple[str, object]] = []
        self._window_proc = None  # Keep the ctypes callback alive for Windows.
        self._layered_dc = None
        self._layered_bitmap = None
        self._layered_previous = None
        self._layered_bits = None
        position = settings.get("position")
        if isinstance(position, list) and len(position) == 2:
            self._user.SetWindowPos(
                self._hwnd, 0, int(position[0]), int(position[1]), 0, 0, 0x1 | 0x4
            )
        self._set_topmost(self._always_on_top)

        self._textures: dict[str, int] = {}
        self._surfaces: dict[str, pygame.Surface] = {}
        for png in pngs:
            surface = pygame.image.load(str(png)).convert_alpha()
            surface = pygame.transform.smoothscale(surface, (self._width, self._height))
            key = _normalize(png.name)
            self._surfaces[key] = surface
            self._textures[key] = self._make_texture(surface)

        self._setup_gl()
        self._clock = pygame.time.Clock()
        self._left_origin: tuple[int, int] | None = None
        self._left_max_move = 0.0
        self._squish_x = 0.0
        self._squish_y = 0.0
        self._right_drag: tuple[int, int, int, int] | None = None
        self._roam_remaining = random.uniform(12.0, 24.0)
        self._roam_velocity = 0.0
        self._last_roam_time = time.monotonic()

        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            base_squeak = pygame.mixer.Sound(str(assets_dir / "Squeak.ogg"))
            self._poke_sounds = [
                base_squeak,
                self._retime_sound(base_squeak, 0.84),
                self._retime_sound(base_squeak, 1.18),
            ]
            self._held_squeak = self._pad_sound(base_squeak, 0.45)
            self._held_channel: pygame.mixer.Channel | None = None
        except pygame.error:
            self._poke_sounds = []
            self._held_squeak = None
            self._held_channel = None

        if settings.get("desktop_transparent", False):
            self._set_desktop_transparency(True)

    def _configure_win32(self) -> None:
        self._user = ctypes.windll.user32
        self._gdi = ctypes.windll.gdi32
        self._kernel = ctypes.windll.kernel32
        self._user.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        self._user.GetWindowLongW.restype = ctypes.c_long
        self._user.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        self._user.SetWindowLongW.restype = ctypes.c_long
        self._user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [
            ctypes.c_int
        ] * 4 + [ctypes.c_uint]
        self._user.GetCursorPos.argtypes = [ctypes.POINTER(_Point)]
        self._user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_Rect)]
        self._user.CreateWindowExW.argtypes = [
            ctypes.c_uint, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_uint,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p,
        ]
        self._user.CreateWindowExW.restype = wintypes.HWND
        self._user.UpdateLayeredWindow.argtypes = [
            wintypes.HWND, wintypes.HDC, ctypes.POINTER(_Point), ctypes.POINTER(_Size),
            wintypes.HDC, ctypes.POINTER(_Point), ctypes.c_uint,
            ctypes.POINTER(_BlendFunction), ctypes.c_uint,
        ]
        self._user.UpdateLayeredWindow.restype = wintypes.BOOL
        self._user.PeekMessageW.argtypes = [
            ctypes.POINTER(_Msg), wintypes.HWND, ctypes.c_uint, ctypes.c_uint, ctypes.c_uint
        ]
        self._user.RegisterClassW.argtypes = [ctypes.POINTER(_WindowClass)]
        self._user.DefWindowProcW.argtypes = [
            wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM
        ]
        self._user.DefWindowProcW.restype = ctypes.c_ssize_t
        self._kernel.GetModuleHandleW.restype = wintypes.HMODULE
        self._user.GetDC.argtypes = [wintypes.HWND]
        self._user.GetDC.restype = wintypes.HDC
        self._user.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        self._gdi.CreateCompatibleDC.argtypes = [wintypes.HDC]
        self._gdi.CreateCompatibleDC.restype = wintypes.HDC
        self._gdi.CreateDIBSection.argtypes = [
            wintypes.HDC, ctypes.POINTER(_BitmapInfo), ctypes.c_uint,
            ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, ctypes.c_uint,
        ]
        self._gdi.CreateDIBSection.restype = wintypes.HBITMAP
        self._gdi.SelectObject.argtypes = [wintypes.HDC, wintypes.HANDLE]
        self._gdi.SelectObject.restype = wintypes.HANDLE
        self._gdi.DeleteObject.argtypes = [wintypes.HANDLE]
        self._gdi.DeleteDC.argtypes = [wintypes.HDC]

    def _load_settings(self) -> dict:
        try:
            return json.loads(self._settings_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def _save_settings(self) -> None:
        window = _Rect()
        self._user.GetWindowRect(self._hwnd, ctypes.byref(window))
        settings = {
            "position": [window.left, window.top],
            "desktop_transparent": self._desktop_transparent,
            "always_on_top": self._always_on_top,
        }
        self._settings_path.write_text(
            json.dumps(settings, indent=2) + "\n", encoding="utf-8"
        )

    def _setup_gl(self) -> None:
        glViewport(0, 0, self._width, self._height)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, self._width, self._height, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glEnable(GL_TEXTURE_2D)
        glEnable(GL_BLEND)
        # Keep RGB visible locally while preserving alpha for OBS.
        glBlendFuncSeparate(
            GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA
        )

    @staticmethod
    def _make_texture(surface: pygame.Surface) -> int:
        texture = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        data = pygame.image.tostring(surface, "RGBA", False)
        glTexImage2D(
            GL_TEXTURE_2D,
            0,
            GL_RGBA,
            surface.get_width(),
            surface.get_height(),
            0,
            GL_RGBA,
            GL_UNSIGNED_BYTE,
            data,
        )
        return texture

    @staticmethod
    def _retime_sound(sound: pygame.mixer.Sound, speed: float) -> pygame.mixer.Sound:
        """Make a related pitch/tempo variant without adding outside audio."""
        channels = pygame.mixer.get_init()[2]
        samples = array("h")
        samples.frombytes(sound.get_raw())
        frame_count = len(samples) // channels
        output = array("h")
        for frame in range(max(1, round(frame_count / speed))):
            source = min(frame_count - 1, int(frame * speed))
            output.extend(samples[source * channels : (source + 1) * channels])
        return pygame.mixer.Sound(buffer=output.tobytes())

    @staticmethod
    def _pad_sound(sound: pygame.mixer.Sound, silence_seconds: float) -> pygame.mixer.Sound:
        """A squeak with breathing room makes a held loop feel deliberate."""
        frequency, _, channels = pygame.mixer.get_init()
        silence = b"\x00" * (round(frequency * silence_seconds) * channels * 2)
        return pygame.mixer.Sound(buffer=sound.get_raw() + silence)

    def _sprite_key_for(self, intent: PetIntent) -> str:
        expression = intent.expression.value
        candidates = []
        if intent.blinking and intent.talking:
            candidates.append(f"{expression}+Blink+Speak")
        if intent.blinking:
            candidates.append(f"{expression}+Blink")
        if intent.talking:
            candidates.append(f"{expression}+Speak")
        candidates.append(expression)
        for candidate in candidates:
            key = _normalize(candidate)
            if key in self._textures:
                return key
        return _normalize("Base")

    def _texture_for(self, intent: PetIntent) -> int:
        return self._textures[self._sprite_key_for(intent)]

    def _surface_for(self, intent: PetIntent) -> pygame.Surface:
        return self._surfaces[self._sprite_key_for(intent)]

    def _set_desktop_transparency(self, enable: bool) -> None:
        """Swap the framed GL window for a true-alpha native overlay."""
        if enable == self._desktop_transparent:
            return
        if enable:
            window = _Rect()
            self._user.GetWindowRect(self._gl_hwnd, ctypes.byref(window))
            self._create_overlay_window(window.left, window.top)
            self._hwnd = self._overlay_hwnd
            self._set_topmost(self._always_on_top)
            self._user.ShowWindow(self._gl_hwnd, 0)  # SW_HIDE
        else:
            self._destroy_overlay_window()
            self._hwnd = self._gl_hwnd
            self._user.ShowWindow(self._gl_hwnd, 4)  # SW_SHOWNOACTIVATE
        self._desktop_transparent = enable

    def _create_overlay_window(self, x: int, y: int) -> None:
        if self._overlay_class_name is None:
            callback_type = ctypes.WINFUNCTYPE(
                ctypes.c_ssize_t, wintypes.HWND, ctypes.c_uint, wintypes.WPARAM, wintypes.LPARAM
            )
            self._window_proc = callback_type(self._native_window_proc)
            self._overlay_class_name = f"PocketPikitaOverlay{ id(self) }"
            window_class = _WindowClass()
            window_class.window_proc = ctypes.cast(self._window_proc, ctypes.c_void_p).value
            window_class.instance = self._kernel.GetModuleHandleW(None)
            window_class.class_name = self._overlay_class_name
            if not self._user.RegisterClassW(ctypes.byref(window_class)):
                raise OSError(f"Could not register transparent window: {ctypes.get_last_error()}")

        overlay = self._user.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOOLWINDOW,
            self._overlay_class_name,
            "",
            WS_POPUP,
            x,
            y,
            self._width,
            self._height,
            None,
            None,
            self._kernel.GetModuleHandleW(None),
            None,
        )
        if not overlay:
            raise OSError(f"Could not create transparent window: {ctypes.get_last_error()}")
        self._overlay_hwnd = overlay
        self._create_layered_buffer()
        self._user.ShowWindow(overlay, 4)  # SW_SHOWNOACTIVATE

    def _destroy_overlay_window(self) -> None:
        self._destroy_layered_buffer()
        if self._overlay_hwnd:
            self._user.DestroyWindow(self._overlay_hwnd)
        self._overlay_hwnd = None

    def _create_layered_buffer(self) -> None:
        screen_dc = self._user.GetDC(None)
        self._layered_dc = self._gdi.CreateCompatibleDC(screen_dc)
        bits = ctypes.c_void_p()
        info = _BitmapInfo()
        info.header.size = ctypes.sizeof(_BitmapInfoHeader)
        info.header.width = self._width
        info.header.height = -self._height  # Top-down: pygame rows copy directly.
        info.header.planes = 1
        info.header.bit_count = 32
        self._layered_bitmap = self._gdi.CreateDIBSection(
            self._layered_dc, ctypes.byref(info), 0, ctypes.byref(bits), None, 0
        )
        if not self._layered_dc or not self._layered_bitmap or not bits.value:
            raise OSError("Could not allocate transparent-window surface.")
        self._layered_previous = self._gdi.SelectObject(self._layered_dc, self._layered_bitmap)
        self._layered_bits = bits
        self._user.ReleaseDC(None, screen_dc)

    def _destroy_layered_buffer(self) -> None:
        if self._layered_dc and self._layered_previous:
            self._gdi.SelectObject(self._layered_dc, self._layered_previous)
        if self._layered_bitmap:
            self._gdi.DeleteObject(self._layered_bitmap)
        if self._layered_dc:
            self._gdi.DeleteDC(self._layered_dc)
        self._layered_dc = self._layered_bitmap = self._layered_previous = self._layered_bits = None

    def _render_layered(self, intent: PetIntent) -> None:
        sprite = self._surface_for(intent)
        width_scale = 1.0 - 0.62 * intent.squish_x + 0.12 * intent.squish_y
        height_scale = 1.0 - 0.62 * intent.squish_y + 0.12 * intent.squish_x
        width, height = round(self._width * width_scale), round(self._height * height_scale)
        sprite = pygame.transform.smoothscale(sprite, (width, height))
        frame = pygame.Surface((self._width, self._height), pygame.SRCALPHA, 32)
        sway, bob = _walk_offset(bool(self._roam_velocity), time.monotonic())
        frame.blit(sprite, (
            round((self._width - width) / 2 + sway),
            round((self._height - height) / 2 + bob),
        ))
        pixels = pygame.image.tostring(frame.premul_alpha(), "BGRA", False)
        ctypes.memmove(self._layered_bits, pixels, len(pixels))

        window = _Rect()
        self._user.GetWindowRect(self._hwnd, ctypes.byref(window))
        screen_dc = self._user.GetDC(None)
        try:
            updated = self._user.UpdateLayeredWindow(
                self._hwnd, screen_dc, ctypes.byref(_Point(window.left, window.top)),
                ctypes.byref(_Size(self._width, self._height)), self._layered_dc,
                ctypes.byref(_Point(0, 0)), 0,
                ctypes.byref(_BlendFunction(0, 0, 255, AC_SRC_ALPHA)), ULW_ALPHA,
            )
            if not updated:
                raise OSError(f"Could not paint transparent window: {ctypes.get_last_error()}")
        finally:
            self._user.ReleaseDC(None, screen_dc)

    def _native_window_proc(self, hwnd, message, w_param, l_param):
        """Record overlay input; pygame continues to handle the framed window."""
        if message == WM_KEYDOWN:
            self._native_events.append(("key", int(w_param)))
        elif message in (WM_LBUTTONDOWN, WM_RBUTTONDOWN, WM_MOUSEMOVE, WM_LBUTTONUP, WM_RBUTTONUP):
            x = ctypes.c_short(l_param & 0xFFFF).value
            y = ctypes.c_short((l_param >> 16) & 0xFFFF).value
            names = {
                WM_LBUTTONDOWN: "left_down", WM_LBUTTONUP: "left_up",
                WM_RBUTTONDOWN: "right_down", WM_RBUTTONUP: "right_up",
                WM_MOUSEMOVE: "move",
            }
            self._native_events.append((names[message], (x, y)))
            if message in (WM_LBUTTONDOWN, WM_RBUTTONDOWN):
                self._user.SetCapture(hwnd)
            elif message in (WM_LBUTTONUP, WM_RBUTTONUP):
                self._user.ReleaseCapture()
        return self._user.DefWindowProcW(hwnd, message, w_param, l_param)

    def _pump_overlay_messages(self) -> None:
        if not self._overlay_hwnd:
            return
        message = _Msg()
        while self._user.PeekMessageW(
            ctypes.byref(message), self._overlay_hwnd, 0, 0, PM_REMOVE
        ):
            self._user.TranslateMessage(ctypes.byref(message))
            self._user.DispatchMessageW(ctypes.byref(message))

    def _handle_key(self, key: int) -> bool:
        if key in (pygame.K_ESCAPE, 0x1B):
            return True
        if key in (pygame.K_t, 0x54):
            self._set_desktop_transparency(not self._desktop_transparent)
        elif key in (pygame.K_a, 0x41):
            self._set_topmost(not self._always_on_top)
        elif key in (pygame.K_m, 0x4D):
            # M is a nudge: make him take a little walk right now.
            self._roam_velocity = random.choice((-1.0, 1.0)) * random.uniform(18.0, 32.0)
            self._roam_remaining = random.uniform(2.0, 4.5)
        return False

    def _handle_mouse_down(self, button: int, position: tuple[int, int]) -> None:
        if button == 1:
            self._left_origin = position
            self._left_max_move = 0.0
        elif button == 3:
            self._begin_window_drag()

    def _handle_mouse_up(self, button: int) -> bool:
        if button == 1 and self._left_origin is not None:
            poked = self._left_max_move < DRAG_THRESHOLD
            self._left_origin = None
            self._squish_x = self._squish_y = 0.0
            return poked
        if button == 3:
            self._right_drag = None
        return False

    def _set_topmost(self, enable: bool) -> None:
        hwnd_position = -1 if enable else -2  # HWND_TOPMOST / HWND_NOTOPMOST
        self._user.SetWindowPos(self._hwnd, hwnd_position, 0, 0, 0, 0, 0x1 | 0x2)
        self._always_on_top = enable

    def _begin_window_drag(self) -> None:
        cursor = _Point()
        window = _Rect()
        self._user.GetCursorPos(ctypes.byref(cursor))
        self._user.GetWindowRect(self._hwnd, ctypes.byref(window))
        self._right_drag = (cursor.x, cursor.y, window.left, window.top)

    def _move_window(self) -> None:
        if self._right_drag is None:
            return
        cursor = _Point()
        self._user.GetCursorPos(ctypes.byref(cursor))
        start_x, start_y, window_x, window_y = self._right_drag
        self._user.SetWindowPos(
            self._hwnd,
            0,
            window_x + cursor.x - start_x,
            window_y + cursor.y - start_y,
            0,
            0,
            0x1 | 0x4,
        )

    def _wander(self) -> None:
        """Occasionally take a small horizontal walk, then settle again."""
        now = time.monotonic()
        dt = min(now - self._last_roam_time, 0.1)
        self._last_roam_time = now
        if self._right_drag is not None or self._left_origin is not None:
            return

        self._roam_remaining -= dt
        if self._roam_remaining <= 0.0:
            if self._roam_velocity:
                # Rest long enough that Pikita feels alive, not restless.
                self._roam_velocity = 0.0
                self._roam_remaining = random.uniform(14.0, 30.0)
            else:
                self._roam_velocity = random.choice((-1.0, 1.0)) * random.uniform(18.0, 32.0)
                self._roam_remaining = random.uniform(2.0, 4.5)

        if not self._roam_velocity:
            return

        window = _Rect()
        self._user.GetWindowRect(self._hwnd, ctypes.byref(window))
        next_x = round(window.left + self._roam_velocity * dt)
        # Keep him on the virtual desktop, even on a multi-monitor setup.
        left = self._user.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
        width = self._user.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
        next_x = max(left, min(left + width - self._width, next_x))
        if next_x in (left, left + width - self._width):
            self._roam_velocity *= -1
        self._user.SetWindowPos(self._hwnd, 0, next_x, window.top, 0, 0, 0x1 | 0x4)

    def _update_squish(self, position: tuple[int, int]) -> None:
        if self._left_origin is None:
            return
        start_x, start_y = self._left_origin
        x, y = position
        dx, dy = x - start_x, y - start_y
        self._left_max_move = max(self._left_max_move, (dx * dx + dy * dy) ** 0.5)

        self._squish_x, self._squish_y = _squish_from_drag(
            self._left_origin, position, (self._width, self._height)
        )

    def pump_events(self) -> FrameInput:
        quit_ = poked = False
        self._pump_overlay_messages()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_ = True
            elif event.type == pygame.KEYDOWN:
                quit_ = self._handle_key(event.key) or quit_
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self._handle_mouse_down(event.button, event.pos)
            elif event.type == pygame.MOUSEMOTION:
                if self._left_origin is not None:
                    self._update_squish(event.pos)
                if self._right_drag is not None:
                    self._move_window()
            elif event.type == pygame.MOUSEBUTTONUP:
                poked = self._handle_mouse_up(event.button) or poked

        for kind, payload in self._native_events:
            if kind == "key":
                quit_ = self._handle_key(payload) or quit_
            elif kind == "left_down":
                self._handle_mouse_down(1, payload)
            elif kind == "right_down":
                self._handle_mouse_down(3, payload)
            elif kind == "move":
                if self._left_origin is not None:
                    self._update_squish(payload)
                if self._right_drag is not None:
                    self._move_window()
            elif kind == "left_up":
                poked = self._handle_mouse_up(1) or poked
            elif kind == "right_up":
                self._handle_mouse_up(3)
        self._native_events.clear()

        return FrameInput(
            quit=quit_,
            poked=poked,
            squish_x=self._squish_x,
            squish_y=self._squish_y,
        )

    def render(self, intent: PetIntent) -> None:
        self._wander()
        if intent.sound is Sound.SQUEAK and self._poke_sounds:
            random.choice(self._poke_sounds).play()

        if intent.squishing:
            if self._held_squeak is not None and (
                self._held_channel is None or not self._held_channel.get_busy()
            ):
                self._held_channel = self._held_squeak.play(loops=-1)
        elif self._held_channel is not None:
            self._held_channel.fadeout(100)
            self._held_channel = None

        if self._desktop_transparent:
            self._render_layered(intent)
            self._clock.tick(FPS)
            return

        glClearColor(*BACKGROUND, 0.0)
        glClear(GL_COLOR_BUFFER_BIT)
        glBindTexture(GL_TEXTURE_2D, self._texture_for(intent))

        width_scale = 1.0 - 0.62 * intent.squish_x + 0.12 * intent.squish_y
        height_scale = 1.0 - 0.62 * intent.squish_y + 0.12 * intent.squish_x
        width = self._width * width_scale
        height = self._height * height_scale
        sway, bob = _walk_offset(bool(self._roam_velocity), time.monotonic())
        left = (self._width - width) / 2 + sway
        top = (self._height - height) / 2 + bob
        right, bottom = left + width, top + height

        glBegin(GL_QUADS)
        glTexCoord2f(0, 0)
        glVertex2f(left, top)
        glTexCoord2f(1, 0)
        glVertex2f(right, top)
        glTexCoord2f(1, 1)
        glVertex2f(right, bottom)
        glTexCoord2f(0, 1)
        glVertex2f(left, bottom)
        glEnd()

        pygame.display.flip()
        self._clock.tick(FPS)

    def shutdown(self) -> None:
        self._save_settings()
        if self._held_channel is not None:
            self._held_channel.stop()
        if self._desktop_transparent:
            self._set_desktop_transparency(False)
        glDeleteTextures(list(self._textures.values()))
        pygame.quit()
