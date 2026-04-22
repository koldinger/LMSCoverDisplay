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
from adafruit_mcp230xx.mcp23017 import MCP23017
from adafruit_debouncer import Debouncer, Button
from RPi import GPIO

from . import discovery

#rich.traceback.install()
args: argparse.Namespace

def unix_timestamp():
    return f"{datetime.now().strftime("%H:%M")} |> "

from icecream import ic

#ic.configureOutput(includeContext=True, prefix=unix_timestamp)
#ic.disable()

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
    parser = configargparse.ArgumentParser("Display album art from Lyrion Music Server", ignore_unknown_config_file_keys=True)
                                          
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
buttons = {}
mcp: MCP23017
event_q = Queue()

INTERRUPT_PIN = board.D17
MCP23017_ADDR = 0x27

def initI2C():
    global mcp
    ic()

    i2c = busio.I2C(board.SCL, board.SDA)
    mcp = MCP23017(i2c, address=MCP23017_ADDR)  # MCP23017 w/ A0 set

    # Only initiasize the pins we use, namely A0-A4
    for pin in range(0, 5):
        pin = mcp.get_pin(pin)

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


def checkPins(port):
    ic(port)
    for pin in mcp.int_flag:
        value = pins[pin].value
        if not value:
            ic()
            try:
                event_q.put(KeyEvents(pin))
            except ValueError:
                print(f"Unknown button {pin}")

    mcp.clear_ints()

pin_value = {}

def pollPins():
    while True:
        for pin in pins:
            value = pin.value
            if value != pin_value.get(pin, True):
                #ic(pin, value, pin_value.get(pin, True))
                if not value:
                    ic(KeyEvents(pin._pin))
                    event_q.put(KeyEvents(pin._pin))
            pin_value[pin] = value
        #ic(pin_value.values())
        time.sleep(0.1)

def pollButtons():
    while True:
        for pin, button in buttons.items():
            button.update()
            #print(button.pressed, button.released, button.value, button.rose, button.fell, button.long_press)
            if button.pressed:
                ic(KeyEvents(pin._pin))
                event_q.put(KeyEvents(pin._pin))
        time.sleep(0.05)

reload = False

def reloadConfig(_signum, _frame):
    """ Receive a SIGHUP and reload the configuration file and command line. """
    global args, reload
    ic()
    args = process_cmdline()
    event_q.put(KeyEvents.RELOAD_CONFIG)
    # clear the cache on getArt so we get changes to images immediately


def getPlayer(servers, name) -> player.LMSPlayer:
    ic()
    for srv in servers:
        s = server.LMSServer(srv["host"], int(srv["port"]))
        if s:
            players = s.get_players()
            for plr in players:
                if name in (plr.ref ,plr.name):
                    ic(name, plr)
                    return plr
    return None


def main():
    global args, __version__
    print(f"Running.   Version: {__version__}")
    args = process_cmdline()
    console = Console()

    initI2C()

    #piddir = args.pidfile.parent
    #pidfile = args.pidfile.name

    signal.signal(signal.SIGHUP, reloadConfig)

    with PidFile("lmscontrol"):
        polling_thread = threading.Thread(target=pollButtons)
        polling_thread.daemon = True
        polling_thread.start()
        ic()

        backoff = 1
        while True:
            try:
                servers = discovery.discover_lms()
                ic(servers)
                plr = getPlayer(servers, args.player)
                ic(plr)

                while not reload:
                    event = event_q.get()
                    ic(event)
		
                    match event:
                        case KeyEvents.SKIP_FORWARD:
                            plr.__next__()
                        case KeyEvents.SKIP_BACK:
                            if plr.time_elapsed > 4.0:
                                plr.seek_to(0)
                            else:
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
