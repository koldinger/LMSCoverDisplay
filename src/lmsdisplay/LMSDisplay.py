import argparse
import datetime as dt
import functools
import logging
import random
import re
import signal
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote
import importlib.resources

import configargparse
import requests
import rich.traceback
from icecream import ic
from pid import PidFile
from PIL import Image, ImageEnhance
from PIL.Image import Resampling
from rich.console import Console
from telnetlib3 import telnetlib

from . import AnalogClockGenerator, Transitions, flaschen, util

rich.traceback.install()

args: argparse.Namespace

def unix_timestamp():
    return f"{datetime.now().strftime("%H:%M")} |> "

ic.configureOutput(includeContext=True, prefix=unix_timestamp)
ic.disable()

logger: logging.Logger

idpat = re.compile(r" id:\s*(\d+)")
playpat = re.compile(r" mode:\s*(\w+)")

def command_string(string, query=False):
    if query:
        string = string + " ?"
    return bytes(string + "\r\n", "ascii")


def getLine(tn_session):
    return unquote(tn_session.read_until(b"\n")).strip()


def getPlayerID(tn_session, name):
    count_cmd = "player count"
    r = doQuery(tn_session, count_cmd)
    for i in range(int(r)):
        n = doQuery(tn_session, f"player name {i}")
        if name == n.strip():
            playerID = doQuery(tn_session, f"player id {i}")
            return playerID
    return None


def getPlayingID(tn_session):
    count_cmd = "player count"
    line = doQuery(tn_session, count_cmd)
    for i in range(int(line)):
        playerID = doQuery(tn_session, f"player id {i}")
        # name = doQuery(t, f"player name {i}")
        # TODO: Parse the line
        # status = doQuery(tn_session, f"{playerID} status 0 1")
        return playerID
    return None


def doQuery(tn_session, query):
    """ Take a query, send it to the LMS server, and grab the response. """
    tn_session.write(command_string(query, True))
    line = getLine(tn_session)
    if not line.startswith(query):
        raise ValueError(f"Unexpected response: {line}")
    line = line.removeprefix(query).strip()
    ic(query, line)
    return line


def handleStatus(t, f, playerID, transitions):
    lastimg = Image.new("RGB", (args.imagesize))
    subscribe_cmd = f"{playerID} status - 1 subscribe:30"
    clockgen = AnalogClockGenerator.AnalogClockGenerator(
        show_second_hand=False,
        hour_hand_color=(0, 0, 255, 255),
        minute_hand_color=(0, 255, 0, 255),
        origin_color=(255, 0, 0, 255),
    )

    # Start the subscription
    t.write(command_string(subscribe_cmd))

    blank = Image.new("RGB", tuple(args.imagesize), color=(0, 0, 0))
    #lyrionlogo = getInternalArt("logo.png")
    lyrionlogo = blank

    # Setup as if we're paused at the start.
    playing = False
    pausestart = datetime.now()
    first_image = True

    while True:
        line = getLine(t)
        ic(line)
        line = line.removeprefix(subscribe_cmd)

        # Grab the current playing status from the stream
        playmatch = playpat.search(line)
        mode = playmatch.group(1) if playmatch else "unknown"

        match mode:
            case "play":
                playing = True
                idmatch = idpat.search(line)
                if idmatch:
                    trackid = idmatch.group(1)
                    art = getArt(int(trackid))
                else:
                    trackid = None
                    art = getCurrentArt(playerID)


                if art != lastimg:
                    sendTransition(f, art, lastimg, Transitions.getTransition(random.choice(transitions)))
                else:
                    sendArt(f, art)

                lastimg = art
            case "pause":
                if playing:
                    # If we just switched to pause timing, record the time we paused (roughly)
                    pausestart = datetime.now()
                    first_image = True
                playing = False
                pause_img = blank if args.pauselogo else lyrionlogo
                ic(pause_img)

                if (datetime.now() - pausestart).seconds >= args.pausedelay:
                    # If we're past the pausedelay, switch to the pause display
                    if args.clock:
                        clk = clockgen.get_current_clock().resize(tuple(args.imagesize)).convert("RGB")

                        if first_image:
                            sendTransition(f, clk, lastimg, Transitions.getTransition(random.choice(transitions)))
                            first_image = False
                        else:
                            sendArt(f, clk)
                        lastimg = clk
                    else:
                        if lastimg != blank:
                            sendTransition(f, pause_img, lastimg, Transitions.getTransition(random.choice(transitions)))
                        else:
                            sendArt(f, pause_img)
                        lastimg = pause_img
                else:
                    # Else, still in the pause delay, just blast the last image
                    sendArt(f, lastimg)
            case _:
                print(line)


@functools.cache
def dimImage(image):
    """ Dim an image. """
    image = ImageEnhance.Brightness(image).enhance(args.dim)
    return image

