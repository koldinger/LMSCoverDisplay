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
import signal
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from queue import Queue
from typing import Optional

import nmcli
import rich.traceback
import watchfiles
from pid import PidFile
from PIL import Image
from rich.console import Console

from . import (defaults, discovery, display, events, lms_monitor, qrcodes, statemachine, transitions, util)

rich.traceback.install()
args: argparse.Namespace

monitor: Optional[lms_monitor.PlayerMonitor] = None

from icecream import ic

ic.configureOutput(includeContext=True)
# ic.disable()

__version__ = "Unknown"
with contextlib.suppress(importlib.metadata.PackageNotFoundError):
    __version__ = importlib.metadata.version("lmsdisplay")

event_q = Queue()

TIMEOUT_DEF = 20    # 20 second timeout.   Screen should flush at 30

def handle_signal(_signum, _frame):
    ic()
    reload_config()

def reload_config():
    """ Receive a SIGHUP and reload the configuration file and command line. """
    global args, config
    print("Reloading Configuration")
    args, config = process_cmdline()
    # clear the cache on getArt so we get changes to images immediately
    if monitor:
        monitor.clear_art_cache()

    # Stop the statemachine.
    event_q.put(events.PlayEvent(events.EventType.END))


def watch_config(configfile):
    c = Path(configfile).absolute()

    def filter_for_config(change: watchfiles.Change, path: str) -> bool:
        return Path(path) == c and change in [watchfiles.Change.added, watchfiles.Change.modified]

    # watch the parent directory because if the config file is "changed", it may Automatically
    # be deleted, and then readded.   This causes subesquent changes to be lost
    for _ in watchfiles.watch(c.parent, watch_filter=filter_for_config):
        reload_config()

WIFISELECT_CONN_NAME = "wifiselect-hotspot"
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

            if self.last_image and art != self.last_image:
                self.display.transition(self.last_image, art, transitions.TransitionTypes.Fade)
            else:
                self.display.show_artwork(art)

            self.last_image = art
            self.next = datetime.now() + timedelta(seconds=delay)
        else:
            # self.display.show_artwork(self.last_image)
            self.display.refresh()

def check_connection(dis):
    """
    Check to see if we're running on the wifiselect hotspot.

    If the current connection is the wifiselect hotspot, run a rotating display
    that shows a WiFi QRCode for the hotspot, and an image of the WiFi logo.
    """
    nmcli.disable_use_sudo()
    if not args.check_conn:
        return

    qr = qrcodes.generate_wifi_qrcode(SETUP_SSID, config.image_size)
    logo = util.get_internal_art("wifi.jpg").resize((config.image_size, config.image_size), resample=Image.Resampling.NEAREST)

    rd = RotatingDisplay(dis, [(qr, 10), (logo, 5)])
    while True:
        conns = nmcli.connection.show_all(active=True)
        # Find the active wifi connection
        for c in conns:
            if c.conn_type == "wifi" and c.name != WIFISELECT_CONN_NAME:
                ic(c.name, c.conn_type)
                return

        time.sleep(1)
        rd.update()


def check_player(display):
    """
    Check to see if we're in need of configuration.

    Configuration need is assumed if either the player has not been specied, or 
    the specified player cannot be found.
    """
    if not args.check_player:
        return

    qr = qrcodes.generate_config_qrcode(WIFI_INTERFACE, config.image_size)
    logo =  util.get_internal_art("configure.jpg").resize((config.image_size, config.image_size), resample=Image.Resampling.NEAREST)

    rd = RotatingDisplay(display, [(qr, 10), (logo, 5)])

    while True:
        print(config.player)
        with contextlib.suppress(util.PlayerNotFoundError):
            servers = discovery.discover_lms()
            if servers and config.player:
                print(config.player)
                player = util.get_player(servers, config.player)
                if player:
                    return

        time.sleep(1)
        rd.update()
        servers = discovery.discover_lms()

def process_cmdline():
    parser = argparse.ArgumentParser("Display album art from Lyrion Music Server")
                                           # formatter_class=argparse.RawTextHelpFormatter)
    parser.suggest_on_error = True

    parser.add_argument("--config", dest="config", default=None, type=Path, required=True, help="Load configuration from file")
    parser.add_argument("--check-conn", action=argparse.BooleanOptionalAction, default=True, help="Check the connection")
    parser.add_argument("--check-player", action=argparse.BooleanOptionalAction, default=True, help="Check the player configuration")
    parser.add_argument("--watch-config", action=argparse.BooleanOptionalAction, default=True, help="Automatically watch the config file for changes")
    parser.add_argument("--version", "-v", action="version", version=__version__)

    args = parser.parse_args()

    conf = util.loadtoml(args.config, defaults.defaults)

    return args, conf


def init_display():
    x = y = config.image_size
    trans_list = [transitions.TransitionTypes(x) for x in config.transitions]
    return display.FlashenDisplay(trans_list, config.transition_frames, config.frame_delay, config.display_host, config.display_port, x, y, config.orientation)


def main():
    global args, config, monitor
    print(f"Running.   Version: {__version__}")
    args, config = process_cmdline()
    console = Console()

    signal.signal(signal.SIGHUP, handle_signal)
    if args.watch_config:
        threading.Thread(target=watch_config, args=(args.config,), daemon=True).start()

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
                plr = util.get_player(servers, config.player)
                print(f"Monitoring: {plr}")

                sm = statemachine.StateMachine(config, disp, plr, adjuster, event_q)
                monitor = lms_monitor.PlayerMonitor(plr, sm.queue, adjuster)
                monitor.start()

                backoff = 1

                sm.run()
                monitor.close()
            except Exception:
                console.print_exception()
                print(f"Backing off for {backoff}")
                time.sleep(backoff)
                backoff = min(backoff * 2, 120)


if __name__ == "__main__":
    main()
