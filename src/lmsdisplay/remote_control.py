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
import importlib.metadata
import signal
import threading
import time
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from queue import Queue

import configargparse
from digitalio import Direction, Pull
from pid import PidFile
from rich.console import Console

from LMSTools import player, server

import board
import busio
from adafruit_mcp230xx.mcp23008 import MCP23017
from RPi import GPIO

from . import discovery

#rich.traceback.install()
args: argparse.Namespace

def unix_timestamp():
    return f"{datetime.now().strftime("%H:%M")} |> "

from icecream import ic

ic.configureOutput(includeContext=True, prefix=unix_timestamp)
ic.disable()

__version__ = "Unknown"

class PlayerNotFoundError(Exception):
    pass

try:
    # Replace 'your-package-name' with the actual distribution name of your package
    __version__ = importlib.metadata.version("lmsdisplay")
except importlib.metadata.PackageNotFoundError:
    pass
    #print("Package not found or not installed.")

def process_cmdline():
    parser = configargparse.ArgumentParser("Display album art from Lyrion Music Server")
                                          
                                           # formatter_class=argparse.RawTextHelpFormatter)

    midnight = dt.time(0, 0)

    parser.suggest_on_error = True

    parser.add_argument("--config", dest="config", default=None, type=Path, help="Load configuration from file", is_config_file=True)

    # TODO: Remove the required on this later, so we can find any player that's playing.
    parser.add_argument( "--player", "-p", default=None, required=True, help="Player to monitor")

    parser.add_argument( "--login", type=str, default=None, help="Login name.  Leave blank if login not required")
    parser.add_argument( "--password", type=str, default=None, help="Password")

    parser.add_argument( "--lmsserver", "-l", default=None, type=str, help="Name of the LMS Server")
    parser.add_argument( "--lmsports", "-L", default=[9000, 9090], type=int, nargs=2,
                        help="Ports for the LMS Server.   Takes 2 arguments, the Host port and the CLI port")

    # parser.add_argument("--pidfile", type=Path, default=Path(f"/var/run/{Path(sys.argv[0]).name}"), help="File to store PID into. %(default)s")

    parser.add_argument("--version", action="version", version=__version__)

    args = parser.parse_args()

    return args


class ReloadEvent:
    pass

class KeyEvents(Enum):
    SKIP_BACK = 0
    PLAY_PAUSE = 1
    SKIP_FORWARD = 2
    VOL_DOWN = 3
    VOL_UP = 4
    RELOAD_CONFIG = 99

pins = []
mcp: MCP23017
event_q = Queue()

INTERRUPT_PIN = 17
MCP23017_ADDR = 0x27

def initI2C():
    global mcp
    i2c = busio.I2C(board.SCL, board.SDA)
    mcp = MCP23017(i2c, address=MCP23017_ADDR)  # MCP23017 w/ A0 set

    # Only initiasize the pins we use, namely A0-A4
    for pin in range(0, 5):
        pins.append(mcp.get_pin(pin))

    for pin in pins:
        pin.direction = Direction.INPUT
        pin.pull = Pull.UP

    # Set up to check all the port B pins (pins 8-15) w/interrupts!
    mcp.interrupt_enable = 0xFFFF  # Enable Interrupts in all pins
    # If intcon is set to 0's we will get interrupts on
    # both button presses and button releases
    mcp.interrupt_configuration = 0x0000  # interrupt on any change
    mcp.io_control = 0x44  # Interrupt as open drain and mirrored
    mcp.clear_ints()  # Interrupts need to be cleared initially

    # connect either interrupt pin to the Raspberry pi's pin 17.
    # They were previously configured as mirrored.
    GPIO.setmode(GPIO.BCM)
    interrupt = INTERRUPT_PIN
    GPIO.setup(interrupt, GPIO.IN, GPIO.PUD_UP)  # Set up Pi's pin as input, pull up

    # The add_event_detect fuction will call our print_interrupt callback function
    # every time an interrupt gets triggered.
    GPIO.add_event_detect(interrupt, GPIO.FALLING, callback=checkPins, bouncetime=10)


def checkPins(_):
    for pin in mcp.int_flag:
        value = pins[pin].value
        if value:
            try:
                event_q.put(KeyEvents(pin))
            except ValueError:
                print(f"Unknown button {pin}")

    mcp.clear_ints()

reload = False

def reloadConfig(_signum, _frame):
    """ Receive a SIGHUP and reload the configuration file and command line. """
    global args, reload
    ic()
    args = process_cmdline()
    event_q.put(KeyEvents.RELOAD_CONFIG)
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