def sendArt(f, art):
    """
    Send art to the display, dimming it if necessary.

    Sent via the flaschen-taschen library, but sent to via UDP to port 1337 (usually).
    """
    if args.dim is not None and util.betweentimes(datetime.now().time(), *args.dimtimes):
        art = dimImage(art)
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

def getCurrentArt(playerID):
    """
    Get the art for the currently playing track.

    Useful for when you're receiving from a streaming service.
    """
    url = f"http://{args.lmsserver}:{args.lmsports[0]}/music/current/cover.jpg?player={playerID}"
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
def getArt(trackID: str) -> Image.Image:
    """ Get the art for a track ID. """
    url = f"http://{args.lmsserver}:{args.lmsports[0]}/music/{trackID}/cover.jpg"
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
    ic(fname)
    return Image.open(fname).convert("RGB").resize(tuple(args.imagesize))


def process_cmdline():
    epilog = "Avaliable transitions:\n\n" + ", ".join(Transitions.TransitionTypes)
    parser = configargparse.ArgumentParser("Display album art from Lyrion Music Server",
                                           epilog=epilog)
                                           # formatter_class=argparse.RawTextHelpFormatter)

    midnight = dt.time(0, 0)

    parser.add_argument("--config", dest="config", default=None, type=Path, help="Load configuration from file", is_config_file=True)

    # TODO: Remove the required on this later, so we can find any player that's playing.
    parser.add_argument( "--player", "-p", default=None, required=True, help="Player to monitor")

    parser.add_argument( "--displayhost", "-d", default="localhost", type=str, help="Display host")
    parser.add_argument( "--displayport", "-D", default=1337, type=int, help="Display port")

    parser.add_argument( "--lmsserver", "-l", default="localhost", type=str, help="Name of the LMS Server")
    parser.add_argument( "--lmsports", "-L", default=[9000, 9090], type=int, nargs=2,
                        help="Ports for the LMS Server.   Takes 2 arguments, the Host port and the CLI port")

    parser.add_argument("--transitions", "-t", nargs="+", metavar = "Transition",
                        default=[Transitions.TransitionTypes.Instant], choices=Transitions.TransitionTypes,
                        help = "A list of transitions to chose from")
    parser.add_argument("--imagesize", "-i", default=[64, 64], type=int, nargs=2, help="Dimension of the display")

    parser.add_argument("--dim", type=float, default=1.0, help="Dim the screen to this amount")
    parser.add_argument("--dimtimes", type=util.parsetime, default=[midnight, midnight], nargs=2, help="Start dimming at this time")

    parser.add_argument("--contrast", "-c", default=5.0, type=float, help="Enhance contrast to this value.  Def: 1.0 (change nothing)")
    parser.add_argument("--color", "-C", default=1.0, type=float, help="Enhance color to this value.  Def: 1.0 (change nothing)")

    parser.add_argument("--delay", type=float, default=0.15, help="Delay between frames during transitions")
    parser.add_argument("--steps", type=int, default=10, help="Number of interim images in the transitions")

    parser.add_argument("--pausedelay", "-P", type=int, default=0, help="Time to pause (in seconds) before switchiing to pause display")
    parser.add_argument("--clock",  action="store_true", default=False, help="Show Clock if paused")
    parser.add_argument("--pauselogo", action="store_true", default=False, help="Show Lyrion logo when paused")

    parser.add_argument("--pidfile", type=Path, default=None, help="File to store PID into")

    args = parser.parse_args()

    return args


def reloadConfig(signum, frame):
    """ Receive a SIGHUP and reload the configuration file and command line. """
    global args
    ic(signum, frame)
    args = process_cmdline()
    # clear the cache on getArt so we get changes to images immediately
    getArt.cache_clear()

def main():
    global args, logger
    args = process_cmdline()
    console = Console()

    t = telnetlib.Telnet()
    backoff = 1

    signal.signal(signal.SIGHUP, reloadConfig)

    logging.basicConfig(level=logging.INFO)

    pidfile = None
    piddir = None
    if args.pidfile:
        if args.pidfile.is_dir():
            piddir = args.pidfile
        else:
            piddir = args.pidfile.parent
            pidfile = args.pidfile.name

    with PidFile(piddir=piddir, pidname=pidfile) as p:
        ic(p.filename)
        while True:
            try:
                f = flaschen.Flaschen(args.displayhost, args.displayport, args.imagesize[0], args.imagesize[1])
                t.open(args.lmsserver, args.lmsports[1])

                version = doQuery(t, "version")
                ic(version)
                backoff = 1

                playerID = getPlayerID(t, args.player) if args.player else getPlayingID(t)
                ic(playerID)

                handleStatus(t, f, playerID, args.transitions)
            except Exception as e:
                ic(e)
                console.print_exception()
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)


if __name__ == "__main__":
    main()
