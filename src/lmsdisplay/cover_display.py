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

import argparse
import contextlib
import importlib.metadata
import random
import signal
from threading import TIMEOUT_MAX
import time
from datetime import datetime, timedelta
from queue import Queue, Empty
from pathlib import Path

import rich.traceback
from pid import PidFile
from PIL import Image, ImageEnhance
from rich.console import Console

from LMSTools import server

from . import discovery, flaschen, lms_monitor, transitions, util, volume, defaults, events

rich.traceback.install()
args: argparse.Namespace

def unix_timestamp():
    return f"{datetime.now().strftime("%H:%M")} |> "

from icecream import ic

ic.configureOutput(includeContext=True, prefix=unix_timestamp)
ic.disable()

__version__ = "Unknown"
with contextlib.suppress(importlib.metadata.PackageNotFoundError):
    __version__ = importlib.metadata.version("lmsdisplay")

class PlayerNotFoundError(Exception):
    pass

event_q = Queue()

TIMEOUT_DEF = 20                # 20 second timeout.   Screen should flush at 30

def contrasting_color(art: Image.Image) -> tuple[int, int, int, int]:
    try:
        # Get the averoge color of the current screen.
        # Do this by resizing the picture to 1 pixel, and grabbing the color
        small = art.resize((1, 1), resample=Image.Resampling.LANCZOS).convert("RGB")
        R, G, B = small.getpixel((0, 0))
        # Compute the contrasting color, based on the luma
        luma = 0.299*R + 0.587*G + 0.114*B
        color = (255, 255, 255, 200) if luma <= 128 else (0, 0, 0, 200)
    except:
        color = (255, 255, 255, 200)
    return color

def handleEvents(display, trans):
    lastimg = Image.new("RGB", (config.image_size, config.image_size))
    lastvol = 0

    blank = Image.new("RGB", (config.image_size, config.image_size), color=(0, 0, 0))
    #lyrionlogo = getInternalArt("logo.png")

    if not trans:
        trans = list(transitions.TransitionTypes)

    # Setup as if we're paused at the start.
    playing = False
    pause_delta = timedelta(seconds=config.pause_delay)
    cleartime = None

    timeout = TIMEOUT_DEF

    while True:
        try:
            event = event_q.get(timeout = timeout)
            ic(event)
        except Empty:
            ic("Timeout", playing)
            if playing:
                sendArt(lastimg, display)
            else:
                ic(cleartime, datetime.now())
                if cleartime and datetime.now() >= cleartime:
                    ic("Pause clear 1")
                    sendTransition(display, blank, lastimg, transitions.getTransition(random.choice(trans)))
                    timeout = TIMEOUT_DEF
            continue


        # Grab the current playing status from the stream
        overlay = None

        # Handle a reload event and break out of the loop
        if type(event) is ReloadEvent:
            break

        match event.mode:
            case events.EventType.PLAY:
                playing = True
                art = event.artwork

                if config.show_volume_bar:
                    vol = int(event.volume)

                    # If the volume has changed,
                    if vol != lastvol:
                        lastvol = vol
                        color = contrasting_color(art)
                        overlay = volume.drawVolume(vol, (500,500), color = color, xoffset=.05, yoffset=.9, yheight=.05)

                if art != lastimg:
                    sendTransition(display, art, lastimg, transitions.getTransition(random.choice(trans)))
                else:
                    sendArt(display, art, overlay=overlay)
                lastimg = art

            case events.EventType.PAUSE | events.EventType.STOP:
                if playing:
                    # If we just switched to pause timing, record the time we paused (roughly)
                    if config.pause_delay:
                        pausestart = datetime.now()
                        cleartime = pausestart + pause_delta
                        timeout = min(config.pause_delay, TIMEOUT_DEF)

                playing = False
                pause_img = blank #if config.pauselogo else lyrionlogo

                ic(cleartime, datetime.now())
                if (config.pause_delay == 0) or (cleartime and datetime.now() >= cleartime):
                    # If we're past the pause_delay, switch to the pause display
                    ic("Pause clear 2")
                    if lastimg != blank:
                        sendTransition(display, pause_img, lastimg, transitions.getTransition(random.choice(trans)))
                    #else:
                    #    sendArt(display, pause_img)
                    lastimg = pause_img
                    cleartime = None
                    timeout = TIMEOUT_DEF
                else:
                    # Else, still in the pause delay, just blast the last image
                    sendArt(display, lastimg)
            case _:
                print(event)


