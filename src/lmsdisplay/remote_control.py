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
import datetime as dt
import functools
import importlib.metadata
import importlib.resources
import re
import signal
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin
from queue import Queue
from enum import Enum, auto

from LMSTools import server, player

import configargparse
import requests
from pid import PidFile
from PIL import Image, ImageEnhance
from PIL.Image import Resampling
from rich.console import Console

from . import transitions, util, volume
from . import flaschen
from . import lms_monitor, discovery

#rich.traceback.install()
args: argparse.Namespace

def unix_timestamp():
    return f"{datetime.now().strftime("%H:%M")} |> "

from icecream import ic
ic.configureOutput(includeContext=True, prefix=unix_timestamp)
ic.disable()

idpat = re.compile(r" id:\s*(\d+)")
playpat = re.compile(r" mode:\s*(\w+)")
volpat = re.compile(r" volume:\s*(\d+)")

__version__ = "Unknown"

class PlayerNotFoundError(Exception):
    pass

event_q = Queue()

try:
    # Replace 'your-package-name' with the actual distribution name of your package
    __version__ = importlib.metadata.version("lmsdisplay")
except importlib.metadata.PackageNotFoundError:
    pass
    #print("Package not found or not installed.")

def process_cmdline():
    epilog = "Avaliable transitions:\n\n" + ", ".join(transitions.TransitionTypes)
    parser = configargparse.ArgumentParser("Display album art from Lyrion Music Server",
                                           epilog=epilog)
                                           # formatter_class=argparse.RawTextHelpFormatter)

    midnight = dt.time(0, 0)

    parser.suggest_on_error = True

    parser.add_argument("--config", dest="config", default=None, type=Path, help="Load configuration from file", is_config_file=True)

    # TODO: Remove the required on this later, so we can find any player that's playing.
    parser.add_argument( "--player", "-p", default=None, required=True, help="Player to monitor")

    parser.add_argument( "--login", type=str, default=None, help="Login name.  Leave blank if login not required")
    parser.add_argument( "--password", type=str, default=None, help="Password")

    parser.add_argument( "--displayhost", "-d", default="localhost", type=str, help="Display host")
    parser.add_argument( "--displayport", "-D", default=1337, type=int, help="Display port")

    parser.add_argument( "--lmsserver", "-l", default=None, type=str, help="Name of the LMS Server")
    parser.add_argument( "--lmsports", "-L", default=[9000, 9090], type=int, nargs=2,
                        help="Ports for the LMS Server.   Takes 2 arguments, the Host port and the CLI port")

    parser.add_argument( "--orientation", "-o", default=0, type=int, choices=[0, 90, 180, 270], help="Orientation of the display, in degrees")

    parser.add_argument("--transitions", "-t", nargs="*", metavar = "transition",
                        default=[], choices=transitions.TransitionTypes,
                        help = "A list of transitions to chose from")
    parser.add_argument("--imagesize", "-i", default=[64, 64], type=int, nargs=2, help="Dimension of the display")

    parser.add_argument("--dim", type=float, default=1.0, help="Dim the screen to this amount")
    parser.add_argument("--dimtimes", type=util.parsetime, default=[midnight, midnight], nargs=2, metavar="Time", help="Start dimming at this time")

    parser.add_argument("--contrast", "-c", default=5.0, type=float, help="Enhance contrast to this value.  Def: 1.0 (change nothing)")
    parser.add_argument("--color", "-C", default=1.0, type=float, help="Enhance color to this value.  Def: 1.0 (change nothing)")

    parser.add_argument("--delay", type=float, default=0.15, help="Delay between frames during transitions")
    parser.add_argument("--steps", type=int, default=10, help="Number of interim images in the transitions")

    parser.add_argument("--volume", action="store_true", default=False, help="Display the volume bar when volume changes")

    parser.add_argument("--pausedelay", "-P", type=int, default=0, help="Time to pause (in seconds) before switchiing to pause display")
    parser.add_argument("--pauselogo", action="store_true", default=False, help="Show Lyrion logo when paused")

    # parser.add_argument("--pidfile", type=Path, default=Path(f"/var/run/{Path(sys.argv[0]).name}"), help="File to store PID into. %(default)s")

    parser.add_argument("--version", action="version", version=__version__)

    args = parser.parse_args()

    return args


class ReloadEvent:
    pass

class KeyEvents(Enum):
    SKIP_FORWARD = auto()
    SKIP_BACK = auto()
    PLAY_PAUSE = auto()
    VOL_UP = auto()
    VOL_DOWN = auto()


def getEvent():
    while True:
        x = input()
        match x:
            case 'n':
                return KeyEvents.SKIP_FORWARD
            case 'p':
                return KeyEvents.SKIP_BACK
            case '':
                return KeyEvents.PLAY_PAUSE
            case 'u':
                return KeyEvents.VOL_UP
            case 'd':
                return KeyEvents.VOL_DOWN
            case _:
                print(f"Unknown key {x}")

reload = False

def reloadConfig(_signum, _frame):
    """ Receive a SIGHUP and reload the configuration file and command line. """
    global args, reload
    ic()
    args = process_cmdline()
    # clear the cache on getArt so we get changes to images immediately


def getPlayer(servers, name) -> player.LMSPlayer:
    for srv in servers:
        s = server.LMSServer(srv["host"], int(srv["port"]))
        if s:
            players = s.get_players()
            for plr in players:
                if name in (plr.ref ,plr.name):
                    return plr
    return None


def main():
    global args, __version__
    print(f"Running.   Version: {__version__}")
    args = process_cmdline()
    console = Console()

    #piddir = args.pidfile.parent
    #pidfile = args.pidfile.name

    signal.signal(signal.SIGHUP, reloadConfig)

    with PidFile("lmscontrol"):
        backoff = 1
        while True:
            try:
                servers = discovery.discover_lms()
                plr = getPlayer(servers, args.player)

                while not reload:
                    event = getEvent()
                    match event:
                        case KeyEvents.SKIP_FORWARD:
                            plr.__next__()
                        case KeyEvents.SKIP_BACK:
                            plr.prev()
                        case KeyEvents.PLAY_PAUSE:
                            plr.toggle()
                        case KeyEvents.VOL_UP:
                            plr.volume_up()
                        case KeyEvents.VOL_DOWN:
                            plr.volume_down()

            except Exception as e:
                console.print_exception()
                time.sleep(backoff)
                backoff = min(backoff * 2, 120)

if __name__ == "__main__":
    main()
