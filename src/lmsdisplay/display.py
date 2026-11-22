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

from . import transitions, screensaver

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
                 transition_frames: int,
                 transition_fps: float,
                 size: tuple[int, int],
                 orientation: int):
        self.imgsize = size
        self.orientation = orientation
        self.saver: Optional[screensaver.ScreenSaver] = None
        self.transitions = translist or list(transitions.TransitionTypes)
        self.trantsition_frames = transition_frames
        self.transition_fps = transition_fps
        self.frame_delay = 1.0 / transition_fps
        self.overlay: Optional[Image.Image] = None
        self.saver:   Optional[screensaver.ScreenSaver] = None

        self.dimming: float | None = None
        self.grayscale: bool = False
        self.blank: Image.Image = None
        self.last: Image.Image = None

    def show_artwork(self, artwork: Optional[Image.Image]) -> None:
        """ Show the artwork specified. """
        art = self._prepare_artwork(artwork)
        self._do_show(art)
        self.last = artwork     # Keep the unaltered original.   TODO: Come back to this later.


    def transition(self,
                   old_artwork: Optional[Image.Image],
                   new_artwork: Optional[Image.Image],
                   trans: Optional[transitions.TransitionTypes] = None,
                   frames: Optional[int] = None,
                   frame_delay: Optional[int] = None) -> int:
        # use the specified transition, or choose one
        trans = trans or random.choice(self.transitions)

        # Get values, overriding the internal values if specified
        old_art = old_artwork or self.blank
        new_art = new_artwork or self.blank
        frames = frames or self.trantsition_frames
        frame_delay = frame_delay or self.frame_delay

        # Prepare the artwork
        old_art = self._prepare_artwork(old_art)
        new_art = self._prepare_artwork(new_art)

        self.last = new_art
        # And do the actual transition
        return self._do_transition(old_art, new_art, trans, frames, frame_delay)


    def _do_transition(self, old_art, new_art, trans, frames, frame_delay):
        """ The actual work of doing the transition.   """
        func = trans.function
        nframes = 0
        for i in func(old_art, new_art, frames):
            self._do_show(i)
            time.sleep(frame_delay)
            nframes += 1

        return nframes

    def set_transitions(self, trans:list[transitions.TransitionTypes]):
        self.transitions = trans or list(transitions.TransitionTypes)
        #ic(self.transitions, trans)

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

    def refresh(self):
        pass


    def dim(self, amount: float, grayscale: bool) -> None:
        old = self._prepare_artwork(self.last)      # Prepare the old image based on the current configuration
        self.dimming = amount
        self.grayscale = grayscale
        new = self._prepare_artwork(self.last)      # Prepare the new image based on the new configuration.
        self._do_transition(old, new, transitions.TransitionTypes.Fade, self.trantsition_frames, self.frame_delay)

    def undim(self) -> None:
        self.dim(None, False)

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

        if self.grayscale:
            art = ImageEnhance.Color(art).enhance(0)

        return art

    def _do_show(self, art):
        pass


def FlashenDisplay(trans_list, transition_frames, transition_fps,  size, orientation, driver_config) -> Display:
    from . import display_flaschen
    return display_flaschen.FlashenDisplay(trans_list, transition_frames, transition_fps, size, orientation, driver_config)

def InternalDisplay(trans_list, transition_frames, transition_fps, size, orientation, driver_config) -> Display:
    from . import display_internal
    return display_internal.InternalDisplay(trans_list, transition_frames, transition_fps, size, orientation, driver_config)

def EmulatedDisplay(trans_list, transition_frames, transition_fps, size, orientation, driver_config) -> Display:
    from . import display_emulated
    return display_emulated.EmulatedDisplay(trans_list, transition_frames, transition_fps, size, orientation, driver_config)
