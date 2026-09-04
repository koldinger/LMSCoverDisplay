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
import functools
import importlib
import os
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

import nmcli
import rich.traceback
import toml
import waitress
from flask import Flask, render_template, request, send_file, send_from_directory
from icecream import ic
from LMSTools import server
from pid import PidFile
from PIL import Image
from rich import print

from . import defaults, discovery, transitions, util

ic.configureOutput(includeContext=True)
ic.disable()

args: argparse.Namespace
rich.traceback.install()

app = Flask(__name__, static_url_path="/static")

#app.jinja_env.add_extension("jinja2.ext.debug")

# TODO @kolding: Fix this
__version__ = "Unknown"
with contextlib.suppress(importlib.metadata.PackageNotFoundError):
    __version__ = importlib.metadata.version("lmsdisplay")

# Collect all the servers and players
def getPlayers():
    out = {}
    servers = discovery.discover_lms()
    for s in servers:
        try:
            name = socket.getnameinfo((s.host, s.port), socket.NI_NAMEREQD)[0]
        except socket.gaierror:
            name = None
        host_label = f"{s.host} - {name}" if name else s.host
        ss = server.LMSServer(s.host, s.port)
        s_players = [{"id": p.ref, "label": p.name } for p in sorted(ss.get_players(), key=lambda x:x.name)]

        out[host_label] = s_players
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
    if args.config:
        try:
            presets = toml.load(args.config)
        except FileNotFoundError:
            errmsg = f"{args.config} does not exist"
            print(errmsg)

    trans = makeTransitions()

    print("Presets:    ", presets)
    #print("Players:    ", players)
    #print("Transitions:",  trans)

    return render_template("lms_cover_art_config.html", presets=presets, players=players, transitions=trans, version=__version__)


@app.route("/save_config", methods=["POST"])
def save_config():
    #print("Index - POST")

    print("New Config:", request.json)

    config = request.json
    # Remove values we don't save.

    hostname = config.pop("hostname")
    if hostname and hostname != socket.gethostname():
        print(f"Setting hostname to {hostname}, was {socket.gethostname()}")
        command = ["hostnamectl", "set-hostname", hostname]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        print(result)

    try:
        write_config(args.config, config)
    except Exception as e:
        return str(e), 500

    signal_procs()

    return "Saved"


@app.route("/rescan_players", methods=["POST"])
def rescan_players():
    return getPlayers()

@app.route("/reset_config", methods=["POST"])
def reset_config():
    print(f"Resetting configuration: {args.config}")

    try:
        write_config(args.config, defaults.defaults)
    except Exception as e:
        return str(e), 500

    signal_procs()

    return "Reset"

@app.route("/reset-networking", methods=["POST"])
def reset_networking():
    print("Resetting network configuration")

    try:
        delete_config = request.json.get("delete_config", False)
        try:
            wifi_conn = get_wifi_connection()
            print(delete_config, wifi_conn)
            if delete_config and wifi_conn:
                print(f"Deleting connection {wifi_conn.name}")
                nmcli.connection.delete(wifi_conn.name)
            else:
                nmcli.connection.down(wifi_conn.name)
        except ValueError as e:
            # We're pretty swrewed up if we got here.   Wifi must have dropped between when the user hit the
            # button and now.
            print(str(e))


        # Signal the processes to reload.   This should send the display process back to it's debloy netorking screen
        signal_procs()

        command = ["systemctl", "start", "wifiselect"]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        print(result)

    except Exception as e:
        return str(e), 500

    # This is sort of unnecessary, as the client is probably connected to new network, and this has failed.
    return "Reset"


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(os.path.join(app.root_path, "static"),
                               "favicon.ico", mimetype="image/vnd.microsoft.icon")

@app.route("/art/<ttype>/<transition>")
def art(ttype, transition):
    f = get_art_path(ttype, transition)
    return send_file(f, mimetype="image/webp")

@functools.cache
def proto_images():
    ic()
    size = 256

    paths = importlib.resources.files("lmsdisplay").joinpath("art").glob("cover*")
    images = [Image.open(i).resize([size, size]).convert("RGB") for i in paths]

    return images

