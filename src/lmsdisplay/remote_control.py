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
import signal
import threading
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from queue import Queue
from types import SimpleNamespace

import board
import busio
import watchfiles
from adafruit_debouncer import Button
from adafruit_mcp230xx.mcp23017 import MCP23017
from digitalio import Direction, Pull
from LMSTools import player, server
from pid import PidFile
from rich.console import Console
from RPi import GPIO

from . import defaults, discovery, util

#rich.traceback.install()
args: argparse.Namespace
config: SimpleNamespace

def unix_timestamp():
    return f"{datetime.now().strftime("%H:%M")} |> "

from icecream import ic

ic.configureOutput(includeContext=True, prefix=unix_timestamp)
ic.disable()

__version__ = "Unknown"

class PlayerNotFoundError(Exception):
    pass

with contextlib.suppress(importlib.metadata.PackageNotFoundError):
    # Replace 'your-package-name' with the actual distribution name of your package
    __version__ = importlib.metadata.version("lmsdisplay")

def process_cmdline():
    parser = argparse.ArgumentParser("Display album art from Lyrion Music Server")

    parser.suggest_on_error = True

    parser.add_argument("--config", dest="config", default=None, type=Path, help="Load configuration from file", required=True)
    parser.add_argument("--watch-config", action=argparse.BooleanOptionalAction, default=True, help="Automatically watch the config file for changes")
    parser.add_argument("--version", action="version", version=__version__)

    args = parser.parse_args()

    config = util.loadtoml(args.config, defaults.defaults)

    return args, config


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
buttons = {}
mcp: MCP23017
event_q = Queue()

RESET_PERIOD = 4.0          # Number of seconds in a song during which we'll go back to the previous song, else we just go back to the start of this one.

INTERRUPT_PIN = board.D17
MCP23017_ADDR = 0x27

def initI2C():
    i2c = busio.I2C(board.SCL, board.SDA)
    mcp = MCP23017(i2c, address=MCP23017_ADDR)  # MCP23017 w/ A0 set

    # Only initiasize the pins we use, namely A0-A4
    for p in range(0, 5):
        pin = mcp.get_pin(p)

        pin.direction = Direction.INPUT
        pin.pull = Pull.UP
        #ic(pin, pin._pin)
        button = Button(pin, long_duration_ms=500)
        print(button.value)
        pins.append(pin)
        buttons[pin] = button


    # Set up to check all the port B pins (pins 8-15) w/interrupts!
    #mcp.interrupt_enable = 0xFFFF  # Enable Interrupts in all pins
    # If intcon is set to 0's we will get interrupts on
    # both button presses and button releases

    #mcp.interrupt_configuration = 0x0000  # interrupt on any change
    #mcp.io_control = 0x44  # Interrupt as open drain and mirrored
    #mcp.clear_ints()  # Interrupts need to be cleared initially

    # connect either interrupt pin to the Raspberry pi's pin 17.
    # They were previously configured as mirrored.

    GPIO.setmode(GPIO.BCM)

    # Enable the following to use interrupts
    #GPIO.setup(INTERRUPT_PIN, GPIO.IN, GPIO.PUD_UP)  # Set up Pi's pin as input, pull up

    # The add_event_detect fuction will call our print_interrupt callback function
    # every time an interrupt gets triggered.
    #GPIO.add_event_detect(INTERRUPT_PIN, GPIO.FALLING, callback=checkPins, bouncetime=10)

    return mcp

def poll_buttons():
    while True:
        for pin, button in buttons.items():
            button.update()
            #print(button.pressed, button.released, button.value, button.rose, button.fell, button.long_press)
            if button.pressed:
                ic(KeyEvents(pin._pin))
                event_q.put(KeyEvents(pin._pin))
        time.sleep(0.05)

def handle_signal(_signum, _frame):
    reload_config()

def watch_config(configfile):
    c = Path(configfile).absolute()

    def filter_for_config(change: watchfiles.Change, path: str) -> bool:
        return Path(path) == c and change in [watchfiles.Change.added, watchfiles.Change.modified]

    # watch the parent directory because if the config file is "changed", it may Automatically
    # be deleted, and then readded.   This causes subesquent changes to be lost
    for _ in watchfiles.watch(c.parent, watch_filter=filter_for_config):
        reload_config()



def reload_config():
    """ Receive a SIGHUP and reload the configuration file and command line. """
    global args, config
    print("Reloading Configuration")
    args, config = process_cmdline()
    event_q.put(KeyEvents.RELOAD_CONFIG)
    # clear the cache on getArt so we get changes to images immediately


def get_player(servers, name) -> player.LMSPlayer | None:
    ic()
    for srv in servers:
        s = server.LMSServer(srv.host, int(srv.port))
        if s:
            players = s.get_players()
            for plr in players:
                if name in (plr.ref ,plr.name):
                    ic(name, plr)
                    return plr
    return None


def main():
    global args, config, mcp
    print(f"Running.   Version: {__version__}")
    args, config = process_cmdline()
    console = Console()

    mcp = initI2C()

    #piddir = args.pidfile.parent
    #pidfile = args.pidfile.name

    signal.signal(signal.SIGHUP, reload_config)
    if args.watch_config:
        threading.Thread(target=watch_config, args=(args.config,), daemon=True).start()

    with PidFile("lmsremote"):
        polling_thread = threading.Thread(target=poll_buttons)
        polling_thread.daemon = True
        polling_thread.start()

        backoff = 1
        while True:
            try:
                servers = discovery.discover_lms()
                ic(servers)
                plr = get_player(servers, config.player)
                ic(plr)

                while True:
                    event = event_q.get()
                    ic(event)

                    match event:
                        case KeyEvents.SKIP_FORWARD:
                            plr.next()
                        case KeyEvents.SKIP_BACK:
                            if plr.time_elapsed > RESET_PERIOD:
                                plr.seek_to(0)
                            else:
                                plr.prev()
                        case KeyEvents.PLAY_PAUSE:
                            plr.toggle()
                        case KeyEvents.VOL_UP:
                            plr.volume_up()
                        case KeyEvents.VOL_DOWN:
                            plr.volume_down()
                        case KeyEvents.RELOAD_CONFIG:
                            break
            except Exception:
                console.print_exception()
                time.sleep(backoff)
                backoff = min(backoff * 2, 120)

if __name__ == "__main__":
    main()
