"""OpenGL desktop renderer with an alpha channel OBS can preserve."""

import ctypes
import json
from ctypes import wintypes
from dataclasses import replace
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
    GL_NEAREST,
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
from desktop_icons import DesktopIcon, DesktopIcons
from pet.intent import Expression, PetIntent, Sound
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
CURSOR_NOTICE_DISTANCE = 520
SCREEN_EDGE_DISTANCE = 36
JUMP_DURATION = 0.6
DRAG_REST_ANGLE = 0.15
DRAG_REST_SPEED = 0.5


def _normalize(name: str) -> str:
    return name.removesuffix(".png").replace(" ", "").lower()


def _clean_transparent_edge(surface: pygame.Surface) -> pygame.Surface:
    """Replace white RGB hidden in translucent silhouette pixels with black."""
    pixels = bytearray(pygame.image.tostring(surface, "RGBA", False))
    for offset in range(0, len(pixels), 4):
        alpha = pixels[offset + 3]
        if alpha < 255:
            pixels[offset : offset + 3] = b"\x00\x00\x00"
    return pygame.image.frombuffer(bytes(pixels), surface.get_size(), "RGBA").copy()


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


def _walk_offset(walking: bool, seconds: float, strength: float = 1.0) -> tuple[float, float]:
    """A small gait that gives a static sprite a sense of weight and motion."""
    if not walking:
        return 0.0, 0.0
    step = math.sin(seconds * 11.0)
    return step * 9.0 * strength, -abs(step) * 11.0 * strength


def _walk_speed_scale(seconds: float) -> float:
    """Match forward motion to the gait so he moves in visible little steps."""
    return 0.45 + 0.55 * abs(math.sin(seconds * 11.0))


def _grab_angle(grab: tuple[int, int], size: tuple[int, int], velocity_x: float) -> float:
    """Combine pendulum swing with the orientation implied by the grab point."""
    x, y = grab
    width, height = size
    depth = max(0.0, min(1.0, (y / max(height, 1) - 0.62) / 0.28))
    inversion = (180.0 if x < width / 2 else -180.0) * depth
    # The body trails the grabbed point, so horizontal motion produces opposite torque.
    swing = max(-38.0, min(38.0, -velocity_x * 0.075)) * (1.0 - depth)
    return inversion + swing


def _rotated_quad(
    left: float, top: float, width: float, height: float, angle: float
) -> list[tuple[float, float]]:
    """Return clockwise screen-space corners rotated around the sprite center."""
    center_x, center_y = left + width / 2, top + height / 2
    radians = math.radians(angle)
    cosine, sine = math.cos(radians), math.sin(radians)
    corners = []
    for x, y in ((left, top), (left + width, top), (left + width, top + height), (left, top + height)):
        dx, dy = x - center_x, y - center_y
        corners.append((center_x + dx * cosine - dy * sine, center_y + dx * sine + dy * cosine))
    return corners


def _rotated_bounds(width: float, height: float, angle: float) -> tuple[float, float]:
    """Return the canvas dimensions needed by a rotated rectangle."""
    radians = math.radians(angle)
    bounds_width = abs(width * math.cos(radians)) + abs(height * math.sin(radians))
    bounds_height = abs(width * math.sin(radians)) + abs(height * math.cos(radians))
    return bounds_width, bounds_height


def _rotate_screen_point(
    point: tuple[float, float], center: tuple[float, float], angle: float
) -> tuple[float, float]:
    """Rotate a screen-space point with the same angle convention as pygame."""
    radians = math.radians(angle)
    cosine, sine = math.cos(radians), math.sin(radians)
    dx, dy = point[0] - center[0], point[1] - center[1]
    return (
        center[0] + dx * cosine + dy * sine,
        center[1] - dx * sine + dy * cosine,
    )


def _sprite_ratio_at_point(
    point: tuple[float, float],
    sprite_rect: tuple[float, float, float, float],
    angle: float,
) -> tuple[float, float]:
    """Map a click on the rotated sprite back to its unrotated proportions."""
    left, top, width, height = sprite_rect
    center = (left + width / 2, top + height / 2)
    x, y = _rotate_screen_point(point, center, -angle)
    return (
        max(0.0, min(1.0, (x - left) / max(width, 1))),
        max(0.0, min(1.0, (y - top) / max(height, 1))),
    )


def _point_at_sprite_ratio(
    ratio: tuple[float, float],
    sprite_rect: tuple[float, float, float, float],
    angle: float,
) -> tuple[float, float]:
    """Return where a normalized sprite point appears after rotation."""
    left, top, width, height = sprite_rect
    center = (left + width / 2, top + height / 2)
    point = (left + ratio[0] * width, top + ratio[1] * height)
    return _rotate_screen_point(point, center, angle)


def _grounded_canvas_origin(
    sprite_center_x: float, sprite_bottom: float, canvas_width: int, canvas_height: int
) -> tuple[int, int]:
    """Place a replacement canvas without moving Pikita's feet or center line."""
    return round(sprite_center_x - canvas_width / 2), round(sprite_bottom - canvas_height)


