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
import random
import re
import signal
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin
from queue import Queue

from LMSTools import server

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

def handleEvents(display, playerID, trans, baseUrl):
    lastimg = Image.new("RGB", (args.imagesize))
    lastvol = 0

    blank = Image.new("RGB", tuple(args.imagesize), color=(0, 0, 0))
    #lyrionlogo = getInternalArt("logo.png")
    lyrionlogo = blank

    if not trans:
        trans = list(transitions.TransitionTypes)

    # Setup as if we're paused at the start.
    playing = False
    pausestart = datetime.now()

    while True:
        event = event_q.get()
        ic(event)

        # Grab the current playing status from the stream
        overlay = None

        # Handle a reload event and break out of the loop
        if type(event) is ReloadEvent:
            break

        match event.mode:
            case "play":
                playing = True
                if event.song:
                    trackid = event.song
                    art = getArt(int(trackid), baseUrl)
                else:
                    trackid = None
                    art = getCurrentArt(playerID, baseUrl)

                if args.volume:
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

            case "pause" | "stop":
                if playing:
                    # If we just switched to pause timing, record the time we paused (roughly)
                    pausestart = datetime.now()
                playing = False
                pause_img = blank if args.pauselogo else lyrionlogo

                if (datetime.now() - pausestart).seconds >= args.pausedelay:
                    # If we're past the pausedelay, switch to the pause display
                    if lastimg != blank:
                        sendTransition(display, pause_img, lastimg, transitions.getTransition(random.choice(trans)))
                    #else:
                    #    sendArt(display, pause_img)
                    lastimg = pause_img
                else:
                    # Else, still in the pause delay, just blast the last image
                    sendArt(display, lastimg)
            case _:
                print(event)


def dimImage(image):
    """ Dim an image. """
    image = ImageEnhance.Brightness(image).enhance(args.dim)
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

    if args.dim is not None and util.betweentimes(datetime.now().time(), *args.dimtimes):
        art = dimImage(art)

    if args.orientation:
        art = art.rotate(args.orientation)

    px = art.load()
    for x in range(art.width):
        for y in range(art.height):
            pixel = tuple(px[x, y])
            f.set(x, y, pixel)
    f.send()

def sendTransition(f, art, lastimg, transition):
    for i in transition(lastimg, art, args.steps):
        sendArt(f, i)
        time.sleep(args.delay)

def enhanceImage(img: Image.Image) -> Image.Image:
    """ Pump up the contrast and color if requested. """
    if args.contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(args.contrast)
    if args.color != 1.0:
        img = ImageEnhance.Color(img).enhance(args.color)
    return img

def getCurrentArt(playerID, baseUrl):
    """
    Get the art for the currently playing track.

    Useful for when you're receiving from a streaming service.
    """
    url = urljoin(baseUrl, f"music/current/cover.jpg?player={playerID}")
    resp = requests.get(url, timeout=(5, 10))
    if resp.status_code == requests.codes["ok"]:
        img = Image.open(BytesIO(resp.content))
        rimg = img.resize(tuple(args.imagesize), Resampling.BILINEAR)
        rimg = enhanceImage(rimg)
    else:
        rimg = getInternalArt("questionmark.jpg")

    if rimg.mode not in ["RGB", "RGBA"]:
        rimg = rimg.convert("RGB")
    return rimg


@functools.lru_cache(maxsize=128)
def getArt(trackID: str, baseUrl):
    """ Get the art for a track ID. """
    url = urljoin(baseUrl, f"music/{trackID}/cover.jpg")
    resp = requests.get(url, timeout=(5, 10))
    if resp.status_code == requests.codes["ok"]:
        img = Image.open(BytesIO(resp.content))
        rimg = img.resize(tuple(args.imagesize), Resampling.BILINEAR)
        rimg = enhanceImage(rimg)
    else:
        rimg = getInternalArt("questionmark.jpg")

    if rimg.mode not in ["RGB", "RGBA"]:
        rimg = rimg.convert("RGB")
    return rimg

@functools.cache
def getInternalArt(name: str) -> Image.Image:
    """ Retrieve artwork from the internal resource files. """
    fname = importlib.resources.files().joinpath("art", name).read_bytes()
    return Image.open(fname).convert("RGB").resize(tuple(args.imagesize))

def process_cmdline():
    epilog = "Avaliable transitions:\n\n" + ", ".join(transitions.TransitionTypes)
    parser = configargparse.ArgumentParser("Display album art from Lyrion Music Server",
                                           epilog=epilog)
                                           # formatter_class=argparse.RawTextHelpFormatter)

    midnight = dt.time(0, 0)

    parser.suggest_on_error = True

    parser.add_argument("--config", dest="config", default=None, type=Path, help="Load configuration from file", is_config_file=True)

    # TODO: Remove the required on this later, so we can find any player that's playing.
    parser.add_argument( "--player", "-p", default=None, help="Player to monitor")

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

def reloadConfig(_signum, _frame):
    """ Receive a SIGHUP and reload the configuration file and command line. """
    global args
    ic()
    args = process_cmdline()
    # clear the cache on getArt so we get changes to images immediately
    getArt.cache_clear()
    event_q.put(ReloadEvent())

def getPlayer(servers, name):
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

    with PidFile("lmsdisplay"):
        backoff = 1
        while True:
            try:
                servers = discovery.discover_lms()
                plr = getPlayer(servers, args.player)
                print(f"Monitoring: {plr}")
                if not (plr):
                    raise PlayerNotFoundError(args.player)

                base_url = f"http://{plr.server.host}:{plr.server.port}"

                disp = flaschen.Flaschen(args.displayhost, args.displayport, args.imagesize[0], args.imagesize[1])

                mon = lms_monitor.PlayerMonitor(plr.ref, plr.server.host, event_q, args.login, args.password)
                mon.start()

                backoff = 1

                handleEvents(disp, args.player, args.transitions, base_url)
                mon.close()
            except Exception as e:
                console.print_exception()
                time.sleep(backoff)
                backoff = min(backoff * 2, 120)

if __name__ == "__main__":
    main()
