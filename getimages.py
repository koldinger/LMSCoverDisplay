import argparse
import re
from functools import lru_cache
from io import BytesIO
from urllib.parse import unquote

import requests
from icecream import ic
from PIL import Image
import rich.traceback
from telnetlib3 import telnetlib
import time
from enum import StrEnum, auto

import Transitions

import flaschen

import AnalogClockGenerator

ic.configureOutput(includeContext=True)
ic.disable()

rich.traceback.install()


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
        n = doQuery(t, f"player name {i}")
        if name == n.strip():
            playerID = doQuery(t, f"player id {i}")
            return playerID
    return None

def doQuery(t, query):
    t.write(tt(query, True))
    r = getLine(t)
    if not r.startswith(query):
        raise Exception(f"Invalid response: {r}")
    r = r.removeprefix(query).strip()
    return r

def handleStatus(t, f, playerID):
    lastimg =  Image.new("RGB", (args.imagesize))
    idpat = re.compile(r" id:\s*(\d+)")
    playpat = re.compile(r" mode:\s*(\w+)")
    subscribe_cmd = f"{playerID} status - 1 subscribe:30"
    clockgen = AnalogClockGenerator.AnalogClockGenerator(show_second_hand=False, hour_hand_color=(0,0,255,255), minute_hand_color=(0,255,0,255), origin_color=(255,0,0,255))

    t.write(tt(subscribe_cmd))
    while True:
        line = getLine(t)
        line = line.removeprefix(subscribe_cmd)
        playmatch = playpat.search(line)
        if playmatch:
            playing = playmatch.group(1)

        if playing == 'play':
            # ic(line)
            idmatch = idpat.search(line)
            if idmatch:
                trackid = idmatch.group(1)
                art = getArt(int(trackid))
            else:
                trackid = None
                art = getCurrentArt(playerID)

            if art != lastimg and args.transition:
                transition = Transitions.getTransition(args.transition)
                for i in transition(lastimg, art, 10):
                    sendArt(f, i)
                    time.sleep(0.1)

            sendArt(f, art)
            lastimg = art
        elif args.clock:
            clk = clockgen.get_current_clock().resize(tuple(args.imagesize))
            sendArt(f, clk)


def sendArt(f, art):
    ic(art)
    px = art.load()
    for x in range(64):
        for y in range(64):
            pixel = tuple(px[x, y])
            f.set(x, y, pixel)
    f.send()


def getCurrentArt(playerID):
    url = f"http://{args.lmsserver}:{args.lmsports[0]}/music/current/cover.jpg?player={playerID}"
    resp = requests.get(url)
    img = Image.open(BytesIO(resp.content))
    rimg = img.resize(tuple(args.imagesize))
    #rimg.save(f"{trackID}.jpg")
    return rimg

@lru_cache(maxsize = 128)
def getArt(trackID):
    url = f"http://{args.lmsserver}:{args.lmsports[0]}/music/{trackID}/cover.jpg"
    #ic(url)
    resp = requests.get(url)
    img = Image.open(BytesIO(resp.content))
    rimg = img.resize(tuple(args.imagesize))
    #rimg.save(f"{trackID}.jpg")
    return rimg

def process_cmdline():
    parser = argparse.ArgumentParser()

    parser.add_argument("--player", "-p", default=None, help="Player to monitor")

    parser.add_argument("--displayhost", "-d", default="localhost", type=str, help="Display host")
    parser.add_argument("--displayport", "-D", default=1337, type=int, help="Display port")

    parser.add_argument("--lmsserver", "-l", default="localhost", type=str, help="Name of the LMS Server")
    parser.add_argument("--lmsports", "-L", default=[9000, 9090], type=int, nargs=2, help="Ports for the LMS Server.   Takes 2 arguments, the Host port and the CLI port")

    parser.add_argument("--transition", "-t", default=Transitions.TransitionTypes.none, choices=Transitions.TransitionTypes)
    parser.add_argument("--imagesize", "-i", default=[64, 64], type=int, nargs=2, help="Dimension of the display")
    parser.add_argument("--clock", "-c", type=bool, const=True, nargs="?", default=False, help="Show Clock if not playing")
    return parser.parse_args()

args: argparse.Namespace

def main():
    global  args
    args = process_cmdline()
    ic(args)
    t = telnetlib.Telnet()
    f = flaschen.Flaschen(args.displayhost, args.displayport, args.imagesize[0], args.imagesize[1])

    t.open(args.lmsserver, args.lmsports[1])

    version = doQuery(t, "version")
    if args.player:
        playerID = getPlayerID(t, args.player)
    else:
        playerID = getPlayingID(t)

    handleStatus(t, f, playerID)

if __name__ == "__main__":
    main()