FRAME_DURATION = 50         # 20 fps
def make_group(images, grp):
    ic(grp)
    trans = transitions.make_transitions(grp)
    ic(trans)
    # Make sure there's more than one transsition
    if len(trans) == 1:
        trans = trans * 2

    images = images[:len(trans)]
    ic(images)

    results = []

    for i in range(len(trans)):
        f = images[i % len(images)]
        s = images[(i + 1) % len(images)]
        transition = trans[i % len(trans)]
        ic(i, transition)

        t = list(transition.function(f, s, 16))

        # Do the transition, and then make a copy of all images.
        # Have to do this because some transitions return the same object each time, which screws up
        # the image builder.
        #results.extend([i.copy() for i in transition.function(f, s, 16)])
        # add extra copies to extend
        #results.extend([s] * 5)

        results.extend([(img.copy(), FRAME_DURATION) for img in transition.function(f, s, 16)])
        # add extra copies to extend
        results.append((s, 5 * FRAME_DURATION))

    return results

def make_transition(images, transition):
    ic(transition)
    results = []

    for i in range(len(images)):
        f = images[i % len(images)]
        s = images[(i + 1) % len(images)]
        # Do the transition, and then make a copy of all images.
        # Have to do this because some transitions return the same object each time, which screws up
        # the image builder.
        results.extend([(img.copy(), FRAME_DURATION) for img in transition.function(f, s, 16)])
        # add extra copies to extend
        results.append((s, 5 * FRAME_DURATION))

    return results

def get_art_path(ttype, transition) -> Path:
    t_name = Path(transition).stem.replace("-", "_")
    filepath = Path(args.imagedir.absolute(), ttype, t_name).with_suffix(".webp")
    ic(ttype, transition, t_name, filepath)

    if filepath.exists():
        ic()
        return filepath

    match ttype:
        case "groups":
            images = proto_images()
            out = transitions.TransitionGroups(t_name)
            #ic(out, images)
            images = make_group(images, out)
        case "transitions":
            images = proto_images()
            out = transitions.TransitionTypes(t_name)
            #ic(out, images)
            images = make_transition(images, out)
        case _:
            raise ValueError(f"{ttype}/{transition}")

    filepath.parent.mkdir(parents=True, exist_ok=True)
    i, d = zip(*images)
    i[0].save(filepath, save_all=True, append_images=i[1:], optimize=True, lossless=False, loop=0, duration=d, quality=20, method=0)
    ic(filepath)
    return filepath


def get_wifi_connection():
    connections = nmcli.connection.show_all(active=True)
    for c in connections:
        if c.device == "wlan0":
            return c
    raise ValueError("No current wifi connection")

def signal_proc(pidfile):
    if pidfile:
        try:
            ic(pidfile)
            with open(pidfile) as f:
                pid = int(f.readline().strip())

            os.kill(pid, signal.SIGHUP)
        except Exception as e:
            print("Unable to send HUP signal: ", str(e))


def signal_procs():
    for i in args.pidfiles:
        signal_proc(i)


def write_config(filename, config):
    if filename:
        print(f"Saving configuration: { filename }")
        with filename.open("w") as f:
            toml.dump(config, f)


class Prerenderer(threading.Thread):
    def run(self):
        for g in transitions.TransitionGroups:
            print(f"Generating group {g} ", end="", flush=True)
            s_time = time.thread_time()
            p = get_art_path("groups", str(g) + ".webp")
            e_time = time.thread_time()
            print(f"{p} generated.  {(e_time - s_time):0.3f} CPU seconds")
        for t in transitions.TransitionTypes:
            s_time = time.thread_time()
            print(f"Generating transition {t} ", end="", flush=True)
            get_art_path("transitions", str(t) + ".webp")
            e_time = time.thread_time()
            print(f"{p} generated.  {(e_time - s_time):0.3f} CPU seconds")

def processCommandLine():
    parser = argparse.ArgumentParser("LMS Display Configuration Web Interface")
    parser.add_argument("--port", default=5000, type=util.port_number, help="Listen on this port.")
    parser.add_argument("--pidfiles",    default=[], nargs="*", type=Path,         help="Signal the display process to reread configurations")
    parser.add_argument("--config", type=Path,   help="Config file for the display process")
    parser.add_argument("--prerender", action=argparse.BooleanOptionalAction, default=False, help="Prerender art")
    parser.add_argument("--imagedir", type=Path, default=Path("/opt/share/lmsdisplay"), help="Location of image files")
    parser.add_argument("--version", action="version", version =__version__)

    return parser.parse_args()

def main():
    global args
    args = processCommandLine()
    ic(args)

    with PidFile("lmsconfig") as p:
        ic(p)

        if args.prerender:
            Prerenderer().start()

        # Generate a config file if it doesn't exist already
        if args.config and not args.config.exists():
            write_config(args.config, defaults.defaults)

        waitress.serve(app, host="0.0.0.0", port=args.port)
        #app.run(host="0.0.0.0", port=args.port)

if __name__ == "__main__":
    main()
