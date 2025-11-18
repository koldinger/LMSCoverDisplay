import argparse
import functools
import itertools
import logging
import re
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote
import sys
import pprint

import requests
import rich.traceback
from icecream import ic
from PIL import Image, ImageEnhance
from PIL.Image import Resampling
from telnetlib3 import telnetlib
import configargparse

import AnalogClockGenerator
import flaschen
import Transitions


def unixTimestamp():
    return f"{datetime.now().strftime("%H:%M")} |> "


ic.configureOutput(includeContext=True, prefix=unixTimestamp)
#ic.disable()

rich.traceback.install()

logger: logging.Logger

idpat = re.compile(r" id:\s*(\d+)")
playpat = re.compile(r" mode:\s*(\w+)")


def tt(string, query=False):
    if query:
        string = string + " ?"
    return bytes(string + "\r\n", "ascii")


def getLine(t):
    r = t.read_until(b"\n")
    return unquote(r)


def getPlayerID(t, name):
    count_cmd = "player count"
    r = doQuery(t, count_cmd)
    for i in range(int(r)):
        n = doQuery(t, f"player name {i}")
        if name == n.strip():
            playerID = doQuery(t, f"player id {i}")
            return playerID
    return None


def getPlayingID(t):
    count_cmd = "player count"
    r = doQuery(t, count_cmd)
    for i in range(int(r)):
        playerID = doQuery(t, f"player id {i}")
        # name = doQuery(t, f"player name {i}")
        # TODO: Parse the
        status = doQuery(t, f"{playerID} status 0 1")
        return playerID
    return None


def doQuery(t, query):
    t.write(tt(query, True))
    r = getLine(t)
    if not r.startswith(query):
        raise Exception(f"Invalid response: {r}")
    r = r.removeprefix(query).strip()
    return r


def handleStatus(t, f, playerID, transitions):
    lastimg = Image.new("RGB", (args.imagesize))
    subscribe_cmd = f"{playerID} status - 1 subscribe:30"
    clockgen = AnalogClockGenerator.AnalogClockGenerator(
        show_second_hand=False,
        hour_hand_color=(0, 0, 255, 255),
        minute_hand_color=(0, 255, 0, 255),
        origin_color=(255, 0, 0, 255),
    )

    # make it an infinite list
    transitions = itertools.cycle(transitions)

    # Start the subscription
    t.write(tt(subscribe_cmd))

    while True:
        line = getLine(t)
        ic(line)
        line = line.removeprefix(subscribe_cmd)
        playmatch = playpat.search(line)
        if playmatch:
            playing = playmatch.group(1)

        if playing == "play":
            idmatch = idpat.search(line)
            if idmatch:
                trackid = idmatch.group(1)
                art = getArt(int(trackid))
            else:
                trackid = None
                art = getCurrentArt(playerID)

            if art != lastimg and transitions:
                transition = Transitions.getTransition(next(transitions))
                for i in transition(lastimg, art, 10):
                    sendArt(f, i)
                    time.sleep(0.15)

            sendArt(f, art)
            lastimg = art
        elif args.clock:
            clk = clockgen.get_current_clock().resize(tuple(args.imagesize))
            sendArt(f, clk)


def sendArt(f, art):
    px = art.load()
    for x in range(art.width):
        for y in range(art.height):
            pixel = tuple(px[x, y])
            f.set(x, y, pixel)
    f.send()


def enhanceImage(img: Image.Image) -> Image.Image:
    if args.contrast != 1.0:
        img = ImageEnhance.Contrast(img).enhance(args.contrast)
    if args.color != 1.0:
        img = ImageEnhance.Color(img).enhance(args.color)
    return img

def getCurrentArt(playerID):
    url = f"http://{args.lmsserver}:{args.lmsports[0]}/music/current/cover.jpg?player={playerID}"
    resp = requests.get(url)
    img = Image.open(BytesIO(resp.content))
    rimg = img.resize(tuple(args.imagesize), Resampling.BILINEAR)
    # rimg.save(f"{trackID}.jpg")
    return rimg


@functools.lru_cache(maxsize=128)
def getArt(trackID):
    url = f"http://{args.lmsserver}:{args.lmsports[0]}/music/{trackID}/cover.jpg"
    resp = requests.get(url)
    img = Image.open(BytesIO(resp.content))
    rimg = img.resize(tuple(args.imagesize), Resampling.BILINEAR)
    rimg = enhanceImage(rimg)

    # rimg.save(f"{trackID}.jpg")
    return rimg

def process_cmdline():
    epilog = "Avaliable transitions:\n\n" + ", ".join(Transitions.TransitionTypes)
    parser = configargparse.ArgumentParser("Display album art from Lyrion Music Server",
                                           epilog=epilog)
                                           # formatter_class=argparse.RawTextHelpFormatter)

    # TODO: Remove the required on this later, so we can find any player that's playing.
    parser.add_argument("--config", dest="config", default=None, type=Path, help="Load configuration from file", is_config_file=True)

    parser.add_argument( "--player", "-p", default=None, required=True, help="Player to monitor")

    parser.add_argument( "--displayhost", "-d", default="localhost", type=str, help="Display host")
    parser.add_argument( "--displayport", "-D", default=1337, type=int, help="Display port")

    parser.add_argument( "--lmsserver", "-l", default="localhost", type=str, help="Name of the LMS Server")
    parser.add_argument( "--lmsports", "-L", default=[9000, 9090], type=int, nargs=2,
                        help="Ports for the LMS Server.   Takes 2 arguments, the Host port and the CLI port")

    parser.add_argument("--transitions", "-t", nargs="+", metavar = "Transition", default=[Transitions.TransitionTypes.none], choices=Transitions.TransitionTypes)
    parser.add_argument("--imagesize", "-i", default=[64, 64], type=int, nargs=2,
                        help="Dimension of the display")

    parser.add_argument("--contrast", "-c", default=5.0, type=float, help="Enhance contrast to this value.  Def: 1.0 (change nothing)")
    parser.add_argument("--color", "-C", default=1.0, type=float, help="Enhance color to this value.  Def: 1.0 (change nothing)")

    parser.add_argument("--clock",      type=bool, const=True, nargs="?", default=False, help="Show Clock if not playing")

    args = parser.parse_args()

    return args

args: argparse.Namespace

def main():
    global args, logger
    args = process_cmdline()
    t = telnetlib.Telnet()
    backoff = 1

    logging.basicConfig(level=logging.INFO)

    while True:
        try:
            f = flaschen.Flaschen(args.displayhost, args.displayport, args.imagesize[0], args.imagesize[1])
            t.open(args.lmsserver, args.lmsports[1])

            version = doQuery(t, "version")
            backoff = 1

            playerID = getPlayerID(t, args.player) if args.player else getPlayingID(t)

            handleStatus(t, f, playerID, args.transitions)
        except Exception as e:
            ic(e)
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)


if __name__ == "__main__":
    main()
