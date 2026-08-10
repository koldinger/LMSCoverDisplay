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

import rgbmatrix
from . import flaschen
from PIL import Image


class FlashenDisplay:
    def __init__(self, host: str, port: int, xsize: int, ysize: int):
        self.disp = flaschen.Flaschen(host, port, xsize, ysize)

    def send_image(self, art: Image.Image) -> None:
        """ Send art to the flashchen-taschen display, over the network. """
        px = art.load()
        for x in range(art.width):
            for y in range(art.height):
                pixel = tuple(px[x, y])
                self.disp.set(x, y, pixel)
        self.disp.send()


ADAFRUIT_HAT_PWM = "adafruit-hat-pwm"
ADAFRUIT_HAT = "adafruit-hat"
DEFAULT_HARDWARE = ADAFRUIT_HAT_PWM

class InternalDisplay:
    def __init__(self, xsize: int, ysize: int, gpio_slowdown: int, max_refresh: int):
        options = rgbmatrix.RGBMatrixOptions()
        options.cols = xsize
        options.rows = ysize
        options.chain_length = 1
        options.parallel = 1
        options.brightness = 100
        options.gpio_slowdown = gpio_slowdown
        options.hardware_mapping = DEFAULT_HARDWARE
        options.pwm_bits = 11
        options.limit_refresh_rate_hz = max_refresh
        options.disable_hardware_pulsing = False

        self.options = options                      # Oh why not
        self.matrix = rgbmatrix.RGBMatrix(options=options)
        self.canvas = self.matrix.CreateFrameCanvas()

    def send_image(self, art: Image.Image) -> None:
        self.canvas.SetImage(art.convert("RGB"))
        self.canvas = self.matrix.SwapOnVSync(self.canvas)

    def clear(self) -> None:
        self.matrix.Clear()
