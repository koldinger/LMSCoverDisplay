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

import sys

from PIL import Image
from pathlib import Path

import transitions
import util

from icecream import ic

def makeGif(outputdir: Path, images, transition):
    print(f"Processing transition: {transition}")

    results = []

    for i in range(len(images)):
        f = images[i % len(images)]
        s = images[(i + 1) % len(images)]
        # Do the transition, and then make a copy of all images.
        # Have to do this because some transitions return the same object each time, which screws up
        # the gif builder.
        results.extend([i.copy() for i in transition.function(f, s, 16)])
        # add extra copies to pause
        results.extend([s] * 5)

    outname = outputdir.joinpath(str(transition)).with_suffix(".gif")

    print(f"Transition: {transition} {outname} {len(results)}")

    results[0].save(outname, save_all=True, append_images=results[1:], optimize=True, loop=0, duration=1*len(results))

def makeGifs(output: Path, images, trans=None):
    if not trans:
        trans = list(transitions.TransitionTypes)

    for i in trans:
        try:
            makeGif(output, images, i)
        except Exception as e:
            print(f"{i} Failed: {e}")

def doTheGifThing():
    output = Path("static/transitions")
    size = 256

    trans = sys.argv.copy()
    trans.pop(0)
    trans = [transitions.TransitionTypes(i) for i in trans]

    util.makedir(output)

    names = ["test1.png", "test2.png", "test3.png"]
    names = [Path("art", x) for x in names]

    images = [Image.open(i).resize([size, size]).convert("RGB") for i in names]

    makeGifs(output, images, trans)

def makeGrpGif(outputdir: Path, images, grp):
    print(f"Procressing group {grp}")
    trans = transitions.make_transitions(grp)
    # Make sure there's more than one transsition
    if len(trans) == 1:
        trans = trans * 2

    images = images[:len(trans)]

    results = []

    for i in range(len(images)):
        f = images[i % len(images)]
        s = images[(i + 1) % len(images)]
        transition = trans[i % len(trans)]

        # Do the transition, and then make a copy of all images.
        # Have to do this because some transitions return the same object each time, which screws up
        # the gif builder.
        results.extend([i.copy() for i in transition.function(f, s, 16)])
        # add extra copies to extend
        results.extend([s] * 5)

    # Generate a name for the file.
    # Due to a bug in the web page, we need to replace the _ (underscores) with
    # - (dash).   Not sure why, AI generated JavaScript is beyond me.
    #
    outname = outputdir.joinpath(str(grp).replace("_", "-")).with_suffix(".gif")

    print(f"Transition: {grp} {outname} {len(results)}")

    results[0].save(outname, save_all=True, append_images=results[1:], optimize=True, loop=0, duration=1*len(results))


def makeGrpGifs(output, images, grps):
    if not grps:
        grps = list(transitions.TransitionGroups)

    for i in grps:
        try:
            makeGrpGif(output, images, i)
        except Exception as e:
            print(f"{i} Failed: {e}")


def doTheGroupThing():
    output = Path("static/groups")
    size = 256

    grps = sys.argv.copy()
    grps.pop(0)
    grps = [transitions.TransitionGroups(i) for i in grps]

    util.makedir(output)

    names = ["test1.png", "test2.png", "test3.png", "test4.png", "test5.png"]
    names = [Path("art", x) for x in names]

    images = [Image.open(i).resize([size, size]).convert("RGB") for i in names]

    makeGrpGifs(output, images, grps)

def main():
    doTheGifThing()
    doTheGroupThing()

if __name__ == "__main__":
    main()

