# vim: set et sw=4 sts=4 fileencoding=utf-8:
#
# Copyright 2025-2026, Eric Koldinger, All Rights Reserved.
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

import threading
import queue
from types import SimpleNamespace
from enum import Enum, auto
from PIL import Image
from typing import Optional
from datetime import datetime

from LMSTools import LMSPlayer

from . import display, screensaver, eventscheduler, volume, util
from .events import EventType, PlayEvent

from icecream import ic

class States(Enum):
    PAUSED = auto()
    PLAYING = auto()


TIMEOUT_DEF = 20

class StateMachine(threading.Thread):
    def __init__(self, config:SimpleNamespace, disp:display.Display, player: LMSPlayer, adjuster: util.ImageAdjuster, event_q: queue.Queue):
        self.queue = event_q

        self._display = disp
        self._config = config
        self._stop = False

        self._player= player
        self._adjuster = adjuster

        self._state = States.PAUSED
        self._saver: Optional[screensaver.ScreenSaver] = None
        self._last_image: Optional[Image.Image] = None
        self._last_song = -1
        self._last_volume = -1
        self._scheduler = eventscheduler.EventScheduler()

        self._dim_event: Optional[eventscheduler.EventData] = None
        self._undim_event: Optional[eventscheduler.EventData] = None
        self._ss_event: Optional[eventscheduler.EventData] = None
        self._pause_event: Optional[eventscheduler.EventData] = None
        self._overlay_event: Optional[eventscheduler.EventData] = None

        # Create events to start and end dimming, assuming they're specified
        self._dim_start = util.parsetime(config.dim_start_time)
        self._dim_end   = util.parsetime(config.dim_end_time)
        ic(config.dim_start_time, self._dim_start, config.dim_end_time, self._dim_end)
        self._dimmed = config.dim_at_night and util.betweentimes(datetime.now().time(), self._dim_start, self._dim_end)
        if self._dimmed:
            print("Setting Dimmed Mode")
            self._display.dim(config.dimmed_brightness)
        if config.dim_at_night:
            d_time = util.next_time(self._dim_start)
            ud_time = util.next_time(self._dim_end)
            ic(d_time, ud_time)
            self._dim_event   = self._scheduler.enterabs(d_time.timestamp(), queue.Queue.put, (self.queue, PlayEvent(EventType.DIM)))
            self._undim_event = self._scheduler.enterabs(ud_time.timestamp(),  queue.Queue.put, (self.queue, PlayEvent(EventType.UNDIM)))

        # TODO: This should be a constructor argument, honestly.
        if config.enable_screensaver:
            ss = config.screensavers.get("screensaver")
            c = SimpleNamespace(**config.screensavers[ss])
            ic(c)
            match config.screensavers["screensaver"]:
                case "coverflow":
                    self._saver = screensaver.CoverFlowScreensaver(self._display, self._player.server, self._config.display_time, c.frame_delay, self._adjuster)
                case "clock":
                    self._saver = screensaver.DigitalClockScreenSaver(self._display, c.hour_format, c.font, self._adjuster)
                case _:
                    raise ValueError(config.screensavers["screensaver"])


    def stop(self):
        self._stop = True
        self.queue.put(PlayEvent(EventType.END))

    def handle_play(self, event):
        """
        Handle a playing event.

        Takes the event, returns the next state (States.PLAYING).
        If we're paused, start playing mode.
        If we're already playing, mostly just refresh.

        Update the volume overlay, if volume has changed.
        """
        ic(event)

        match self._state:
            case States.PAUSED:
                # Cancel any events that are schedule in Paused mode
                self._scheduler.cancel(self._ss_event)
                self._scheduler.cancel(self._pause_event)
                self._ss_event = self._pause_event = None

                self._display.stop_screensaver()

                if self._last_image:
                    self._display.show_artwork(self._last_image)
                else:
                    self._display.transition(self._last_image, event.artwork)
                self._last_image = event.artwork
                self._last_song = event.song
            case States.PLAYING:
                if event.song != self._last_song:
                    if event.artwork != self._last_image:
                        self._display.transition(self._last_image, event.artwork)
                        self._last_image = event.artwork
                    else:
                        self._display.refresh()
                    self._last_song = event.song
                else:
                    self._display.refresh()

                # if the volume has changed, and we want to show the volume bar, create the overlay
                if self._config.show_volume_bar and event.volume != self._last_volume:
                    ic(self._last_volume, event.volume)
                    self._last_volume = event.volume
                    over_color = util.contrasting_color(self._last_image)
                    overlay = volume.drawVolume(event.volume, self._display.size(), color = over_color, xoffset=.05, yoffset=.9, yheight=.05)
                    # Set the overlay, and then send the image again to draw the overlaid image
                    self._display.set_overlay(overlay)
                    self._display.show_artwork(self._last_image)
                    # Cancel the old event, and create a new one
                    self._scheduler.cancel(self._overlay_event)
                    self._overlay_event = self._scheduler.enter(5, queue.Queue.put, (self.queue, PlayEvent(EventType.END_OVERLAY)))

        return States.PLAYING

    def handle_pause(self):
        ic()
        match self._state:
            case States.PAUSED:
                pass
            case States.PLAYING:
                if self._config.pause_delay:
                    self._display.refresh()
                    self._scheduler.enter(self._config.pause_delay, queue.Queue.put, (self.queue, PlayEvent(EventType.END_PAUSE_DELAY)))
                else:
                    self._display.transition(self._last_image, None)
                    self._last_image = None

                if self._config.enable_screensaver:
                    if self._config.screensaver_delay:
                        delay = self._config.screensaver_delay + self._config.pause_delay
                        self._scheduler.enter(delay, queue.Queue.put, (self.queue, PlayEvent(EventType.START_SAVER)))
                    else:
                        self.start_screensaver()
        return States.PAUSED

    def start_screensaver(self):
        ic()
        if self._state == States.PAUSED and not (self._config.disable_screensaver_dimmed and self._dimmed):
            self._display.start_screensaver(self._saver)

    def stop_screensaver(self):
        ic()
        self._display.stop_screensaver()

    def dim(self):
        ic()
        print("Dimming")
        if self._config.disable_screensaver_dimmed and self._saver:
            self.stop_screensaver()
        self._display.dim(self._config.dimmed_brightness)
        self._dim_event = self._scheduler.enterabs(util.next_time(self._dim_start).timestamp(), queue.Queue.put, (self.queue, PlayEvent(EventType.DIM)))
        self._dimmed = True
        if self._state == States.PLAYING:
            self._display.show_artwork(self._last_image)

    def undim(self):
        ic()
        print("Undimming")
        self._display.undim()
        self._undim_event = self._scheduler.enterabs(util.next_time(self._dim_end).timestamp(),  queue.Queue.put, (self.queue, PlayEvent(EventType.UNDIM)))
        self._dimmed = False

        if self._state == States.PAUSED and self._config.enable_screensaver:
            self.start_screensaver()
        elif self._state._state == PLAYING:
            self._display.show_artwork(self._last_image)

    def end_paused_delay(self):
        ic()
        if self._state == States.PAUSED:
            self._display.transition(self._last_image, None)
            self._last_image = None

    def end_overlay(self):
        ic()
        self._display.set_overlay(None)
        self._display.show_artwork(self._last_image)

    def run(self):
        self._scheduler.start_background()
        while not self._stop:
            event = None
            try:
                event = self.queue.get(timeout=TIMEOUT_DEF)
            except queue.Empty:
                ic()
                self._display.refresh()

            ic(event)
            if event:
                match event.mode:
                    case EventType.PLAY:
                        self._state = self.handle_play(event)
                    case EventType.PAUSE | EventType.STOP:
                        self._state = self.handle_pause()
                    case EventType.START_SAVER:
                        self.start_screensaver()
                    case EventType.STOP_SAVER:
                        self.stop_screensaver()
                    case EventType.END_PAUSE_DELAY:
                        self.end_paused_delay()
                    case EventType.END_OVERLAY:
                        self.end_overlay()
                    case EventType.DIM:
                        self.dim()
                    case EventType.UNDIM:
                        self.undim()
                    case EventType.END:
                        break
                    case _:
                        print(f"Unknown Event: {event.mode}")

        print("State machine ending")
        self._scheduler.stop()
        self._display.set_overlay(None)
        self._display.stop_screensaver()
