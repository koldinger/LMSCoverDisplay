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
import itertools
import random
import signal
import time
from datetime import datetime, timedelta
from queue import Queue, Empty
from pathlib import Path

import rich.traceback
import nmcli
from pid import PidFile
from PIL import Image, ImageEnhance
from rich.console import Console
from LMSTools import server

from . import discovery, lms_monitor, transitions, util, volume, defaults, events, display, qrcodes

rich.traceback.install()
args: argparse.Namespace

monitor: lms_monitor.PlayerMonitor | None = None
reloaded: bool = False

from icecream import ic
ic.configureOutput(includeContext=True)
# ic.disable()

__version__ = "Unknown"
with contextlib.suppress(importlib.metadata.PackageNotFoundError):
    __version__ = importlib.metadata.version("lmsdisplay")


class PlayerNotFoundError(Exception):
    pass


event_q = Queue()

TIMEOUT_DEF = 20    # 20 second timeout.   Screen should flush at 30

def contrasting_color(art: Image.Image) -> tuple[int, int, int, int]:
    try:
        # Get the averoge color of the current screen.
        # Do this by resizing the picture to 1 pixel, and grabbing the color
        small = art.resize((1, 1), resample=Image.Resampling.LANCZOS).convert("RGB")
        r, g, b = small.getpixel((0, 0))
        # Compute the contrasting color, based on the luma
        luma = 0.299*r + 0.587*g + 0.114*b
        color = (255, 255, 255, 200) if luma <= 128 else (0, 0, 0, 200)
    except:
        color = (255, 255, 255, 200)
    return color


def handleEvents(disp, trans: list[transitions.TransitionTypes]) -> None:
    lastimg = Image.new("RGB", (config.image_size, config.image_size))
    lastvol = 0

    blank = Image.new("RGB", (config.image_size, config.image_size), color=(0, 0, 0))

    trans = trans or list(transitions.TransitionTypes)

    # Setup as if we're paused at the start.
    playing = False
    pause_delta = timedelta(seconds=config.pause_delay)
    cleartime = None

    timeout = TIMEOUT_DEF

    while True:
        event = None            # Clear the previous event
        try:
            event = event_q.get(timeout = timeout)
        except Empty:
            if playing:
                sendArt(disp, lastimg)
            elif cleartime and datetime.now() >= cleartime:
                sendTransition(display, blank, lastimg, transitions.getTransition(random.choice(trans)))
                timeout = TIMEOUT_DEF
            continue

        # Grab the current playing status from the stream
        overlay = None

        # Continue on if no event was discovered
        if not event:
            continue

        # Handle a reload event and break out of the loop
        if type(event) is ReloadEvent:
            event = None
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
                    sendTransition(disp, art, lastimg, transitions.getTransition(random.choice(trans)))
                else:
                    sendArt(disp, art, overlay=overlay)
                lastimg = art

            case events.EventType.PAUSE | events.EventType.STOP:
                if playing and config.pause_delay:
                    pausestart = datetime.now()
                    cleartime = pausestart + pause_delta
                    timeout = min(config.pause_delay, TIMEOUT_DEF)

                playing = False
                pause_img = blank

                ic(cleartime, datetime.now())
                if (config.pause_delay == 0) or (cleartime and datetime.now() >= cleartime):
                    # If we're past the pause_delay, switch to the pause display
                    ic("Pause clear 2")
                    if lastimg != blank:
                        sendTransition(display, pause_img, lastimg, transitions.getTransition(random.choice(trans)))
                    # else:
                    #    sendArt(display, pause_img)
                    lastimg = pause_img
                    cleartime = None
                    timeout = TIMEOUT_DEF
                else:
                    # Else, still in the pause delay, just blast the last image
                    sendArt(disp, lastimg)
            case _:
                print(event)


def dimImage(image):
    """ Dim an image. """
    if config.dim_at_night:
        image = ImageEnhance.Brightness(image).enhance(config.dimmed_brightness)
    return image


def sendArt(disp, art, overlay=None):
    """
    Send art to the display, dimming it if necessary.

    If an overlay image is presented, it will be overlaid over the artwork
    before sending.
    """
    if overlay:
        overlay = overlay.resize(art.size)
        art = art.copy()
        art.paste(overlay, (0, 0), overlay)

    if config.dim_at_night and util.betweentimes(datetime.now().time(), util.parsetime(config.dim_start_time), util.parsetime(config.dim_end_time)):
        art = dimImage(art)

    if config.orientation:
        art = art.rotate(config.orientation)

    ic(disp, art)
    disp.send_image(art)


