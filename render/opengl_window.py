"""OpenGL desktop renderer with an alpha channel OBS can preserve."""

import ctypes
import json
from ctypes import wintypes
from pathlib import Path

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
from pygame.locals import DOUBLEBUF, NOFRAME, OPENGL

from input.events import FrameInput
from pet.intent import PetIntent, Sound
from render.renderer import Renderer

TARGET_HEIGHT = 600
FPS = 60
BACKGROUND = (0.075, 0.085, 0.12)
DRAG_THRESHOLD = 6


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
    if abs(from_center_x) > abs(from_center_y):
        inward = abs(from_center_x) - abs(x - center_x)
        return max(0.0, min(1.0, inward / max(abs(from_center_x), 1))), 0.0
    inward = abs(from_center_y) - abs(y - center_y)
    return 0.0, max(0.0, min(1.0, inward / max(abs(from_center_y), 1)))


class _DwmBlurBehind(ctypes.Structure):
    _fields_ = [
        ("dwFlags", ctypes.c_uint),
        ("fEnable", ctypes.c_int),
        ("hRgnBlur", wintypes.HRGN),
        ("fTransitionOnMaximized", ctypes.c_int),
    ]


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _Rect(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class OpenGLWindow(Renderer):
    def __init__(self, assets_dir: Path):
        self._settings_path = assets_dir.parent / "settings.json"
        settings = self._load_settings()
        pygame.init()
        pygame.display.gl_set_attribute(pygame.GL_ALPHA_SIZE, 8)

        pngs = sorted(assets_dir.glob("*.png"))
        if not pngs:
            raise FileNotFoundError(f"No .png sprites found in {assets_dir}")

        sample = pygame.image.load(str(pngs[0]))
        scale = TARGET_HEIGHT / sample.get_height()
        self._width = round(sample.get_width() * scale)
        self._height = TARGET_HEIGHT
        pygame.display.set_mode(
            (self._width, self._height), OPENGL | DOUBLEBUF | NOFRAME
        )
        pygame.display.set_caption("Pocket Pikita")

        self._hwnd = pygame.display.get_wm_info()["window"]
        self._configure_win32()
        self._always_on_top = bool(settings.get("always_on_top", True))
        self._desktop_transparent = False
        position = settings.get("position")
        if isinstance(position, list) and len(position) == 2:
            self._user.SetWindowPos(
                self._hwnd, 0, int(position[0]), int(position[1]), 0, 0, 0x1 | 0x4
            )
        self._set_topmost(self._always_on_top)
        if settings.get("desktop_transparent", False):
            self._set_desktop_transparency(True)

        self._textures: dict[str, int] = {}
        for png in pngs:
            surface = pygame.image.load(str(png)).convert_alpha()
            surface = pygame.transform.smoothscale(surface, (self._width, self._height))
            self._textures[_normalize(png.name)] = self._make_texture(surface)

        self._setup_gl()
        self._clock = pygame.time.Clock()
        self._left_origin: tuple[int, int] | None = None
        self._left_max_move = 0.0
        self._squish_x = 0.0
        self._squish_y = 0.0
        self._right_drag: tuple[int, int, int, int] | None = None

        try:
            pygame.mixer.init()
            self._sounds = {
                Sound.SQUEAK: pygame.mixer.Sound(str(assets_dir / "Squeak.ogg"))
            }
        except pygame.error:
            self._sounds = {}

    def _configure_win32(self) -> None:
        self._dwm = ctypes.windll.dwmapi
        self._gdi = ctypes.windll.gdi32
        self._user = ctypes.windll.user32
        self._dwm.DwmEnableBlurBehindWindow.argtypes = [
            wintypes.HWND,
            ctypes.POINTER(_DwmBlurBehind),
        ]
        self._dwm.DwmEnableBlurBehindWindow.restype = ctypes.c_long
        self._gdi.CreateRectRgn.argtypes = [ctypes.c_int] * 4
        self._gdi.CreateRectRgn.restype = wintypes.HRGN
        self._gdi.DeleteObject.argtypes = [wintypes.HGDIOBJ]
        self._user.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND] + [
            ctypes.c_int
        ] * 4 + [ctypes.c_uint]
        self._user.GetCursorPos.argtypes = [ctypes.POINTER(_Point)]
        self._user.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(_Rect)]

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

    def _texture_for(self, intent: PetIntent) -> int:
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
            texture = self._textures.get(_normalize(candidate))
            if texture is not None:
                return texture
        return self._textures[_normalize("Base")]

    def _set_desktop_transparency(self, enable: bool) -> None:
        blur = _DwmBlurBehind()
        region = None
        if enable:
            region = self._gdi.CreateRectRgn(0, 0, -1, -1)
            blur.dwFlags = 0x1 | 0x2  # enable + blur region
            blur.fEnable = 1
            blur.hRgnBlur = region
        else:
            blur.dwFlags = 0x1
            blur.fEnable = 0
        result = self._dwm.DwmEnableBlurBehindWindow(
            self._hwnd, ctypes.byref(blur)
        )
        if region:
            self._gdi.DeleteObject(region)
        if result != 0:
            raise OSError(f"DWM transparency toggle failed: HRESULT {result}")
        self._desktop_transparent = enable

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
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit_ = True
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    quit_ = True
                elif event.key == pygame.K_t:
                    self._set_desktop_transparency(not self._desktop_transparent)
                elif event.key == pygame.K_a:
                    self._set_topmost(not self._always_on_top)
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    self._left_origin = event.pos
                    self._left_max_move = 0.0
                elif event.button == 3:
                    self._begin_window_drag()
            elif event.type == pygame.MOUSEMOTION:
                if self._left_origin is not None:
                    self._update_squish(event.pos)
                if self._right_drag is not None:
                    self._move_window()
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1 and self._left_origin is not None:
                    poked = self._left_max_move < DRAG_THRESHOLD
                    self._left_origin = None
                    self._squish_x = self._squish_y = 0.0
                elif event.button == 3:
                    self._right_drag = None

        return FrameInput(
            quit=quit_,
            poked=poked,
            squish_x=self._squish_x,
            squish_y=self._squish_y,
        )

    def render(self, intent: PetIntent) -> None:
        if intent.sound is not None:
            sound = self._sounds.get(intent.sound)
            if sound is not None:
                sound.play()

        glClearColor(*BACKGROUND, 0.0)
        glClear(GL_COLOR_BUFFER_BIT)
        glBindTexture(GL_TEXTURE_2D, self._texture_for(intent))

        width_scale = 1.0 - 0.62 * intent.squish_x + 0.12 * intent.squish_y
        height_scale = 1.0 - 0.62 * intent.squish_y + 0.12 * intent.squish_x
        width = self._width * width_scale
        height = self._height * height_scale
        left = (self._width - width) / 2
        top = (self._height - height) / 2
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
        if self._desktop_transparent:
            self._set_desktop_transparency(False)
        glDeleteTextures(list(self._textures.values()))
        pygame.quit()
