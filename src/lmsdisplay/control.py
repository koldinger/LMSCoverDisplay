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

import os
import signal
import socket
import subprocess
from pathlib import Path

import configargparse
import rich.traceback
from flask import Flask, render_template, request
from LMSTools import server
from pid import PidFile
from rich import print

from . import discovery, transitions

from icecream import ic
ic.configureOutput(includeContext=True)

args: configargparse.Namespace
rich.traceback.install()

app = Flask(__name__, static_url_path="/static")
#app.jinja_env.add_extension("jinja2.ext.debug")


# Collect all the servers and players
def getPlayers():
    out = {}
    servers = discovery.discover_lms()
    for s in servers:
        ss = server.LMSServer(s["host"], s["port"])
        s_players = [{"id": p.ref, "label": p.name } for p in sorted(ss.get_players(), key=lambda x:x.name)]
        out[ss.host] = s_players
    return out

def makeTransitions():
    out = []
    for grp in transitions.TransitionGroups:
        t = {"id": str(grp), "label": str(grp), "subs": []}
        for sub in transitions.make_transitions(grp):
            s = {
                "id": str(sub),
                "label": str(sub).replace("_", " "),
            }
            t["subs"].append(s)
        out.append(t)

    return out

@app.route("/", methods=["GET"])
def index():
    #print("Index - GET")
    players = getPlayers()

    presets = {}
    errmsg = ""
    if args.displayconfig:
        try:
            with open(args.displayconfig) as conf:
                presets = configargparse.YAMLConfigFileParser().parse(conf)
        except FileNotFoundError:
            errmsg = f"{args.displayconfig} does not exist"
            print(errmsg)

    trans = makeTransitions()

    print("Presets:    ", presets)
    #print("Players:    ", players)
    #print("Transitions:",  trans)

    return render_template("lms_cover_art_config.html", presets=presets, players=players, transitions=trans)

@app.route("/save_config", methods=["POST"])
def save_config():
    #print("Index - POST")

    print(request.json)

    output = request.json


    # Remove values we don't save.
    hostname = output.pop("hostname")
    if hostname and hostname != socket.gethostname():
        print(f"Setting hostname to {hostname}, was {socket.gethostname()}")
        command = ["hostnamectl", "set-hostname", hostname]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        print(result)

    if args.displayconfig:
        print(f"Saving configuration:{ args.displayconfig}")
        with open(args.displayconfig, "w") as f:
            f.write(configargparse.DefaultConfigFileParser().serialize(output))

    for i in args.pidfiles:
        signal_proc(i)

    return "Saved"

@app.route("/reset_config", methods=["POST"])
def reset_config():
    print(f"Resetting configuration: {args.displayconfig}")
    defaults = {
        "player": "",
        "transitions": [],
        "color_saturation": 1.6,
        "contrast_enhancement": 1.6,
        "frames_in_transitions": 39,
        "frame_delay_in_transitions": 1.35,
        "show_volume_bar": True,
        "dim_at_night": True,
        "dim_start_time": "22:00",
        "dim_end_time": "07:00",
        "dimmed_brightness": 0.41,
        "display_host": "localhost",
        "display_port": 1337,
        "orientation": 0,
    }

    if args.displayconfig:
        try:
            with open(args.displayconfig, "w") as f:
                f.write(configargparse.DefaultConfigFileParser().serialize(defaults))
        except Exception as e:
            return str(e), 500

    return "Reset"

def signal_proc(pidfile):
    if pidfile:
        try:
            ic(pidfile)
            with open(pidfile) as f:
                pid = int(f.readline().strip())

            os.kill(pid, signal.SIGHUP)
        except Exception as e:
            print("Unable to send HUP signal: ", str(e))

def processCommandLine():
    parser = configargparse.ArgumentParser("LMS Display Configuration Web Interface")
    parser.add_argument("--pidfiles",    default=[], nargs='*', type=Path,         help="Signal the display process to reread configurations")
    parser.add_argument("--displayconfig", type=Path,   help="Config file for the display process")

    return parser.parse_args()

def main():
    global args
    with PidFile("lmsconfig"):
        args = processCommandLine()
        ic(args)

        # Generate a config file if it doesn't exist already
        if args.displayconfig and not args.displayconfig.exists():
            reset_config()
        app.run(host="0.0.0.0")

if __name__ == "__main__":
    main()