def sendTransition(f, art, lastimg, transition, overlay=None):
    for i in transition(lastimg, art, config.transition_frames):
        sendArt(f, i, overlay)
        time.sleep(config.frame_delay)


class ReloadEvent:
    pass


def reloadConfig(_signum, _frame):
    """ Receive a SIGHUP and reload the configuration file and command line. """
    global args, config, reloaded
    ic()
    args, config = process_cmdline()
    # clear the cache on getArt so we get changes to images immediately
    if monitor:
        monitor.clear_art_cache()

    reloaded = True
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


WIFISELECT_CONN = "wifiselect-hotspot"
WIFI_INTERFACE = "wlan0"
SETUP_SSID = "LMSCoverSetup"

class RotatingDisplay:
    def __init__(self, display, images):
        ic(images, len(images))
        self.images = itertools.cycle(images)
        self.next = datetime.now()
        self.last_image = None
        self.display = display

    def update(self):
        now = datetime.now()
        if now > self.next:
            art, delay = next(self.images)
            ic(art, delay)

            if self.last_image and art != self.last_image:
                ic()
                sendTransition(self.display, art, self.last_image, transitions.TransitionTypes.Fade.function)
            else:
                sendArt(self.display, art)

            self.last_image = art
            self.next = datetime.now() + timedelta(seconds=delay)
            ic(self.next)
        else:
            sendArt(self.display, self.last_image)

def check_connection(dis):
    nmcli.disable_use_sudo()
    if not args.check_conn:
        return

    qr = qrcodes.generate_wifi_qrcode(SETUP_SSID, config.image_size)
    logo = util.get_internal_art("wifi.jpg").resize((config.image_size, config.image_size), resample=Image.Resampling.NEAREST)
    ic(logo)

    rd = RotatingDisplay(dis, [(qr, 10), (logo, 5)])
    while True:
        conns = nmcli.connection.show_all(active=True)
        # Find the active wifi connection
        for c in conns:
            if c.conn_type == "wifi" and c.name != WIFISELECT_CONN:
                ic(c.name, c.conn_type)
                return

        time.sleep(1)
        rd.update()


def check_player(display):
    if not args.check_player:
        return

    qr = qrcodes.generate_config_qrcode(WIFI_INTERFACE, config.image_size)
    logo =  util.get_internal_art("configure.jpg").resize((config.image_size, config.image_size), resample=Image.Resampling.NEAREST)

    rd = RotatingDisplay(display, [(qr, 10), (logo, 5)])
    ic(config.player)
    while not config.player:
        time.sleep(1)
        rd.update()

def process_cmdline():
    parser = argparse.ArgumentParser("Display album art from Lyrion Music Server")
                                           # formatter_class=argparse.RawTextHelpFormatter)
    parser.suggest_on_error = True

    parser.add_argument("--config", dest="config", default=None, type=Path, required=True, help="Load configuration from file")                                                     
    parser.add_argument("--check-conn", action=argparse.BooleanOptionalAction, default=True, help="Check the connection")
    parser.add_argument("--check-player", action=argparse.BooleanOptionalAction, default=True, help="Check the player configuration")
    parser.add_argument("--version", "-v", action="version", version=__version__)

    args = parser.parse_args()

    conf = util.loadtoml(args.config, defaults.defaults)

    return args, conf


def init_display():
    x = y = config.image_size

    match config.driver:
        case "flaschen_taschen":
            disp = display.FlashenDisplay(config.display_host, config.display_port, x, y)
        case "internal":
            disp = display.InternalDisplay(x, y, config.gpio_slowdown, config.max_refresh_rate)
        case _:
            raise ValueError(config.driver)
    return disp


def main():
    global args, config, monitor
    print(f"Running.   Version: {__version__}")
    args, config = process_cmdline()
    console = Console()

    signal.signal(signal.SIGHUP, reloadConfig)

    with PidFile("lmsdisplay"):
        backoff = 1
        while True:
            disp = init_display()
            adjuster = util.ImageAdjuster(config.contrast_enhancement, config.color_saturation, config.image_size)

            check_connection(disp)
            check_player(disp)

            try:
                ic("Looking for servers")
                servers = discovery.discover_lms()
                ic(servers)
                plr = getPlayer(servers, config.player)
                print(f"Monitoring: {plr}")

                monitor = lms_monitor.PlayerMonitor(plr, event_q, adjuster)
                monitor.start()

                backoff = 1

                handleEvents(disp, config.transitions)
                monitor.close()
            except Exception:
                console.print_exception()
                print(f"Backing off for {backoff}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 120)


if __name__ == "__main__":
    main()
