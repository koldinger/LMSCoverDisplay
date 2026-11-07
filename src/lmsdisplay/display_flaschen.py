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

from threading import RLock
from types import SimpleNamespace
from typing import Optional

import flaschen
from icecream import ic
from PIL import Image

from . import display, transitions


class FlashenDisplay(display.Display):
    def __init__(self, translist: list[transitions.TransitionTypes], frames: int, frame_delay: float, size: tuple[int, int], orientation: int, driver_config: SimpleNamespace):
        super().__init__(translist, frames, frame_delay, size, orientation)
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