def _perspective_scale(sprite_top: int, monitor_top: int, monitor_bottom: int) -> float:
    """Map Pikita's visible top to depth, with his original size at screen center."""
    midpoint = (monitor_top + monitor_bottom) / 2
    half_height = max((monitor_bottom - monitor_top) / 2, 1)
    depth = max(-1.0, min(1.0, (sprite_top - midpoint) / half_height))
    # Background is exactly half-size; foreground becomes visually dominant.
    return 1.0 + (0.50 if depth < 0 else 0.55) * depth


def _jump_motion(progress: float) -> tuple[float, float, float, float]:
    """Return a small airborne arc and stretch for a monitor-to-monitor leap."""
    arc = math.sin(math.pi * max(0.0, min(1.0, progress)))
    return 0.0, -72.0 * arc, 1.0 - 0.12 * arc, 1.0 + 0.10 * arc


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


_MonitorEnumProc = ctypes.WINFUNCTYPE(
    wintypes.BOOL, wintypes.HANDLE, wintypes.HDC, ctypes.POINTER(_Rect), wintypes.LPARAM
)


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
        self._overlay_width = self._width
        self._overlay_height = self._height
        self._overlay_sprite_width = self._width
        self._overlay_sprite_height = self._height
        position = settings.get("position")
        if isinstance(position, list) and len(position) == 2:
            self._user.SetWindowPos(
                self._hwnd, 0, int(position[0]), int(position[1]), 0, 0, 0x1 | 0x4
            )
        self._set_topmost(self._always_on_top)

        self._textures: dict[str, int] = {}
        self._surfaces: dict[str, pygame.Surface] = {}
        for png in pngs:
            surface = _clean_transparent_edge(
                pygame.image.load(str(png)).convert_alpha()
            )
            key = _normalize(png.name)
            self._surfaces[key] = surface
            # Keep the original for the layered window. Enlarging an already
            # resized surface is what produced the faint vertical striping.
            texture_surface = pygame.transform.smoothscale(
                surface, (self._width, self._height)
            )
            self._textures[key] = self._make_texture(texture_surface)

        self._setup_gl()
        self._clock = pygame.time.Clock()
        self._left_origin: tuple[int, int] | None = None
        self._left_max_move = 0.0
        self._left_drag: tuple[int, int, int, int] | None = None
        self._left_grab = (self._width // 2, self._height // 3)
        self._left_grab_ratio = (0.5, 1 / 3)
        self._drag_cursor: tuple[int, int] | None = None
        self._drag_release_pending = False
        self._last_sprite_rect = (0.0, 0.0, float(self._width), float(self._height))
        self._drag_last_cursor: tuple[int, int] | None = None
        self._drag_last_time = time.monotonic()
        self._drag_release_pause_until = self._drag_last_time
        self._drag_velocity_x = 0.0
        self._drag_angle = 0.0
        self._drag_target_angle = 0.0
        self._drag_angular_velocity = 0.0
        self._drag_physics_time = self._drag_last_time
        self._right_origin: tuple[int, int] | None = None
        self._squish_x = 0.0
        self._squish_y = 0.0
        self._roam_remaining = random.uniform(12.0, 24.0)
        self._roam_velocity = (0.0, 0.0)
        self._walk_kind = "idle"
        self._last_roam_time = time.monotonic()
        self._walk_started = self._last_roam_time
        self._walk_duration = 0.0
        self._cursor_next_check = self._last_roam_time
        self._cursor_pause_until = self._last_roam_time
        self._inspect_until = 0.0
        self._inspection_squeaked = False
        self._attention_until = 0.0
        self._attention_expression = Expression.BASE
        self._jump_target: tuple[int, int] | None = None
        self._jump_origin: tuple[int, int] | None = None
        self._jump_started = 0.0
        self._peek_target: tuple[int, int] | None = None
        self._peek_started = 0.0
        self._monitors: list[_Rect] = []
        self._next_monitor_refresh = 0.0
        self._desktop_icons = DesktopIcons()
        self._next_icon_try = self._last_roam_time + random.uniform(20.0, 35.0)
        self._eating_icon: DesktopIcon | None = None
        self._snack_target: DesktopIcon | None = None
        self._eating_started = 0.0
        self._eating_sounded = False

        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            squeak_paths = [assets_dir / "Squeak.ogg", *sorted(assets_dir.glob("Squeak_*.mp3"))]
            # These are distinct recordings, not pitch-shifted copies of one file.
            self._poke_sounds = [pygame.mixer.Sound(str(path)) for path in squeak_paths]
            self._held_squeaks = [self._pad_sound(sound, 0.45) for sound in self._poke_sounds]
            self._held_channel: pygame.mixer.Channel | None = None
        except pygame.error:
            self._poke_sounds = []
            self._held_squeaks = []
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
        # user32 is shared across modules; accept any compatible POINT struct.
        self._user.ClientToScreen.argtypes = [wintypes.HWND, ctypes.c_void_p]
        self._user.ClientToScreen.restype = wintypes.BOOL
        self._user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_Rect)]
        self._user.EnumDisplayMonitors.argtypes = [
            wintypes.HDC, ctypes.POINTER(_Rect), _MonitorEnumProc, wintypes.LPARAM
        ]
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
        # Textures are premultiplied before upload, preventing transparent white
        # edge pixels from forming a halo against the framed window's background.
        glBlendFuncSeparate(
            GL_ONE, GL_ONE_MINUS_SRC_ALPHA, GL_ONE, GL_ONE_MINUS_SRC_ALPHA
        )

    @staticmethod
    def _make_texture(surface: pygame.Surface) -> int:
        texture = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture)
        # Linear sampling leaves vertical bands in the flat white areas of the
        # temporary raster sprite. Nearest keeps the line art clean at this size.
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        data = pygame.image.tostring(surface.premul_alpha(), "RGBA", False)
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
            # The framed view is a stable preview/OBS window, not pet mode.
            self._roam_velocity = (0.0, 0.0)
            self._walk_kind = "idle"
            self._jump_target = self._jump_origin = self._peek_target = None
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
        self._overlay_width, self._overlay_height = self._width, self._height
        self._overlay_sprite_width, self._overlay_sprite_height = self._width, self._height
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
        info.header.width = self._overlay_width
        info.header.height = -self._overlay_height  # Top-down: pygame rows copy directly.
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

    def _update_overlay_scale(self, intent: PetIntent) -> None:
        """Resize the alpha canvas from Pikita's visible top as he changes depth."""
        window = _Rect()
        self._user.GetWindowRect(self._hwnd, ctypes.byref(window))
        # Layered sprites sit on the canvas floor; using centered padding here
        # made a rotating canvas look as though Pikita had jumped upward.
        sprite_top = window.top + self._overlay_height - self._overlay_sprite_height
        sprite_rect = _Rect(
            round(window.left + (self._overlay_width - self._overlay_sprite_width) / 2),
            round(sprite_top),
            round(window.left + (self._overlay_width + self._overlay_sprite_width) / 2),
            round(sprite_top + self._overlay_sprite_height),
        )
        monitor = self._monitor_for_sprite_top(sprite_rect, self._monitor_rects())
        if monitor is None:
            return
        scale = _perspective_scale(round(sprite_top), monitor.top, monitor.bottom)
        sprite_width = round(self._width * scale)
        sprite_height = round(self._height * scale)
        rotating = (
            self._left_drag is not None
            or abs(self._drag_angle) >= DRAG_REST_ANGLE
            or abs(self._drag_angular_velocity) >= DRAG_REST_SPEED
        )
        if rotating:
            # Allocate once for the whole gesture. Rebuilding the native DIB at
            # every angle was the source of the visible drag jitter.
            maximum_scale = 1.55
            diameter = math.ceil(
                math.hypot(self._width * maximum_scale, self._height * maximum_scale)
            )
            width = height = diameter
        else:
            width, height = sprite_width, sprite_height
        canvas_changed = width != self._overlay_width or height != self._overlay_height
        sprite_changed = (
            sprite_width != self._overlay_sprite_width
            or sprite_height != self._overlay_sprite_height
        )
        if not canvas_changed and not sprite_changed:
            return
        self._overlay_sprite_width, self._overlay_sprite_height = sprite_width, sprite_height
        if not canvas_changed:
            return
        sprite_center_x = (window.left + window.right) / 2
        sprite_bottom = window.top + self._overlay_height
        self._destroy_layered_buffer()
        self._overlay_width, self._overlay_height = width, height
        x, y = _grounded_canvas_origin(sprite_center_x, sprite_bottom, width, height)
        if self._left_drag is not None and self._drag_cursor is not None:
            # A new rotation canvas is positioned from the grab itself. This
            # avoids a one-frame visit to its expanded top-left corner.
            sprite_rect = (
                (width - sprite_width) / 2,
                height - sprite_height,
                sprite_width,
                sprite_height,
            )
            grabbed = _point_at_sprite_ratio(
                self._left_grab_ratio, sprite_rect, self._drag_angle
            )
            x = round(self._drag_cursor[0] - grabbed[0])
            y = round(self._drag_cursor[1] - grabbed[1])
        self._user.SetWindowPos(
            self._hwnd,
            0,
            x,
            y,
            width,
            height,
            0x4,
        )
        self._create_layered_buffer()

    def _sprite_layout(self, intent: PetIntent) -> tuple[float, float, float, float]:
        """Place the sprite on a shared ground line for normal and alpha rendering."""
        window = _Rect()
        self._user.GetWindowRect(self._hwnd, ctypes.byref(window))
        monitor = self._monitor_for_sprite_top(window, self._monitor_rects())
        canvas_width = self._overlay_width if self._desktop_transparent else self._width
        canvas_height = self._overlay_height if self._desktop_transparent else self._height
        sprite_width = self._overlay_sprite_width if self._desktop_transparent else self._width
        sprite_height = self._overlay_sprite_height if self._desktop_transparent else self._height
        # The overlay canvas owns depth. The framed preview is always fixed-size.
        perspective = 1.0
        width_scale = (1.0 - 0.62 * intent.squish_x + 0.12 * intent.squish_y) * perspective
        height_scale = (1.0 - 0.62 * intent.squish_y + 0.12 * intent.squish_x) * perspective
        if self._is_jumping():
            sway, bob, jump_width, jump_height = _jump_motion(self._jump_progress())
            width_scale *= jump_width
            height_scale *= jump_height
        elif self._is_peeking():
            sway, bob = (14.0 if self._roam_velocity[0] >= 0 else -14.0), 0.0
        elif self._is_inspecting():
            sway, bob = 8.0, -3.0
        else:
            sway, bob = _walk_offset(
                self._is_walking(), time.monotonic(), self._walk_strength()
            )
        width = sprite_width * width_scale
        height = sprite_height * height_scale
        return (canvas_width - width) / 2 + sway, canvas_height - height + bob, width, height

    def _render_layered(self, intent: PetIntent) -> None:
        sprite = self._surface_for(intent)
        left, top, width, height = self._sprite_layout(intent)
        self._last_sprite_rect = (left, top, width, height)
        width, height = round(width), round(height)
        sprite = pygame.transform.smoothscale(sprite, (width, height))
        frame = pygame.Surface((self._overlay_width, self._overlay_height), pygame.SRCALPHA, 32)
        if abs(self._drag_angle) > 0.1:
            sprite = pygame.transform.rotozoom(sprite, self._drag_angle, 1.0)
            center = (round(left + width / 2), round(top + height / 2))
            frame.blit(sprite, sprite.get_rect(center=center))
        else:
            frame.blit(sprite, (round(left), round(top)))
        self._draw_eating_icon(frame, left, top, width, height)
        pixels = pygame.image.tostring(frame.premul_alpha(), "BGRA", False)
        ctypes.memmove(self._layered_bits, pixels, len(pixels))

        window = _Rect()
        self._user.GetWindowRect(self._hwnd, ctypes.byref(window))
        screen_dc = self._user.GetDC(None)
        try:
            updated = self._user.UpdateLayeredWindow(
                self._hwnd, screen_dc, ctypes.byref(_Point(window.left, window.top)),
                ctypes.byref(_Size(self._overlay_width, self._overlay_height)), self._layered_dc,
                ctypes.byref(_Point(0, 0)), 0,
                ctypes.byref(_BlendFunction(0, 0, 255, AC_SRC_ALPHA)), ULW_ALPHA,
            )
            if not updated:
                raise OSError(f"Could not paint transparent window: {ctypes.get_last_error()}")
        finally:
            self._user.ReleaseDC(None, screen_dc)

    def _draw_eating_icon(
        self, frame: pygame.Surface, sprite_left: float, sprite_top: float, sprite_width: int, sprite_height: int
    ) -> None:
        """Lift the captured desktop icon to Pikita's mouth, then shrink it away."""
        if self._eating_icon is None:
            return
        progress = min(1.0, (time.monotonic() - self._eating_started) / 2.0)
        mouth_x = sprite_left + sprite_width * 0.51
        mouth_y = sprite_top + sprite_height * 0.57
        # Keep a real desktop icon readable at his mouth before he swallows it.
        size = max(4, round(88 * (1.0 - max(0.0, progress - 0.68) / 0.32)))
        icon = pygame.transform.smoothscale(self._eating_icon.image, (size, size))
        # smoothscale drops a source colorkey, which otherwise resurrects the
        # captured desktop background as an opaque black rectangle.
        icon.set_colorkey(icon.get_at((0, 0)))
        start_x, start_y = sprite_width * 0.86, sprite_height * 0.72
        x = sprite_left + start_x + (mouth_x - (sprite_left + start_x)) * progress - size / 2
        y = sprite_top + start_y + (mouth_y - (sprite_top + start_y)) * progress - size / 2
        frame.blit(icon, (round(x), round(y)))
        if progress >= 1.0:
            self._eating_icon = None

    def _try_eat_desktop_icon(self, now: float, force: bool = False) -> bool:
        if self._eating_icon is not None or self._snack_target is not None or (not force and now < self._next_icon_try):
            return False
        self._next_icon_try = now + random.uniform(35.0, 65.0)
        try:
            window = _Rect()
            self._user.GetWindowRect(self._hwnd, ctypes.byref(window))
            monitor = self._monitor_for_sprite_top(window, self._monitor_rects())
            monitor_bounds = (
                (monitor.left, monitor.top, monitor.right, monitor.bottom)
                if monitor is not None
                else None
            )
            icon = self._desktop_icons.choose_visible(
                ((window.left + window.right) // 2, (window.top + window.bottom) // 2)
                if force else None,
                monitor_bounds,
            )
        except OSError:
            return False
        if icon is None:
            return False
        self._snack_target = icon
        self._walk_kind = "snack"
        self._attention_expression = Expression.HAPPY
        self._attention_until = now + 1.2
        return True

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
            self._begin_walk()
        elif key in (pygame.K_e, 0x45) and self._desktop_transparent:
            # E is deliberately a manual test of the visible-icon behavior.
            self._try_eat_desktop_icon(time.monotonic(), force=True)
        return False

    def _handle_mouse_down(self, button: int, position: tuple[int, int]) -> None:
        if button == 1:
            self._left_origin = position
            self._left_max_move = 0.0
            self._begin_window_drag(position)
            self._attention_expression = Expression.HAPPY
            self._attention_until = time.monotonic() + 0.5
        elif button == 3:
            self._right_origin = position

    def _handle_mouse_up(self, button: int) -> bool:
        if button == 1 and self._left_origin is not None:
            poked = self._left_max_move < DRAG_THRESHOLD
            self._left_origin = None
            self._left_drag = None
            self._drag_cursor = None
            self._drag_release_pending = True
            self._drag_target_angle = 0.0
            return poked
        if button == 3 and self._right_origin is not None:
            self._right_origin = None
            self._squish_x = self._squish_y = 0.0
        return False

    def _set_topmost(self, enable: bool) -> None:
        hwnd_position = -1 if enable else -2  # HWND_TOPMOST / HWND_NOTOPMOST
        self._user.SetWindowPos(self._hwnd, hwnd_position, 0, 0, 0, 0, 0x1 | 0x2)
        self._always_on_top = enable

    def _begin_window_drag(self, position: tuple[int, int]) -> None:
        window = _Rect()
        self._user.GetWindowRect(self._hwnd, ctypes.byref(window))
        cursor_x, cursor_y = self._client_to_screen(position)
        self._left_drag = (cursor_x, cursor_y, window.left, window.top)
        self._left_grab_ratio = _sprite_ratio_at_point(
            position,
            self._last_sprite_rect
            if self._desktop_transparent
            else (0.0, 0.0, float(self._width), float(self._height)),
            self._drag_angle,
        )
        self._drag_cursor = (cursor_x, cursor_y)
        self._drag_last_cursor = (cursor_x, cursor_y)
        now = time.monotonic()
        self._drag_last_time = now
        self._drag_physics_time = now
        self._drag_velocity_x = 0.0
        self._drag_angular_velocity = 0.0
        self._drag_release_pending = False
        self._roam_velocity = (0.0, 0.0)
        self._walk_kind = "idle"
        self._snack_target = None
        self._jump_target = self._jump_origin = self._peek_target = None

    def _client_to_screen(self, position: tuple[int, int]) -> tuple[int, int]:
        point = _Point(round(position[0]), round(position[1]))
        if not self._user.ClientToScreen(self._hwnd, ctypes.byref(point)):
            window = _Rect()
            self._user.GetWindowRect(self._hwnd, ctypes.byref(window))
            return window.left + position[0], window.top + position[1]
        return point.x, point.y

    def _move_window(self, position: tuple[int, int]) -> None:
        if self._left_drag is None:
            return
        current = _Rect()
        self._user.GetWindowRect(self._hwnd, ctypes.byref(current))
        cursor_x, cursor_y = self._client_to_screen(position)
        start_x, start_y, _, _ = self._left_drag
        self._left_max_move = max(
            self._left_max_move,
            math.hypot(cursor_x - start_x, cursor_y - start_y),
        )
        now = time.monotonic()
        previous_cursor = self._drag_last_cursor
        if self._drag_last_cursor is not None:
            elapsed = max(now - self._drag_last_time, 0.001)
            velocity_x = (cursor_x - self._drag_last_cursor[0]) / elapsed
            smoothing = 1.0 - math.exp(-elapsed * 18.0)
            self._drag_velocity_x += (velocity_x - self._drag_velocity_x) * smoothing
        self._drag_last_cursor = (cursor_x, cursor_y)
        self._drag_cursor = (cursor_x, cursor_y)
        self._drag_last_time = now
        if self._desktop_transparent:
            return
        self._user.SetWindowPos(
            self._hwnd,
            0,
            current.left + cursor_x - previous_cursor[0],
            current.top + cursor_y - previous_cursor[1],
            0,
            0,
            0x1 | 0x4,
        )

    def _anchor_dragged_sprite(self, intent: PetIntent) -> None:
        """Keep the exact grabbed point beneath the cursor as Pikita swings."""
        if not self._desktop_transparent or self._left_drag is None or self._drag_cursor is None:
            return
        sprite_rect = self._sprite_layout(intent)
        grabbed = _point_at_sprite_ratio(
            self._left_grab_ratio, sprite_rect, self._drag_angle
        )
        client_origin_x, client_origin_y = self._client_to_screen((0, 0))
        current = _Rect()
        self._user.GetWindowRect(self._hwnd, ctypes.byref(current))
        delta_x = self._drag_cursor[0] - (client_origin_x + grabbed[0])
        delta_y = self._drag_cursor[1] - (client_origin_y + grabbed[1])
        if abs(delta_x) < 0.5 and abs(delta_y) < 0.5:
            return
        self._user.SetWindowPos(
            self._hwnd,
            0,
            round(current.left + delta_x),
            round(current.top + delta_y),
            0,
            0,
            0x1 | 0x4,
        )

    def _wander(self) -> None:
        """Choose among idle wandering, short cursor steps, and screen jumps."""
        now = time.monotonic()
        dt = min(now - self._last_roam_time, 0.1)
        self._last_roam_time = now
        if (
            self._left_drag is not None
            or self._right_origin is not None
            or now < self._drag_release_pause_until
            or abs(self._drag_angle) >= DRAG_REST_ANGLE
            or abs(self._drag_angular_velocity) >= DRAG_REST_SPEED
        ):
            return

        if self._snack_target is not None:
            window = _Rect()
            self._user.GetWindowRect(self._hwnd, ctypes.byref(window))
            center_x = (window.left + window.right) / 2
            center_y = (window.top + window.bottom) / 2
            dx = self._snack_target.center[0] - center_x
            dy = self._snack_target.center[1] - center_y
            distance = math.hypot(dx, dy)
            if distance <= 12.0:
                self._eating_icon = self._snack_target
                self._snack_target = None
                self._eating_started = now
                self._eating_sounded = False
                self._roam_velocity = (0.0, 0.0)
                self._walk_kind = "idle"
            else:
                # Short gait-paced steps make the approach visibly intentional.
                step = min(distance, 220.0 * dt * _walk_speed_scale(now))
                self._roam_velocity = (dx / distance, dy / distance)
                self._user.SetWindowPos(
                    self._hwnd, 0, round(window.left + dx / distance * step),
                    round(window.top + dy / distance * step), 0, 0, 0x1 | 0x4,
                )
            return

        if not self._is_walking() and not self._is_jumping() and self._try_eat_desktop_icon(now):
            return

        window = _Rect()
        self._user.GetWindowRect(self._hwnd, ctypes.byref(window))

        if self._is_jumping():
            progress = self._jump_progress(now)
            origin_x, origin_y = self._jump_origin
            target_x, target_y = self._jump_target
            eased = progress * progress * (3.0 - 2.0 * progress)
            arc = 72.0 * math.sin(math.pi * progress)
            self._user.SetWindowPos(
                self._hwnd,
                0,
                round(origin_x + (target_x - origin_x) * eased),
                round(origin_y + (target_y - origin_y) * eased - arc),
                0,
                0,
                0x1 | 0x4,
            )
            if progress >= 1.0:
                target_x, target_y = self._jump_target
                self._user.SetWindowPos(self._hwnd, 0, target_x, target_y, 0, 0, 0x1 | 0x4)
                self._jump_target = None
                self._jump_origin = None
                self._roam_velocity = (0.0, 0.0)
                self._walk_kind = "idle"
                self._roam_remaining = random.uniform(1.0, 3.0)
            return

        if self._is_peeking():
            if now - self._peek_started >= 0.45:
                self._jump_target = self._peek_target
                self._jump_origin = (window.left, window.top)
                self._jump_started = now
                self._peek_target = None
                self._walk_kind = "jump"
            return

        if not self._is_walking() and self._try_cursor_step(window, now):
            return

        self._roam_remaining -= dt
        if self._roam_remaining <= 0.0:
            if self._is_walking():
                self._roam_velocity = (0.0, 0.0)
                self._roam_remaining = (
                    random.uniform(1.4, 2.4)
                    if self._walk_kind == "cursor"
                    else random.uniform(14.0, 30.0)
                )
                if self._walk_kind == "cursor":
                    self._cursor_pause_until = now + self._roam_remaining
                self._walk_kind = "idle"
            else:
                self._begin_walk()

        if not self._is_walking():
            return

        monitors = self._monitor_rects()
        monitor = self._monitor_for_window(window, monitors)
        if monitor is None:
            return
        if self._try_begin_screen_jump(window, monitor, monitors):
            return

        window_width = window.right - window.left
        window_height = window.bottom - window.top
        velocity_x, velocity_y = self._roam_velocity
        stride = dt * _walk_speed_scale(now) * self._walk_strength(now)
        next_x = round(window.left + velocity_x * stride)
        next_y = round(window.top + velocity_y * stride)
        max_x = monitor.right - window_width
        max_y = monitor.bottom - window_height
        next_x = max(monitor.left, min(max_x, next_x))
        next_y = max(monitor.top, min(max_y, next_y))
        if next_x in (monitor.left, max_x):
            velocity_x *= -1
        if next_y in (monitor.top, max_y):
            velocity_y *= -1
        self._roam_velocity = (velocity_x, velocity_y)
        self._user.SetWindowPos(self._hwnd, 0, next_x, next_y, 0, 0, 0x1 | 0x4)

    def _try_cursor_step(self, window: _Rect, now: float) -> bool:
        if now < self._cursor_next_check or now < self._cursor_pause_until:
            return False
        self._cursor_next_check = now + random.uniform(0.35, 0.8)
        cursor = _Point()
        self._user.GetCursorPos(ctypes.byref(cursor))
        center_x = (window.left + window.right) / 2
        center_y = (window.top + window.bottom) / 2
        dx, dy = cursor.x - center_x, cursor.y - center_y
        distance = math.hypot(dx, dy)
        if not 24.0 < distance <= CURSOR_NOTICE_DISTANCE:
            return False
        if distance <= 150.0:
            self._inspect_until = now + 0.8
            self._inspection_squeaked = False
            self._attention_expression = Expression.WINK
            self._attention_until = self._inspect_until
            self._cursor_pause_until = self._inspect_until + random.uniform(1.4, 2.4)
            return True
        self._begin_walk("cursor", math.atan2(dy, dx), random.uniform(0.45, 0.85))
        return True

    def _begin_walk(
        self,
        kind: str = "wander",
        direction: float | None = None,
        duration: float | None = None,
    ) -> None:
        """Take a few brisk, weighty steps before settling again."""
        direction = random.uniform(0.0, math.tau) if direction is None else direction
        # Ease-in/ease-out lowers average speed, so the stride starts brisker.
        speed = random.uniform(175.0, 230.0)
        self._roam_velocity = (math.cos(direction) * speed, math.sin(direction) * speed)
        self._roam_remaining = random.uniform(2.0, 4.5) if duration is None else duration
        self._walk_kind = kind
        self._walk_started = time.monotonic()
        self._walk_duration = self._roam_remaining

    def _monitor_rects(self) -> list[_Rect]:
        if self._monitors and time.monotonic() < self._next_monitor_refresh:
            return self._monitors
        monitors: list[_Rect] = []

        def collect(_monitor, _dc, rect, _data) -> bool:
            source = rect.contents
            monitors.append(_Rect(source.left, source.top, source.right, source.bottom))
            return True

        callback = _MonitorEnumProc(collect)
        self._user.EnumDisplayMonitors(None, None, callback, 0)
        self._monitors = monitors
        self._next_monitor_refresh = time.monotonic() + 2.0
        return self._monitors

    @staticmethod
    def _monitor_for_window(window: _Rect, monitors: list[_Rect]) -> _Rect | None:
        center_x = (window.left + window.right) / 2
        center_y = (window.top + window.bottom) / 2
        for monitor in monitors:
            if monitor.left <= center_x < monitor.right and monitor.top <= center_y < monitor.bottom:
                return monitor
        return None

    @staticmethod
    def _monitor_for_sprite_top(window: _Rect, monitors: list[_Rect]) -> _Rect | None:
        """Find the active display from Pikita's visible top, even in flight."""
        anchor_x = (window.left + window.right) / 2
        anchor_y = window.top
        for monitor in monitors:
            if monitor.left <= anchor_x < monitor.right and monitor.top <= anchor_y < monitor.bottom:
                return monitor
        # A jump arc can briefly put his top between displays. Pick the closest
        # monitor so perspective continues changing instead of freezing.
        if not monitors:
            return None
        return min(
            monitors,
            key=lambda monitor: (
                max(monitor.left - anchor_x, 0, anchor_x - monitor.right) ** 2
                + max(monitor.top - anchor_y, 0, anchor_y - monitor.bottom) ** 2
            ),
        )

    def _try_begin_screen_jump(
        self, window: _Rect, monitor: _Rect, monitors: list[_Rect]
    ) -> bool:
        velocity_x, velocity_y = self._roam_velocity
        width = window.right - window.left
        height = window.bottom - window.top
        for other in monitors:
            if other is monitor:
                continue
            if velocity_x < 0 and window.left - monitor.left <= SCREEN_EDGE_DISTANCE and abs(other.right - monitor.left) <= 2:
                target = (other.right - width - 12, max(other.top, min(other.bottom - height, window.top)))
            elif velocity_x > 0 and monitor.right - window.right <= SCREEN_EDGE_DISTANCE and abs(other.left - monitor.right) <= 2:
                target = (other.left + 12, max(other.top, min(other.bottom - height, window.top)))
            elif velocity_y < 0 and window.top - monitor.top <= SCREEN_EDGE_DISTANCE and abs(other.bottom - monitor.top) <= 2:
                target = (max(other.left, min(other.right - width, window.left)), other.bottom - height - 12)
            elif velocity_y > 0 and monitor.bottom - window.bottom <= SCREEN_EDGE_DISTANCE and abs(other.top - monitor.bottom) <= 2:
                target = (max(other.left, min(other.right - width, window.left)), other.top + 12)
            else:
                continue
            self._peek_target = target
            self._peek_started = time.monotonic()
            self._attention_expression = Expression.SMUG
            self._attention_until = self._peek_started + 0.45
            return True
        return False

    def _is_jumping(self) -> bool:
        return self._jump_target is not None

    def _is_peeking(self) -> bool:
        return self._peek_target is not None

    def _is_inspecting(self) -> bool:
        return time.monotonic() < self._inspect_until

    def _jump_progress(self, now: float | None = None) -> float:
        if not self._is_jumping():
            return 0.0
        return min(1.0, ((time.monotonic() if now is None else now) - self._jump_started) / JUMP_DURATION)

    def _is_walking(self) -> bool:
        return self._roam_velocity != (0.0, 0.0) and not self._is_jumping()

    def _walk_strength(self, now: float | None = None) -> float:
        if not self._is_walking() or self._walk_duration <= 0.0:
            return 0.0
        elapsed = (time.monotonic() if now is None else now) - self._walk_started
        progress = max(0.0, min(1.0, elapsed / self._walk_duration))
        return math.sin(math.pi * progress)

    def _update_squish(self, position: tuple[int, int]) -> None:
        if self._right_origin is None:
            return
        start_x, start_y = self._right_origin
        x, y = position
        dx, dy = x - start_x, y - start_y
        self._left_max_move = max(self._left_max_move, (dx * dx + dy * dy) ** 0.5)

        self._squish_x, self._squish_y = _squish_from_drag(
            self._right_origin,
            position,
            (self._overlay_sprite_width, self._overlay_sprite_height)
            if self._desktop_transparent else (self._width, self._height),
        )

    def _update_drag_physics(self) -> None:
        now = time.monotonic()
        dt = min(now - self._drag_physics_time, 0.05)
        self._drag_physics_time = now
        if self._left_drag is not None:
            self._drag_velocity_x *= math.exp(-dt * 9.0)
            size = (
                (self._overlay_sprite_width, self._overlay_sprite_height)
                if self._desktop_transparent else (self._width, self._height)
            )
            self._left_grab = (
                round(self._left_grab_ratio[0] * size[0]),
                round(self._left_grab_ratio[1] * size[1]),
            )
            self._drag_target_angle = _grab_angle(
                self._left_grab, size, self._drag_velocity_x
            )
            stiffness, damping = 72.0, 17.0
            acceleration = (
                (self._drag_target_angle - self._drag_angle) * stiffness
                - self._drag_angular_velocity * damping
            )
        else:
            stiffness, damping = 28.0, 10.5
            acceleration = -self._drag_angle * stiffness - self._drag_angular_velocity * damping
        self._drag_angular_velocity += acceleration * dt
        self._drag_angular_velocity = max(-720.0, min(720.0, self._drag_angular_velocity))
        self._drag_angle += self._drag_angular_velocity * dt
        if (
            abs(self._drag_angle) < DRAG_REST_ANGLE
            and abs(self._drag_angular_velocity) < DRAG_REST_SPEED
        ):
            self._drag_angle = self._drag_angular_velocity = 0.0
            if self._drag_release_pending:
                # Let the sprite visibly settle before its normal curiosity
                # routines can choose another walk or icon target.
                self._drag_release_pending = False
                self._drag_release_pause_until = now + random.uniform(1.2, 2.0)
                self._roam_remaining = random.uniform(4.0, 8.0)

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
                if self._left_drag is not None:
                    self._move_window(event.pos)
                if self._right_origin is not None:
                    self._update_squish(event.pos)
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
                if self._left_drag is not None:
                    self._move_window(payload)
                if self._right_origin is not None:
                    self._update_squish(payload)
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
        self._update_drag_physics()
        # Only the true-alpha desktop overlay is allowed to move itself.
        if self._desktop_transparent:
            self._wander()
        if self._left_drag is not None and not intent.squishing:
            intent = replace(intent, expression=Expression.UNIMPRESSED)
        elif time.monotonic() < self._attention_until and not intent.squishing:
            intent = replace(intent, expression=self._attention_expression)
        if self._is_inspecting() and not self._inspection_squeaked and self._poke_sounds:
            random.choice(self._poke_sounds).play()
            self._inspection_squeaked = True
        if self._eating_icon is not None and not self._eating_sounded and self._poke_sounds:
            # Temporary stand-in until the selected Minecraft eating asset is supplied.
            random.choice(self._poke_sounds).play()
            self._eating_sounded = True
        if intent.sound is Sound.SQUEAK and self._poke_sounds:
            random.choice(self._poke_sounds).play()

        if intent.squishing:
            if self._held_squeaks and (
                self._held_channel is None or not self._held_channel.get_busy()
            ):
                self._held_channel = random.choice(self._held_squeaks).play(loops=-1)
        elif self._held_channel is not None:
            self._held_channel.fadeout(100)
            self._held_channel = None

        if self._desktop_transparent:
            self._update_overlay_scale(intent)
            self._anchor_dragged_sprite(intent)
            self._render_layered(intent)
            self._clock.tick(FPS)
            return

        glClearColor(*BACKGROUND, 0.0)
        glClear(GL_COLOR_BUFFER_BIT)
        glBindTexture(GL_TEXTURE_2D, self._texture_for(intent))

        left, top, width, height = self._sprite_layout(intent)
        corners = _rotated_quad(left, top, width, height, self._drag_angle)

        glBegin(GL_QUADS)
        glTexCoord2f(0, 0)
        glVertex2f(*corners[0])
        glTexCoord2f(1, 0)
        glVertex2f(*corners[1])
        glTexCoord2f(1, 1)
        glVertex2f(*corners[2])
        glTexCoord2f(0, 1)
        glVertex2f(*corners[3])
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
