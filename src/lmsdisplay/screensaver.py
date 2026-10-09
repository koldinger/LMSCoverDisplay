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
import importlib.resources

import requests
from icecream import ic
from LMSTools import LMSServer
from PIL import Image, ImageDraw, ImageFont

import imgcat

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
        self.last_img = self.adjustor.adjustor(BLANK)

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
        ic("CoverFlowScreensaver Starting")
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


class DigitalClockScreenSaver(ScreenSaver):
    def __init__(self, display, time_fmt, font, adjustor):
        super().__init__(display)
        self.adjustor = adjustor
        self.formats = ["%-I:%M", "%-I %M"] if time_fmt == 12 else ["%-H:%M", "%-H %M"]
        style = font.title().replace("_", "")
        fontname = f"DSEG7Modern-{style}.woff2"
        fontpath = importlib.resources.files("lmsdisplay").joinpath("fonts").joinpath(fontname)
        ic(fontpath)
        ic(font, style, fontpath)
        self.font = ImageFont.truetype(fontpath, 48)

    def run(self):
        self.stopped = False
        ic("Screensaver Starting")
        minute = -1
        last_img = self.adjustor.adjustImage(BLANK)
        images = []

        while not self.stopped:
            now = datetime.now().time()
            if now.minute != minute:
                ic("Updating time", now)
                minute = now.minute
                images = [Image.new("RGB", (200, 200), color="black") for i in range(0, 2)]

                for i in [0, 1]:
                    drw = ImageDraw.Draw(images[i])
                    txt = now.strftime(self.formats[i])
                    drw.text((100, 100), txt, fill=(255, 0, 0), font=self.font, anchor="mm")

                    images[i] = self.adjustor.adjustImage(images[i])
                    ic(self.display.size(), images[i].size)

            n = self.display.transition(last_img, images[0], transitions.TransitionTypes.Fade, frames=5)
            s = max((1.0 - (n * self.display.frame_delay)), 0)
            time.sleep(s)
            n = self.display.transition(images[0], images[1], transitions.TransitionTypes.Fade, frames=5)
            last_img = images[1]
            self.stop_event.wait(timeout=s)
            self.stop_event.clear()

        ic()
        self.display.transition(last_img, BLANK, transitions.TransitionTypes.Fade)
        ic("Screensaver Done")

if __name__ == "__main__":
    from types import SimpleNamespace
    def run_saver(saver):
        t = threading.Thread(target=saver.run)
        t.start()
        time.sleep(65)
        saver.stop()
        t.join()

    server = LMSServer()
    #display = display.FlashenDisplay("localhost", 1337, 64, 64, 0)
    config = {
        "host": "localhost",
        "port": 1337,
    }
    disp = display.FlashenDisplay([], 25, 0.05, (64, 64), 0, SimpleNamespace(**config))
    adjustor = util.ImageAdjuster(1.0, 1.0, 64)
    #s = CoverFlowScreensaver(disp, server, 5, 0.05, adjustor)
    s = DigitalClockScreenSaver(disp, 12, "bold-italic", adjustor)
    run_saver(s)
