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

import random
import threading
import time
from datetime import datetime, timedelta
from io import BytesIO
from urllib.parse import urljoin

import requests
from icecream import ic
from LMSTools import LMSServer
from PIL import Image

from lmsdisplay import display, transitions, util

ic.configureOutput(includeContext=True)

BLANK = Image.new("RGB", (64, 64), color=(0, 0, 0))

class ScreenSaver:
    def __init__(self, display):
        self.display = display
        self.stopped = False
        self.stop_event = threading.Event()

    def stop(self):
        ic()
        self.stopped = True
        self.stop_event.set()

    def run(self):
        pass

class CoverFlowScreensaver(ScreenSaver):
    def __init__(self, display, server, display_time, frame_delay, adjustor):
        super().__init__(display)
        self.frame_delay = frame_delay
        self.pause_delta = timedelta(seconds=display_time)
        self.display_time = display_time
        self.server = server
        self.adjustor = adjustor
        self.last_img = BLANK

    def num_albums(self):
        resp = self.server.request(params="info total albums ?")
        return resp["_albums"]

    def album(self, number):
        # TODO:: replace the 'j' with the appropriate LMSTags value
        resp = self.server.request(params=["albums", number, 1, "tags:j"])
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

    def run(self):
        self.stopped = False
        ic("Screensaver Starting")
        changetime = datetime.now()
        waittime = min(10.0, self.display_time)

        time.sleep(0.1)

        while not self.stopped:
            now = datetime.now()
            ic(now, changetime, now >= changetime)

            if now >= changetime:
                album = self.random_album()
                track_id = album["artwork_track_id"]
                ic(album)
                art = self.get_art(track_id)
                if not art:
                    ic("No art")
                    continue

                next_img = self.adjustor.adjustImage(art)
                self.display.transition(self.last_img, next_img, transitions.TransitionTypes.PageTurn)
                changetime = datetime.now() + self.pause_delta
                self.last_img = next_img
            else:
                #self.send_art(self.last_img)
                self.display.refresh()

            # now wait for appropriate time, unless we're woken up.
            self.stop_event.wait(timeout=waittime)
            self.stop_event.clear()

        ic()
        self.display.transition(self.last_img, BLANK, transitions.TransitionTypes.PageTurn)
        ic("Screensaver Done")


if __name__ == "__main__":
    server = LMSServer()
    #display = display.FlashenDisplay("localhost", 1337, 64, 64, 0)
    disp = display.FlashenDisplay([], 25, 0.05, "localhost", 1337, 64, 64, 0)
    adjustor = util.ImageAdjuster(1.0, 1.0, 64)
    s = CoverFlowScreensaver(disp, server, 5, 0.05, adjustor)
    t = threading.Thread(target=s.run)
    t.start()
    time.sleep(65)
    s.stop()
    t.join()

