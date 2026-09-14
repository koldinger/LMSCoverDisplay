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

import time
import random
from io import BytesIO
from threading import Thread, Event
from datetime import datetime, timedelta

from LMSTools import LMSServer
from urllib.parse import urljoin
import requests
from PIL import Image

from icecream import ic

from lmsdisplay import util, transitions, display

ic.configureOutput(includeContext=True)

BLANK = Image.new("RGB", (64, 64), color=(0, 0, 0))

class ScreenSaver(Thread):
    def __init__(self, server: LMSServer, display, display_time, frame_delay, adjustor: util.ImageAdjuster):
        super().__init__()
        ic("__INIT__", display_time, frame_delay)

        self.server = server
        self.display = display
        self.stopped = False
        self.frame_delay = frame_delay
        self.adjustor = adjustor
        self.pause_delta = timedelta(seconds=display_time)
        self.display_time = display_time
        self.last_img = BLANK
        self.stop_event = Event()

        # Make sure we shutdown if everything else does, rather than hanging around forever.
        self.daemon = True

    def num_albums(self):
        resp = self.server.request(params="info total albums ?")
        return resp["_albums"]

    def album(self, number):
        resp = self.server.request(params=["albums", number, 1, "tags:jlt"])
        return resp["albums_loop"][0]

    def random_album(self):
        num = random.randint(0, self.num_albums())
        album = self.album(num)
        return album

    def get_art(self, track_id) -> Image.Image:
        url = urljoin(self.server.url, f"music/{track_id}/cover.jpg")
        ic(url)
        resp = requests.get(url, timeout=(5, 10))
        img = Image.open(BytesIO(resp.content)) if resp.status_code == requests.codes["ok"] else None
        return img

    def stop(self):
        self.stopped = True
        self.stop_event.set()

    def run(self):
        ic()
        changetime = datetime.now()
        waittime = min(10.0, self.display_time)
        time.sleep(0.1)

        while not self.stopped:
            now = datetime.now()
            ic(now, changetime, now >= changetime)

            if now >= changetime:
                album = self.random_album()
                track_id = album["artwork_track_id"]
                art = self.get_art(track_id)
                if not art:
                    ic("No art")
                    continue

                next_img = self.adjustor.adjustImage(art)
                self.display.transition(self.last_img, next_img, transitions.TransitionTypes.PageTurn)
                changetime = datetime.now() + self.pause_delta
                self.last_img = next_img
            else:
                self.display.refresh()

            # now wait for appropriate time, unless we're woken up.
            self.stop_event.wait(timeout=waittime)

        self.display.transition(self.last_img, None, transitions.TransitionTypes.PageTurn)



if __name__ == "__main__":
    server = LMSServer()
    display = display.FlashenDisplay("localhost", 1337, 64, 64, 0)
    adjustor = util.ImageAdjuster(1.0, 1.0, 64)
    s = ScreenSaver(server, display, 15, 0.05, adjustor)
    s.start()
    time.sleep(65)
    s.stop()
    s.join()

