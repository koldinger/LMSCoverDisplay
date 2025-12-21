from pathlib import Path

import os
import signal

import configargparse
from flask import Flask, config, render_template, request

from . import Transitions
from rich import print

from pprint import pprint, pformat

args: configargparse.Namespace

app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    print("Index - GET")
    presets = {}
    errmsg = ""
    if args.displayconfig:
        try:
            presets = configargparse.DefaultConfigFileParser().parse(open(args.displayconfig))
        except FileNotFoundError:
            errmsg = f"{args.displayconfig} does not exist"
            print(errmsg)

    dimtimes = presets.get("dimtimes", ["0.00", "0.00"])
    presets["dimstart"] = dimtimes[0] if len(dimtimes) > 0 else "0:00"
    presets["dimend"] = dimtimes[1] if len(dimtimes) > 1 else "0:00"

    ports = presets.get("lmsports", [9000, 9090])
    presets["lmsport_http"] = ports[0]
    presets["lmsport_telnet"] = ports[1]

    print(presets)

    return render_template("index.html", presets=presets, transitions=Transitions.TransitionTypes)

@app.route("/", methods=["POST"])
def indexPost():
    print("Index - POST")

    pprint(request.form)

    transitions = [t for t in request.form.getlist("transitions") if t]

    output = dict(request.form.items())
    presets = dict(request.form.items())        # Copy to use again
    output["transitions"] = transitions
    output["dimtimes"] = [output.pop("dimstart", "0:00"), output.pop("dimend", "0:00")]
    output["lmsports"] = [output.pop("lmsport_http", 9000), output.pop("lmsport_telnet", 9090)]
    if "clock" not in output:
        output["clock"] = False

    print(output)

    if args.displayconfig:
        with open(args.displayconfig, "w") as f:
            f.write(configargparse.DefaultConfigFileParser().serialize(output))

    signal_display(output["pidfile"])

    presets["transitions"] = transitions

    return render_template("index.html", presets=presets, transitions=Transitions.TransitionTypes)

def signal_display(pidfile):
    pidfile = pidfile or args.pidfile
    if args.pidfile or pidfile:
        try:
            with open(pidfile) as f:
                pid = int(f.readline().strip())

            os.kill(pid, signal.SIGHUP)
        except Exception as e:
            print("Unable to send HUP signal: ", str(e))

def processCommandLine():
    parser = configargparse.ArgumentParser("LMS Display Configuration Web Interface")
    parser.add_argument("--pidfile", type=Path,         help="Signal the process to reread configurations")
    parser.add_argument("--displayconfig", type=Path,   help="Config file for the display process")

    return parser.parse_args()

def main():
    global args
    args = processCommandLine()
    app.run(host="0.0.0.0")

if __name__ == "__main__":
    main()

