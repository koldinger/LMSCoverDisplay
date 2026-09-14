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
import threading
import time

from PIL import Image, ImageEnhance

from . import flaschen, screensaver, transitions

# --------------------------------------------------------------------------
# Display interface - subclass this to drive real hardware/UI
# --------------------------------------------------------------------------

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
                 saver: screensaver.ScreenSaver | None = None):
        self.dimming: float | None = None
        self.saver: screensaver.ScreenSaver | None = None
        self.translist = translist or list(transitions.TransitionTypes)
        self.frames = frames
        self.frame_delay = frame_delay
        self.saver = saver
        self.blank: Image.Image

    def show_artwork(self, artwork: Image.Image) -> None:
        pass

    def transition(self, old_artwork: Image.Image, new_artwork: Image.Image, trans: transitions.TransitionTypes | None = None) -> None:
        if not trans:
            trans = random.choice(self.translist)

        if not old_artwork:
            old_artwork = self.blank
        if not new_artwork:
            new_artwork = self.blank

        func = trans.function
        for i in func(old_artwork, new_artwork, self.frames):
            self.show_artwork(i)
            time.sleep(self.frame_delay)

    def refresh(self):
        pass

    def start_screensaver(self, saver):
        self.saver = saver
        self.saver_thread = threading.Thread(target=self.saver.run)
        self.saver_thread.start()

    def stop_screensaver(self) -> None:
        if self.saver and self.saver_thread:
            self.saver.stop()
            self.saver_thread.join()
            self.saver_thread = None

    def clear(self) -> None:
        pass

    def dim(self, amount: float) -> None:
        self.dimming = amount

    def undim(self) -> None:
        self.dimming = None

class FlashenDisplay(Display):
    def __init__(self, translist: list[transitions.TransitionTypes], frames: int, frame_delay: float, host: str, port: int, xsize: int, ysize: int, orientation: int):
        super().__init__(translist, frames, frame_delay)
        self.disp = flaschen.Flaschen(host, port, xsize, ysize)
        self.orientation = orientation

        self.blank = Image.new("RGB", (xsize, ysize))
        self.lock = threading.Lock()


    def show_artwork(self, art: Image.Image) -> None:
        """ Send art to the flashchen-taschen display, over the network. """
        #ic(art)
        if not art:
            art = self.blank

        # Check that no orientation is needed
        if self.orientation:
            art.rotate(self.orientation)

        if self.dimming is not None:
            # Wish there was some way to cache this.
            art = ImageEnhance.Brightness(art).enhance(self.dimming)

        px = art.load()
        with self.lock:
            for x in range(art.width):
                for y in range(art.height):
                    pixel = tuple(px[x, y])
                    self.disp.set(x, y, pixel)
            self.disp.send()

    def refresh(self):
        with self.lock:
            self.disp.send()



# ADAFRUIT_HAT_PWM = "adafruit-hat-pwm"
# ADAFRUIT_HAT = "adafruit-hat"
# DEFAULT_HARDWARE = ADAFRUIT_HAT_PWM
#
# class InternalDisplay:
#     def __init__(self, xsize: int, ysize: int, gpio_slowdown: int, max_refresh: int):
#         options = RgbMatrixDriver.RGBMatrixOptions()
#         options.cols = xsize
#         options.rows = ysize
#         options.chain_length = 1
#         options.parallel = 1
#         options.brightness = 100
#         options.gpio_slowdown = gpio_slowdown
#         options.hardware_mapping = DEFAULT_HARDWARE
#         options.pwm_bits = 11
#         options.limit_refresh_rate_hz = max_refresh
#         options.disable_hardware_pulsing = False
#
#         self.options = options                      # Oh why not
#         self.matrix = RgbMatrixDriver.RGBMatrix(options=options)
#         self.canvas = self.matrix.CreateFrameCanvas()
#
#     def send_image(self, art: Image.Image) -> None:
#         self.canvas.SetImage(art.convert("RGB"))
#         self.canvas = self.matrix.SwapOnVSync(self.canvas)
#
#     def clear(self) -> None:
#         self.matrix.Clear()