def dimImage(image):
    """ Dim an image. """
    if config.dim_at_night:
        image = ImageEnhance.Brightness(image).enhance(config.dimmed_brightness)
    return image

def sendArt(f, art, overlay=None):
    """
    Send art to the display, dimming it if necessary.

    If an overlay image is presented, it will be overlaid over the artwork before sending.
    Sent via the flaschen-taschen library, but sent to via UDP to port 1337 (usually).
    """
    if overlay:
        overlay = overlay.resize(art.size)
        art = art.copy()
        art.paste(overlay, (0, 0), overlay)

    if config.dim_at_night and util.betweentimes(datetime.now().time(), util.parsetime(config.dim_start_time), util.parsetime(config.dim_end_time)):
        art = dimImage(art)

    if config.orientation:
        art = art.rotate(config.orientation)

    px = art.load()
    for x in range(art.width):
        for y in range(art.height):
            pixel = tuple(px[x, y])
            f.set(x, y, pixel)
    f.send()

def sendTransition(f, art, lastimg, transition, overlay=None):
    for i in transition(lastimg, art, config.transition_frames):
        sendArt(f, i, overlay)
        time.sleep(config.frame_delay)

class ReloadEvent:
    pass

def reloadConfig(_signum, _frame):
    """ Receive a SIGHUP and reload the configuration file and command line. """
    global args, config
    args, config = process_cmdline()
    # clear the cache on getArt so we get changes to images immediately
    getArt.cache_clear()
    event_q.put(ReloadEvent())

def getPlayer(servers, name):
    for srv in servers:
        s = server.LMSServer(srv.host, int(srv.port))
        if s:
            players = s.get_players()
            for plr in players:
                if name in (plr.ref ,plr.name):
                    return plr
    raise PlayerNotFoundError(name)


def process_cmdline():                                                                     
    parser = argparse.ArgumentParser("Display album art from Lyrion Music Server")         
                                           # formatter_class=argparse.RawTextHelpFormatter)
    parser.suggest_on_error = True                                                         

    parser.add_argument("--config", dest="config", default=None, type=Path, required=True, help="Load configuration from file")                                                     
    parser.add_argument("--version", action="version", version=__version__)

    args = parser.parse_args()

    conf = util.loadtoml(args.config, defaults.defaults)                                   

    return args, conf                                                                      

def main():
    global args, config
    print(f"Running.   Version: {__version__}")
    args, config = process_cmdline()
    console = Console()

    #piddir = config.pidfile.parent
    #pidfile = config.pidfile.name

    signal.signal(signal.SIGHUP, reloadConfig)

    with PidFile("lmsdisplay"):
        backoff = 1
        while True:
            adjuster = util.ImageAdjuster(config.contrast_enhancement, config.color_saturation, config.image_size)
            try:
                ic("Looking for servers")
                servers = discovery.discover_lms()
                ic(servers)
                plr = getPlayer(servers, config.player)
                print(f"Monitoring: {plr}")

                disp = flaschen.Flaschen(config.display_host, config.display_port, config.image_size, config.image_size)

                mon = lms_monitor.PlayerMonitor(plr, event_q, adjuster)
                mon.start()

                backoff = 1

                handleEvents(disp, config.transitions)
                mon.close()
            except Exception:
                console.print_exception()
                print(f"Backing off for {backoff}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 120)

if __name__ == "__main__":
    main()
