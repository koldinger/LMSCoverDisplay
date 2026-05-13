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
from pathlib import Path

import configargparse
import rich.traceback
from flask import Flask, render_template, request
from rich import print
from pid import PidFile

from LMSTools import server
from . import discovery, transitions

from icecream import ic
ic.configureOutput(includeContext=True)

args: configargparse.Namespace
servers = discovery.discover_lms()
rich.traceback.install()

app = Flask(__name__, static_url_path="/static")

servers = []
players = {}


# Collect all the servers and players
def getServersAndPlayers():
    global servers, players
    l_servers = discovery.discover_lms()
    l_players = {}
    for s in l_servers:
        ss = server.LMSServer(s["host"], s["port"])
        l_players[ss.host] = sorted(ss.get_players(), key=lambda x:x.name)
    players = l_players
    servers = l_servers

@app.route("/", methods=["GET"])
def index():
    #print("Index - GET")
    getServersAndPlayers()

    presets = {}
    errmsg = ""
    if args.displayconfig:
        try:
            with open(args.displayconfig) as conf:
                presets = configargparse.DefaultConfigFileParser().parse(conf)
        except FileNotFoundError:
            errmsg = f"{args.displayconfig} does not exist"
            print(errmsg)

    dimtimes = presets.get("dimtimes", ["0.00", "0.00"])
    presets["dimstart"] = dimtimes[0] if len(dimtimes) > 0 else "0:00"
    presets["dimend"] = dimtimes[1] if len(dimtimes) > 1 else "0:00"

    ports = presets.get("lmsports", [9000, 9090])
    presets["lmsport_http"] = ports[0]
    presets["lmsport_telnet"] = ports[1]

    print("Servers: ", servers)
    print("Players: ", players)

    return render_template("index.html", presets=presets, players=players, servers=servers, transitions=transitions.TransitionTypes)

@app.route("/", methods=["POST"])
def indexPost():
    #print("Index - POST")

    print(request.form)

    trans = [t for t in request.form.getlist("transitions") if t]

    output = dict(request.form.items())
    presets = dict(request.form.items())        # Copy to use again

    output["transitions"] = trans
    output["dimtimes"] = [output.pop("dimstart", "0:10"), output.pop("dimend", "0:01")]
    output["lmsports"] = [output.pop("lmsport_http", 9000), output.pop("lmsport_telnet", 9090)]

    if "volume" not in output:
        output["volume"] = "0"

    #print(output)

    if args.displayconfig:
        with open(args.displayconfig, "w") as f:
            f.write(configargparse.DefaultConfigFileParser().serialize(output))

    signal_proc(args.disppid)
    signal_proc(args.remotepid)

    presets["transitions"] = trans

    return render_template("index.html", presets=presets, players=players, servers=servers, transitions=transitions.TransitionTypes)

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
    parser.add_argument("--disppid",    type=Path,         help="Signal the display process to reread configurations")
    parser.add_argument("--remotepid",  type=Path,         help="Signal the remote process to reread configurations")
    parser.add_argument("--displayconfig", type=Path,   help="Config file for the display process")

    return parser.parse_args()

def main():
    global args
    with PidFile("lmsconfig"):
        args = processCommandLine()
        app.run(host="0.0.0.0")

if __name__ == "__main__":
    main()
