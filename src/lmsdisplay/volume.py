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

from PIL import Image, ImageDraw

def drawVolume(volume, size=(500, 500), color=(255, 255, 255, 255), xoffset=.05, yoffset=.85, yheight=0.1):
    x, y = size

    canvas = Image.new("RGBA", size, color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    top_x = int(xoffset * float(x))
    bot_x = int((1.0 - xoffset) * float(x))

    top_y = int(yoffset * float(y))
    bot_y = int((yoffset + yheight) * float(y))

    draw.rounded_rectangle([(top_x, top_y), (bot_x, bot_y)], radius=5, outline=color, width=1)

    vol_x = int((float(volume) / 100.0) * (bot_x - top_x)) + top_x

    if volume not in [0, 100]:
        draw.line([(vol_x, top_y), (vol_x, bot_y)], width=1, fill=color)
    if volume != 0:
        draw.rounded_rectangle([(top_x, top_y), (vol_x, bot_y)], radius=5, outline=color, fill=color)

    return canvas

if __name__ == "__main__":
    background = Image.open("../../cover5.jpg")
    size = (500, 500)
    background = background.resize(size)

    for volume in range(0, 101, 10):
        vol = drawVolume(volume, size, (211, 100, 100, 200), xoffset=.05, yoffset=.9, yheight=.025)
        img = background.copy()
        img.paste(vol, (0, 0), vol)
        img.convert("RGB").save(f"test{volume}.jpg")
