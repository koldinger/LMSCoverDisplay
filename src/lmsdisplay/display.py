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
import time
from threading import Thread
from typing import Optional

from icecream import ic
from PIL import Image, ImageEnhance

from . import transitions

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
                 size: tuple[int, int],
                 orientation: int):
        self.dimming: float | None = None
        self.imgsize = size
        self.orientation = orientation
        self.saver: screensaver.ScreenSaver | None = None
        self.transitions = translist or list(transitions.TransitionTypes)
        self.frames = frames
        self.frame_delay = frame_delay
        self.blank: Image.Image
        self.overlay: Optional[Image.Image] = None
        self.saver:   Optional[screensaver.ScreenSaver] = None

    def show_artwork(self, artwork: Optional[Image.Image]) -> None:
        pass

    def transition(self, old_artwork: Optional[Image.Image], new_artwork: Optional[Image.Image], trans: Optional[transitions.TransitionTypes] = None, frames=None, frame_delay=None) -> int:
        # use the specified transition, or choose one
        trans = trans or random.choice(self.transitions)

        # Get values, overriding the internal values if specified
        old_artwork = old_artwork or self.blank
        new_artwork = new_artwork or self.blank
        frames = frames or self.frames
        frame_delay = frame_delay or self.frame_delay

        func = trans.function
        nframes = 0
        for i in func(old_artwork, new_artwork, frames):
            self.show_artwork(i)
            time.sleep(frame_delay)
            nframes += 1

        return nframes

    def set_transitions(self, trans:list[transitions.TransitionTypes]):
        self.transitions = trans or list(transitions.TransitionTypes)
        ic(self.transitions, trans)

    def refresh(self):
        pass

    def start_screensaver(self, saver):
        ic(saver)
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


def FlashenDisplay(trans_list, frames, frame_delay,  size, orientation, driver_config) -> Display:
    from . import display_flaschen
    return display_flaschen.FlashenDisplay(trans_list, frames, frame_delay, size, orientation, driver_config)

def InternalDisplay(trans_list, frames, frame_delay, size, orientation, driver_config) -> Display:
    from . import display_internal
    return display_internal.InternalDisplay(trans_list, frames, frame_delay, size, orientation, driver_config)

def EmulatedDisplay(trans_list, frames, frame_delay, size, orientation, driver_config) -> Display:
    from . import display_emulated
    return display_emulated.EmulatedDisplay(trans_list, frames, frame_delay, size, orientation, driver_config)
