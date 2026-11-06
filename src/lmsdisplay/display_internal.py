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

from types import SimpleNamespace
from typing import Optional

#from icecream import ic
from PIL import Image

from . import display, transitions

# --------------------------------------------------------------------------
# Display interface - subclass this to drive real hardware/UI
# --------------------------------------------------------------------------


class InternalDisplay(display.Display):
    # def __init__(self, translist: list[transitions.TransitionTypes], frames: int, frame_delay: float, host: str, port: int, xsize: int, ysize: int, orientation: int):
    def __init__(self, translist: list[transitions.TransitionTypes], frames: int, frame_delay: float, size: tuple[int, int], orientation: int, driver_config: SimpleNamespace):
        super().__init__(translist, frames, frame_delay, size, orientation)
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
