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

import datetime
import importlib.resources
from argparse import ArgumentTypeError
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace

import toml
from PIL import Image, ImageEnhance, ImageOps
from rich import print


def parsetime(timestr):
    """ Parse a time string, with different possible formats. """
    with suppress(ValueError):
        return datetime.datetime.strptime(timestr, "%H:%M",).time()
    with suppress(ValueError):
        return datetime.datetime.strptime(timestr, "%I:%M%p").time()
    with suppress(ValueError):
        return datetime.datetime.strptime(timestr, "%H").time()
    with suppress(ValueError):
        return datetime.datetime.strptime(timestr, "%I%p").time()
    return datetime.time(0, 0)

def betweentimes(now, start, end):
    """ Determine if now is between start and end on a 24 hour clock. """
    if not (start and end):
        return False
    if start <= end:
        return start <= now <= end
    return now <= end or now >= start

def makedir(name: Path):
    if not name.exists():
        name.mkdir()
    elif not name.is_dir():
        raise NotADirectoryError

def loadtoml(file, defaults):
    values = defaults | toml.load(file)
    return SimpleNamespace(**values)

def port_number(value):
    try:
        ivalue = int(value)
    except ValueError:
        raise ArgumentTypeError(f"'{value}' is not a valid integer") from None

    if ivalue not in range(0, 65535):
        raise ArgumentTypeError(f"'{value}' is not a valid port number (0-65535)")

    return ivalue

class ImageAdjuster:
    def __init__(self, contrast, color, size):
        self.contrast = contrast
        self.color = color
        self.size = (size, size)


    def adjustImage(self, img: Image.Image) -> Image.Image:
        """ Resize the image, Pump up the contrast and color if requested. """
        # Resize the image.   If it's not the same size we expect, pad it out.
        # Keeps the aspect ratio, but centered with black bounds.
        print(img.size)
        img.thumbnail(self.size, Image.Resampling.BOX)
        if img.size != self.size:
            img = ImageOps.pad(img, self.size, color="black")

        # Adjust the contrast and color, if requested
        if self.contrast != 1.0:
            img = ImageEnhance.Contrast(img).enhance(self.contrast)
        if self.color != 1.0:
            img = ImageEnhance.Color(img).enhance(self.color)

        # Turn it into RGB, just in case
        if img.mode not in ["RGB", "RGBA"]:
            img = img.convert("RGB")

        print(img.size)
        return img

def get_internal_art(name: str) -> Image.Image:
    path = importlib.resources.files("lmsdisplay").joinpath("art").joinpath(name)
    print(path)
    img = Image.open(str(path))

    return img

if __name__ == "__main__":
    for i in ["11pm", "23", "11:30pm", "11:30", "23:30", "24:30", "13pm"]:
        try:
            print(i, parsetime(i))
        except ValueError as e:
            print(e)

    print(betweentimes(parsetime("11"), parsetime("1"), parsetime("13")))
    print(betweentimes(parsetime("11"), parsetime("13"), parsetime("1")))
    print(betweentimes(parsetime("11"), parsetime("10"), parsetime("1")))
