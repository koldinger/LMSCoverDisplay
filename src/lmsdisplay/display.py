# vim: set et sw=4 sts=4 fileencoding=utf-8:
#
# Copyright 2026-2026, Eric Koldinger, All Rights Reserved.
# kolding@washington.edu
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#     * Neither the name of the copyright holder nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import random
from threading import Thread, RLock
import time
from typing import Optional
from types import SimpleNamespace

from PIL import Image, ImageEnhance

from . import screensaver, transitions

from icecream import ic
try:
    import flaschen
    HAS_FLASHCEN = True
except ModuleNotFoundError:
    HAS_FLASHCEN = False

try:
    #import rgbmatrix
    import RGBMatrixEmulator as rgbmatrix
    HAS_RGBMATRIX = True
except ModuleNotFoundError:
    HAS_RGBMATRIX = False

# --------------------------------------------------------------------------
# Display interface - subclass this to drive real hardware/UI
# --------------------------------------------------------------------------

if not any([HAS_FLASHCEN, HAS_RGBMATRIX]):
    raise Exception("No display driver available")

class Display:
    """
    Override these methods to drive real hardware (LED matrix, framebuffer,
    a GUI window, whatever). The default implementations just log, which is
    enough to see the state machine working end to end.
    """

    def __init__(self,
                 translist: list[transitions.TransitionTypes],
                 frames: int,
                 frame_delay: float,
                 size: tuple[int, int],
                 orientation: int):
        self.dimming: float | None = None
        self.imgsize = size
        self.orientation = orientation
        self.saver: screensaver.ScreenSaver | None = None
        self.translist = translist or list(transitions.TransitionTypes)
        self.frames = frames
        self.frame_delay = frame_delay
        self.blank: Image.Image
        self.overlay: Optional[Image.Image] = None
        self.saver:   Optional[screensaver.ScreenSaver] = None

    def show_artwork(self, artwork: Optional[Image.Image]) -> None:
        pass

    def transition(self, old_artwork: Optional[Image.Image], new_artwork: Optional[Image.Image], trans: Optional[transitions.TransitionTypes] = None, frames=None, frame_delay=None) -> int:
        if not trans:
            trans = random.choice(self.translist)

        if not old_artwork:
            old_artwork = self.blank
        if not new_artwork:
            new_artwork = self.blank
        if frames is None:
            frames = self.frames
        if frame_delay is None:
            frame_delay = self.frame_delay

        func = trans.function
        nframes = 0
        for i in func(old_artwork, new_artwork, frames):
            self.show_artwork(i)
            time.sleep(frame_delay)
            nframes += 1

        return nframes


    def refresh(self):
        pass

    def start_screensaver(self, saver):
        self.saver = saver
        self.saver_thread = Thread(target=self.saver.run, daemon=True)
        self.saver_thread.daemon = True
        self.saver_thread.start()

    def stop_screensaver(self) -> None:
        if self.saver and self.saver_thread:
            self.saver.stop()
            self.saver_thread.join()
            self.saver_thread = None

    def set_overlay(self, overlay: Optional[Image.Image]):
        self.overlay = overlay

    def clear(self) -> None:
        pass

    def dim(self, amount: float) -> None:
        self.dimming = amount

    def undim(self) -> None:
        self.dimming = None

    def size(self) -> tuple[int, int]:
        return self.imgsize

    def _prepare_artwork(self, art):
        #ic(art, self.overlay)
        if not art:
            art = self.blank

        # Check that no orientation is needed
        if self.orientation:
            art = art.rotate(self.orientation)

        # If there's an overlay, paste it over the image.
        if self.overlay:
            art = art.copy()
            art.paste(self.overlay, (0, 0), self.overlay)

        # If dimming is on, dim the image.
        if self.dimming is not None:
            # Wish there was some way to cache this.
            art = ImageEnhance.Brightness(art).enhance(self.dimming)

        return art

class FlashenDisplay(Display):
    def __init__(self, translist: list[transitions.TransitionTypes], frames: int, frame_delay: float, size: tuple[int, int], orientation: int, driver_config: SimpleNamespace):
        super().__init__(translist, frames, frame_delay, size, orientation)
        if not HAS_FLASHCEN:
            raise ImportError("Flaschen-Taschen driver not installed.")
        self.disp = flaschen.Flaschen(driver_config.host, driver_config.port, size[0], size[1])

        self.blank = Image.new("RGB", self.imgsize)
        self.lock = RLock()

    def show_artwork(self, artwork: Optional[Image.Image]) -> None:
        """ Send art to the flashchen-taschen display, over the network. """

        artwork = self._prepare_artwork(artwork)

        px = artwork.load()
        with self.lock:
            for x in range(artwork.width):
                for y in range(artwork.height):
                    pixel = tuple(px[x, y])
                    self.disp.set(x, y, pixel)
            self.disp.send()

    def transition(self, old_artwork: Optional[Image.Image], new_artwork: Optional[Image.Image], trans: Optional[transitions.TransitionTypes] = None, frames=None, frame_delay=None) -> int:
        with self.lock:
            return super().transition(old_artwork, new_artwork, trans, frames, frame_delay)

    def refresh(self):
        with self.lock:
            self.disp.send()


class InternalDisplay(Display):
    # def __init__(self, translist: list[transitions.TransitionTypes], frames: int, frame_delay: float, host: str, port: int, xsize: int, ysize: int, orientation: int):
    def __init__(self, translist: list[transitions.TransitionTypes], frames: int, frame_delay: float, size: tuple[int, int], orientation: int, driver_config: SimpleNamespace):
        super().__init__(translist, frames, frame_delay, size, orientation)
        if not HAS_RGBMATRIX:
            raise ImportError("RGB Matix Driver not installed.")
        options = rgbmatrix.RGBMatrixOptions()
        options.cols = size[0]
        options.rows = size[1]
        options.chain_length = 1
        options.parallel = 1
        options.brightness = driver_config.led_brightness
        options.gpio_slowdown = driver_config.gpio_slowdown
        options.hardware_mapping = driver_config.hw_mapping
        options.pwm_bits = 11
        options.limit_refresh_rate_hz = driver_config.max_framerate
        options.disable_hardware_pulsing = False
        options.daemon = False
        options.drop_privileges = False

        self.options = options                      # Oh why not
        self.matrix = rgbmatrix.RGBMatrix(options=options)
        self.canvas = self.matrix.CreateFrameCanvas()

        self.blank = Image.new("RGB", self.imgsize)


    def show_artwork(self, artwork: Optional[Image.Image]) -> None:
        """ Send art to the display. """
        art = self._prepare_artwork(artwork)

        self.canvas.SetImage(art.convert("RGB"))
        self.canvas = self.matrix.SwapOnVSync(self.canvas)

    def clear(self) -> None:
        self.matrix.Clear()
