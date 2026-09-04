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

import itertools
import random
import time
from contextlib import suppress
from enum import auto
from functools import partial
from pathlib import Path
from hashlib import md5
from math import ceil

import numpy as np
import rich.traceback
from numpy.linalg import LinAlgError
from PIL import Image, ImageEnhance
from strenum import StrEnum

rich.traceback.install()

"""
Helper functions.   Perform an action.   In many cases, the images can be rotated before the
transition, and then rotated back to perform the operation in a certain direction.
"""

def _rotate(angle: int, func, oimg: Image.Image, nimg: Image.Image, steps: int, *moreargs):
    """ Rotate 2 images by 'angle' degrees, perform the transition, and rotate the result back. """
    r_oimg = oimg.rotate(angle)
    r_nimg = nimg.rotate(angle)
    #return map(lambda x: x.rotate(-angle), func(oimg, nimg, steps, *moreargs))
    return (x.rotate(-angle) for x in func(r_oimg, r_nimg, steps, *moreargs))


def _doPush(oimg, nimg, steps):
    """Push an image out from one side to the other."""
    width, height = oimg.size
    inc = width / steps

    # Create a big image, twice as wide as a single one, and put the two 
    # base images side by side.
    cimage = Image.new("RGB", (width * 2, height))
    cimage.paste(oimg, (0, 0))
    cimage.paste(nimg, (width, 0))

    # Now, scan across the combined image, from left to right
    # Selecting a square subsection of the image.
    for i in range(steps + 1):
        shift = i * inc
        res = cimage.crop((shift, 0, width + shift, height))
        #for x in range(width):
        #   for y in range(height):
        #       respx[x, y] = cpx[x + shift, y]

        yield res
    yield nimg


def _doOver(oimg: Image.Image, nimg: Image.Image, steps: int, out: bool):
    """Push an image over the previous."""
    width, height = oimg.size
    inc = int(width / steps)
    rng = range(steps, 0, -1) if out else range(0, steps)

    for i in rng:
        shift = inc * i
        img = oimg.copy()

        over = nimg.crop((shift, 0, width, height))
        img.paste(over, (0, 0))
        yield img
    # yield nimg


def _doWipe(oimg, nimg, steps):
    """Wipe between two images, not moving either, but a line across the images."""
    width, height = nimg.size

    for i in range(1, steps + 1):
        amt = int(i * width / steps)
        img = oimg.copy()
        over = nimg.crop((0, 0, amt, height))
        img.paste(over, (0, 0))
        yield img
    yield nimg


def _doSlide(oimg, nimg, steps):
    """Slide an image in diagonally from one corner."""
    width, height = nimg.size
    for i in range(1, steps + 1):
        amt = int(i * width / steps)
        img = oimg.copy()
        over = nimg.crop((width - amt, height - amt, width, height))
        img.paste(over, (0, 0))
        yield img
    yield nimg


def _doCurtainIn(oimg, nimg, steps):
    """Perform a curtain, closing in with the new image from both sides."""
    left = nimg.crop((0, 0, int(nimg.width / 2), nimg.height))
    right = nimg.crop((int(nimg.width / 2), 0, nimg.width, nimg.height))

    increment = left.width / steps

    for i in range(steps + 1):
        img = oimg.copy()
        width = int(increment * i)
        lc = left.crop((left.width - width, 0, left.width, left.height))
        img.paste(lc, (0, 0))

        # Don't need to crop the right image.   We can just overflow off the side
        # rc = right.crop((0, 0, right.width, right.height))
        img.paste(right, (img.width - width, 0))

        yield img
    yield nimg


def _doCurtainOut(oimg, nimg, steps):
    """ Perform a curtain, opening the old image to the new one. """
    left = oimg.crop((0, 0, int(nimg.width / 2), nimg.height))
    right = oimg.crop((int(nimg.width / 2), 0, nimg.width, nimg.height))

    increment = left.width / steps

    for i in range(steps, -1, -1):
        img = nimg.copy()
        width = int(increment * i)
        lc = left.crop((left.width - width, 0, left.width, left.height))
        img.paste(lc, (0, 0))

        # Don't need to crop the right image.   We can just overflow off the side
        # rc = right.crop((0, 0, right.width, right.height))
        img.paste(right, (img.width - width, 0))

        yield img
    yield nimg


def _doSpin(oimg, nimg, steps, out, clockwise=True):
    """ Spin an image in or out, shrinking or growing as it spins. """
    # Load two same-sized images
    oimga = oimg.convert("RGBA")
    nimga = nimg.convert("RGBA")

    rng = range(1, steps + 1) if out else range(steps, 1, -1)
    rotation = 1 if clockwise else -1

    for i in rng:
        x, y = nimg.size
        x = int(x * i / steps)
        y = int(y * i / steps)

        angle = int(360 * i / steps) * rotation

        # Rotate image A by 45 degrees
        rot = nimga.resize([x, y]).rotate(angle, expand=True)

        # Compute position to center rotated A over B
        x = (oimga.width - rot.width) // 2
        y = (oimga.height - rot.height) // 2

        # Create a copy of B to paste onto
        result = oimga.copy()

        # Paste rotated A on top of B (using its alpha channel as mask)
        result.paste(rot, (x, y), rot)

        yield result


def _doExpand(oimg, nimg, steps, out):
    """Expand an image from the center out"""
    width = nimg.width
    rng = range(1, steps+1) if out else range(steps, 0, -1)
    for i in rng:
        size = int(i * width / steps)
        img = oimg.copy()
        over = nimg.resize((size, size))
        img.paste(over, (0, 0))
        yield img

def _find_coeffs(pa, pb):
    matrix = []
    #ic(pa, pb)
    for p1, p2 in zip(pb, pa):
        matrix.append([p1[0], p1[1], 1, 0, 0, 0,
                      -p2[0]*p1[0], -p2[0]*p1[1]])
        matrix.append([0, 0, 0, p1[0], p1[1], 1,
                      -p2[1]*p1[0], -p2[1]*p1[1]])
    A = np.matrix(matrix, dtype=np.float32)
    B = np.array(pa).reshape(8)
    res = np.dot(np.linalg.inv(A.T * A) * A.T, B)
    return np.array(res).reshape(8)

def _doLean(oimg, nimg, steps, out):
    if not steps % 2:
        steps += 1
    w, h = oimg.size
    oimga = oimg.convert("RGBA")
    nimga = nimg.convert("RGBA")
    rng = range(0, steps+1) if out else range(steps-1, -1, -1)
    with suppress(LinAlgError):
        for i in rng:
            percent = i / steps
            chx = int(percent * w / 2)
            chy = int(percent * h)
            #ic(i, percent, chx, chy)

            coeffs = _find_coeffs(
                [(0, 0), (w, 0), (w, h), (0, h)],
                [(chx, chy), (w - chx, chy), (w, h), (0, h)])
            #ic(coeffs)
            warped = oimga.transform((w, h), Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BICUBIC, fillcolor=(0, 0, 0, 0))
            res = nimga.copy()
            res.alpha_composite(warped)
            yield res

def _doPageTurn(oimg, nimg, steps):
    numblanks = 3
    blank = Image.new("RGBA", oimg.size)
    left  = itertools.chain(_doLean(oimg, blank, steps, True), [blank] * numblanks)
    right = itertools.chain([blank] * numblanks, _rotate(180, _doLean, nimg, blank, steps, False))

    for i in zip(left, right, strict=True):
        res = i[1].copy()
        res.alpha_composite(i[0])
        yield res
    yield nimg

def _doLowerFlip(oimg, nimg, steps):
    blank = Image.new("RGBA", oimg.size)
    oimg = oimg.convert("RGBA")
    nimg = nimg.convert("RGBA")
    lower = _rotate(270, _doPush, oimg, blank, steps)
    flip  = _rotate(180, _doLean, nimg, blank, steps, False)

    #yield from lower
    #yield from flip
    for i in zip(lower, flip, strict=True):
        res = i[0].convert("RGBA")
        res.alpha_composite(i[1].convert("RGBA"))
        yield res
    yield nimg


"""
Actual functions that do the work.   They'll either call the helper function directly, or use the _rotate function
to make it go in a different direction
"""

def push(oimg, nimg, steps, rotation = 0):
    return _rotate(rotation ,_doPush, oimg, nimg, steps)


def over(oimg, nimg, steps, rotation = 0):
    yield from _rotate(rotation, _doOver, oimg, nimg, steps, True)
    yield nimg


def unCover(oimg, nimg, steps, rotation = 0):
    yield from _rotate(rotation, _doOver, nimg, oimg, steps, False)
    yield nimg


def wipe(oimg, nimg, steps, rotation = 0):
    return _rotate(rotation, _doWipe, oimg, nimg, steps)


def slide(oimg, nimg, steps, rotation=0):
    return _rotate(rotation, _doSlide, oimg, nimg, steps)

def expand(oimg, nimg, steps, rotation=0):
    yield from _rotate(rotation, _doExpand, oimg, nimg, steps, True)
    yield nimg

def shrink(oimg, nimg, steps, rotation=0):
    yield from _rotate(rotation, _doExpand, nimg, oimg, steps, False)
    yield nimg

def curtainIn(oimg, nimg, steps, rotation=0):
    return _rotate(rotation, _doCurtainIn, oimg, nimg, steps)

def curtainOut(oimg, nimg, steps, rotation=0):
    return _rotate(rotation, _doCurtainOut, oimg, nimg, steps)

def spinOut(oimg, nimg, steps):
    return _doSpin(oimg, nimg, steps, True, False)

def spinIn(oimg, nimg, steps):
    yield from _doSpin(nimg, oimg, steps, False, True)
    yield nimg

def leanOut(oimg, nimg, steps):
    yield from _doLean(oimg, nimg, steps, True)
    yield nimg

def leanIn(oimg, nimg, steps):
    yield from _doLean(nimg, oimg, steps, False)
    yield nimg

def flipIn(oimg, nimg, steps):
    yield from _rotate(180, _doLean, oimg, nimg, steps, True)
    yield nimg

def flipOut(oimg, nimg, steps):
    yield from _rotate(180, _doLean, nimg, oimg, steps, False)
    yield nimg

""" Composite functions, which use multiple other effect tests. """

def downUp(oimg, nimg, steps):
    """Lower the current image, and then raise the new image up."""
    blank = Image.new("RGB", oimg.size)
    yield from _rotate(270, push, oimg, blank, steps)
    yield from _rotate(90, push, blank, nimg, steps)


def zoomOutIn(oimg, nimg, steps):
    """Zoom one image out to black, and then zoom the new image in."""
    blank = Image.new("RGB", oimg.size)
    yield from zoomOut(oimg, blank, int(steps / 2))
    yield from zoomIn(blank, nimg, int(steps / 2))


def spinInOut(oimg, nimg, steps):
    """Spin one image out to black, and then spin the new one in."""
    blank = Image.new("RGB", oimg.size)
    yield from _doSpin(blank, oimg, int(steps / 2), False, True)
    yield blank
    yield from _doSpin(blank, nimg, int(steps / 2), True, False)
    yield nimg

def leanOutIn(oimg, nimg, steps):
    blank = Image.new("RGB", oimg.size)
    yield from _doLean(oimg, blank, int(steps / 2), True)
    yield from _doLean(nimg, blank, int(steps / 2), False)
    yield nimg

def leanflip(oimg, nimg, steps):
    blank = Image.new("RGB", oimg.size)
    yield from _doLean(oimg, blank, steps, True)
    yield blank
    yield from _rotate(180, _doLean, nimg, blank, steps, False)
    yield nimg

def leanfliphoriz(oimg, nimg, steps):
    blank = Image.new("RGB", oimg.size)
    yield from _rotate(90, _doLean, oimg, blank, steps,True)
    yield blank
    yield from _rotate(270, _doLean, nimg, blank, steps, False)
    yield nimg

def pageturn(oimg, nimg, steps):
    yield from _rotate(90, _doPageTurn, oimg, nimg, steps)

def lowerflip(oimg, nimg, steps):
    yield from _doLowerFlip(oimg, nimg, steps)

"""
Functions that do all the work wihout using a helper.
"""

def zoomIn(oimg, nimg, steps):
    w = oimg.width / steps
    h = oimg.height / steps

    cw = nimg.width / 2
    ch = nimg.height / 2

    yield oimg

    for i in range(1, steps + 1):
        img = oimg.copy()
        cpos = (int(cw - (w * i / 2)), int(ch - (h * i / 2)))
        cimg = nimg.resize((int(nimg.width / steps * i), int(nimg.height / steps * i)))
        img.paste(cimg, cpos)
        yield img


def zoomOut(oimg, nimg, steps):
    w = oimg.width / steps
    h = oimg.height / steps

    cw = nimg.width / 2
    ch = nimg.height / 2

    yield oimg

    for i in range(steps, 0, -1):
        img = nimg.copy()
        cpos = (int(cw - (w * i / 2)), int(ch - (h * i / 2)))
        cimg = oimg.resize((int(nimg.width / steps * i), int(nimg.height / steps * i)))
        img.paste(cimg, cpos)
        yield img

    yield nimg


def fade(oimg, nimg, steps):
    for i in range(steps + 1):
        alpha = float(i / steps)  # Incremental alpha values
        blended = Image.blend(oimg, nimg, alpha).convert("RGB")
        yield blended

def fadeOutIn(oimg, nimg, steps):
    """Fade the old image to black, and then fade the new image in."""
    # steps = int(steps / 2)

    for i in range(steps + 1, 0, -1):
        enhancer = ImageEnhance.Brightness(oimg)
        enchanced = enhancer.enhance(float(i / steps))
        yield enchanced
    yield Image.new("RGB", oimg.size)
    for i in range(steps + 1):
        enhancer = ImageEnhance.Brightness(nimg)
        enchanced = enhancer.enhance(float(i / steps))
        yield enchanced
    yield nimg

def shimmer(oimg, nimg, steps, keep=False):
    """
    Change from one image to another by replacing pixels with pixels from the new image.
    Pixels can shift back and forth between the two images, with the percentage of new pixels
    increasing until all pixels have changed.
    """
    px = nimg.load()
    img = oimg.copy()
    for i in range(steps + 1):
        threshold = float(i) / float(steps)
        count = 0
        ipx = img.load()
        for x in range(oimg.width):
            for y in range(oimg.height):
                if random.random() < threshold:
                    count += 1
                    ipx[x, y] = px[x, y]
        yield img
        if not keep:
            img = oimg.copy()
    yield nimg


def _makeSquares(chunks, size, snake):
    chunk = int(size[0] / chunks)
    squares = []
    xseq = list(range(0, size[0], chunk))
    for y in range(0,  size[1], chunk):
        for x in xseq:
            squares.append((round(x), round(y), round(x + chunk), round(y + chunk)))
        if snake:
            xseq.reverse()
    return squares

def _makeLines(chunks, size):
    x, y = size
    chunk_sz = int(x / chunks)

    lines = []
    for i in range(0, x, chunk_sz):
        lines.append((i, 0, i + chunk_sz, y))
    return lines

def _doBoxes(oimg, nimg, squares):
    image = oimg.copy()
    for i in squares:
        chunk = nimg.crop(i)
        image.paste(chunk, i)
        yield image


def boxes(oimg, nimg, _, rotation=0):
    squares = _makeSquares(4, oimg.size, False)
    yield oimg
    yield from _rotate(rotation, _doBoxes, oimg, nimg, squares)
    yield nimg

def boxessnake(oimg, nimg, _):
    squares = _makeSquares(4, oimg.size, True)
    yield oimg
    yield from _doBoxes(oimg, nimg, squares)
    yield nimg

def boxesrandom(oimg, nimg, _):
    squares = _makeSquares(4, oimg.size, False)
    random.shuffle(squares)
    yield oimg
    yield from _doBoxes(oimg, nimg, squares)
    yield nimg

def _slice(img, num):
    w, h = img.size
    s_h = int(h / num)

    slices = []
    for y in range(0, w, s_h):
        slice = img.crop((0, y, w, y + s_h))
        slices.append(slice)
    return slices

def _doBars(oimg, nimg, steps):
    oslices = _slice(oimg, 4)
    nslices = _slice(nimg, 4)

    angle = 0
    bars = []
    for i in zip(oslices, nslices):
        bar = _rotate(angle, _doPush, i[0], i[1], steps)
        angle = (angle + 180) % 360
        bars.append(bar)

    res = Image.new("RGB", oimg.size)
    for _ in range(steps):
        chunks = [next(x) for x in bars]
        y = 0
        for chunk in chunks:
            res.paste(chunk, (0, y))
            y += chunk.height
        yield res


def _delay(oimg, nimg, frames, trans):
    for _ in range(frames):
        yield oimg
    yield from trans
    while True:
        yield nimg

def _hashImg(img):
    return md5(img.tobytes()).hexdigest()

def _doDrip(oimg, nimg, steps, func, shuffle, numgrps):
    w, h = oimg.size
    rows = list(range(w))
    if shuffle:
        random.shuffle(rows)
    grpsize = int(h / numgrps)
    groups = [rows[i:i + grpsize] for i in range(0, len(rows), grpsize)]
    o_rows = _slice(oimg, h)
    n_rows = _slice(nimg, h)
    strips = [None] * h
    delay = 0
    # Create the groups
    for delay, grp in enumerate(groups):
        for row in grp:
            strips[row] = _delay(o_rows[row], n_rows[row], delay, func(o_rows[row], n_rows[row], steps))

    # print(delay, strips)

    for _ in range(steps + ceil(h / grpsize)):
        # print(f"Iteration {i} {'-' * 20}")
        out = Image.new("RGB", (w, h))
        for row, strp in enumerate(strips):
            strip_img = next(strp)
            # print(row, _hashImg(strip_img), strip_img)
            out.paste(strip_img, (0, row))
        yield(out)

    for strp in strips:
        strp.close()

def streak(oimg, nimg, steps, rotation=0):
    yield oimg
    yield from _rotate(rotation, _doDrip, oimg, nimg, steps, _doPush, True, 8)
    yield nimg

def drip(oimg, nimg, steps, rotation=0):
    yield oimg
    yield from _rotate(rotation, _doDrip, oimg, nimg, steps, _doWipe, True, 8)
    yield nimg

def rip(oimg, nimg, steps, rotation=0):
    yield oimg
    yield from _rotate(rotation, _doDrip, oimg, nimg, steps, _doCurtainOut, True, 8)
    yield nimg

def unrip(oimg, nimg, steps, rotation=0):
    yield oimg
    yield from _rotate(rotation, _doDrip, oimg, nimg, steps, _doCurtainIn, True, 8)
    yield nimg

def diagonal(oimg, nimg, steps, rotation=0):
    yield oimg
    yield from _rotate(rotation, _doDrip, oimg, nimg, steps, _doPush, False, 8)
    yield nimg

def bars(oimg, nimg, steps, rotation=0):
    yield oimg
    yield from _rotate(rotation, _doBars, oimg, nimg, steps)
    yield nimg

def lines(oimg, nimg, steps, rotation=0):
    strips = _makeLines(steps, oimg.size)
    random.shuffle(strips)
    yield oimg
    yield from _rotate(rotation, _doBoxes, oimg, nimg, strips)
    yield nimg


def instant(oimg, nimg, _):
    """ Instantly transition to the new image. """
    yield oimg
    yield nimg

class TransitionTypes(StrEnum):
    def __new__(cls, value, description, function):
        member = str.__new__(cls, value)
        member._value_ = value
        member.description = description
        member.function = function
        return member

    Instant = auto(), "Instant Transition", instant
    Push_Left = auto(), "Push the old image out to the left", partial(push, rotation=0)
    Push_Right = auto(),"Push the old image out to the right", partial(push, rotation=180)
    Push_Up = auto(), "Push the old image up from the bottom", partial(push, rotation=90)
    Push_Down = auto(),"Push the old image down from the top", partial(push, rotation=270)
    Over_Up = auto(),"Pull the new image up from the bottom", partial(over, rotation=270)
    Over_Down = auto(), "Pull the new image down from the top", partial(over, rotation=90)
    Over_Left = auto(), "Pull the new image in from the right", partial(over, rotation=180)
    Over_Right = auto(), "Pull the new image in from the left", partial(over, rotation=0)
    Uncover_Left = auto(), "Pull the old image away to the left", partial(unCover, rotation=0)
    Uncover_Right = auto(), "Pull the old image away to the right", partial(unCover, rotation=180)
    Uncover_Up = auto(), "Pull the old image away to the top", partial(unCover, rotation=90)
    Uncover_Down = auto(), "Pull the old image away to the bottom", partial(unCover, rotation=270)
    Wipe_Left = auto(), "Wipe left from the right side", partial(wipe, rotation=180)
    Wipe_Right = auto(), "Wipe right from the left side", partial(wipe, rotation=0)
    Wipe_Up = auto(), "Wipe up from the bottom", partial(wipe, rotation=270)
    Wipe_Down = auto(), "Wipe down from the top", partial(wipe, rotation=90)
    DownUp = auto(), "Push the old image down, and the new image up", downUp
    Slide_RightDown = auto(), "Slide the new image down from the top left corner", partial(slide, rotation=0)
    Slide_RightUp = auto(), "Slide the new image up from the bottom left corner", partial(slide, rotation=270)
    Slide_LeftDown = auto(), "Slide the new image down from the top right corner", partial(slide, rotation=90)
    Slide_LeftUp = auto(), "Slide the new image up from the bottom right corner", partial(slide, rotation=180)
    Expand_RightDown = auto(), "Expand the image down from the top left corner", partial(expand, rotation=0)
    Expand_RightUp = auto(), "Expand the image up from the bottom left corner", partial(expand, rotation=270)
    Expand_LeftDown = auto(), "Expand the image down from the top right corner", partial(expand, rotation=90)
    Expand_LeftUp = auto(), "Expand the image up from the bottom right corner", partial(expand, rotation=180)
    Shrink_RightDown = auto(), "Shrink the image down from the top left corner", partial(shrink, rotation=180)
    Shrink_RightUp = auto(), "Shrink the image up from the bottom left corner", partial(shrink, rotation=90)
    Shrink_LeftDown = auto(), "Shrink the image down from the top right corner", partial(shrink, rotation=270)
    Shrink_LeftUp = auto(), "Shrink the image up from the bottom right corner", partial(shrink, rotation=0)
    CurtainIn_Horiz = auto(), "Pull the new image in from the left and right", partial(curtainIn, rotation=0)
    CurtainIn_Vert = auto(), "Pull the new image in from the op and bottom", partial(curtainIn, rotation=90)
    CurtainOut_Horiz = auto(), "Push the old image out to both sides", partial(curtainOut, rotation=0)
    CurtainOut_Vert = auto(), "Push the old image out to the top and bottom", partial(curtainOut, rotation=90)
    Zoom_In = auto(), "Expand the new in from the center", zoomIn
    Zoom_Out = auto(), "Shrink the old image out to the center.", zoomOut
    Zoom_OutIn = auto(), "Zoom the old image out, then the new image in", zoomOutIn
    Fade = auto(), "Fade from the old image to the new", fade
    Fade_OutIn = auto(), "Fade the old image out, then the new one in", fadeOutIn
    Spin_Out = auto(), "Spin and expand the new image in to the center", spinOut
    Spin_In = auto(), "Spin and shrink the old image out from the center", spinIn
    Spin_InOut = auto(), "Spin and shrink the old image to the center, then spin and expand the new image in", spinInOut
    Transporter = auto(), "Replace the old image pixel by pixel, randomly", partial(shimmer, keep=True)
    Shimmer = auto(), "Replace pixels randomly, switching between old and new until the new image is complete", partial(shimmer, keep=False)
    Lean_Out = auto(), "Lean the image out to the back", leanOut
    Lean_In = auto(),"Raise the image in from the back", leanIn
    Lean_OutIn = auto(), "Lower the image out to the back, then raise the new image in from the back", leanOutIn
    Flip_Out = auto(), "Lean the image out to the back", flipOut
    Flip_In = auto(),"Raise the image in from the back", flipIn
    # FlipOutIn = auto(), "Lower the image out to the back, then raise the new image in from the back", flipOutIn
    Lean_Flip = auto(), "Lean the old image out at the bottom, and flip the new one in from the top", leanflip
    Lean_FlipHoriz = auto(), "Lean the old image out to the left, and flip the new one in from the right", leanfliphoriz
    #LowerFlip = auto(), "Complicated", lowerflip
    PageTurn = auto(), "Page Turn", pageturn
    Boxes_Down = auto(), "Replace boxes one at a time, top to bottom", boxes
    Boxes_Left = auto(), "Replace boxes one at a time, top to bottom", partial(boxes, rotation=90)
    Boxes_Right = auto(), "Replace boxes one at a time, top to bottom", partial(boxes, rotation=270)
    Boxes_Up = auto(), "Replace boxes one at a time, bottom to top", partial(boxes, rotation=180)
    Boxes_Random = auto(), "Replace boxes one at a time, randomly", boxesrandom
    Boxes_Snake = auto(), "Replace boxes one at a time, top to bottom, snaking", boxessnake
    Bars_Horiz = auto(), "Move bars of the image sideways", partial(bars, rotation=0)
    Bars_Vert = auto(), "Move bars of the image vertically", partial(bars, rotation=90)
    Streak_Down = auto(), "Streak columns from the top to bottom", partial(streak, rotation=270)
    Streak_Up = auto(), "Streak columns from the top to bottom", partial(streak, rotation=90)
    Streak_Left = auto(), "Streak columns from the top to bottom", partial(streak, rotation=0)
    Streak_Right = auto(), "Streak columns from the top to bottom", partial(streak, rotation=180)
    Drip_Left = auto(), "Drip columns from the top to bottom", partial(drip, rotation=180)
    Drip_Right = auto(), "Drip columns from the top to bottom", partial(drip, rotation=0)
    Drip_Down = auto(), "Drip columns from the top to bottom", partial(drip, rotation=90)
    Drip_Up = auto(), "Drip columns from the top to bottom", partial(drip, rotation=270)
    Diagonal_Left = auto(), "Diagonal", partial(diagonal, rotation=0)
    Diagonal_Right = auto(), "Diagonal", partial(diagonal, rotation=180)
    Diagonal_Up = auto(), "Diagonal", partial(diagonal, rotation=90)
    Diagonal_Down = auto(), "Diagonal", partial(diagonal, rotation=270)
    Rip_Horiz = auto(), "Rip apart horizontally", partial(rip, rotation=0)
    Rip_Vert = auto(), "Rip apart vertically", partial(rip, rotation=90)
    Unrip_Horiz = auto(), "Push image together horizontally", partial(unrip, rotation=0)
    Unrip_Vert = auto(), "Push image together vertically", partial(unrip, rotation=90)
    Lines_Horiz = auto(), "Draw lines horizontally", partial(lines, rotation=90)
    Lines_Vert = auto(), "Draw lines vertically", partial(lines, rotation=0)

class Directions(StrEnum):
    Up = auto()
    Down = auto()
    Left = auto()
    Right = auto()
    LeftDown = auto()
    RightDown = auto()
    LeftUp = auto()
    RightUp = auto()
    Horiz = auto()
    Vert = auto()
    In = auto()
    Out = auto()
    InOut = auto()
    OutIn = auto()

Cardinal = [Directions.Left, Directions.Right, Directions.Up, Directions.Down]
Diagonal = [Directions.LeftUp, Directions.RightUp, Directions.LeftDown, Directions.RightDown]
UpDown   = [Directions.Horiz, Directions.Vert]
InOut    = [Directions.In, Directions.Out, Directions.InOut]
InOrOut  = [Directions.In, Directions.Out]
OutIn    = [Directions.In, Directions.Out, Directions.OutIn]

class TransitionGroups(StrEnum):
    def __new__(cls, value, description, variants):
        member = str.__new__(cls, value)
        member._value_ = value
        member.description = description
        member.variants = variants
        return member

    Push = auto(), "Push the old image out with the new image", Cardinal
    Over = auto(), "Slide the new image over the old", Cardinal
    Uncover = auto(), "Uncover the new image by sliding the old", Cardinal
    Wipe = auto(), "Wipe the new image to the old", Cardinal
    DownUp = auto(), "Lower the old image, and raise a new one", None
    Slide = auto(), "Slide the new image in diagonally", Diagonal
    Expand = auto(), "Expand the new image in diagonally", Diagonal
    Shrink = auto(), "Shrink the old image out diagonally, uncovering the new", Diagonal
    CurtainIn = auto(), "Close a curtain with the new image", UpDown
    CurtainOut = auto(), "Open a curtain exposing the new image", UpDown
    Fade = auto(), "Fade from one image to the other", [None, Directions.OutIn]
    Transporter = auto(), "Replace the old image pixel by pixel, randomly", None
    Shimmer = auto(), "Replace pixels randomly, switching between old and new until the new image is complete", None
    Zoom = auto(), "Zoom an image in or out", OutIn
    Spin = auto(), "Spin an image in or out", InOrOut
    Lean = auto(), "Lean image in or out", OutIn
    Flip = auto(), "Flip image in or out", InOrOut
    Boxes = auto(), "Replace the image box by box", [*Cardinal, "Random", "Snake"]
    Bars = auto(), "Slide alternating bars in or out", UpDown
    Streak = auto(), "Replace the image by Streak", Cardinal
    Drip = auto(), "Drip the new image in over the old", Cardinal
    Diagonal = auto(), "Biagonal", Cardinal
    Rip = auto(), "Rip the image apart", UpDown
    Unrip = auto(), "Push the image together", UpDown
    Lines = auto(), "Draw lines one at a time", UpDown
    PageTurn = auto(), "Turn a page", None


def make_transitions(group):
    variants = group.variants
    if not variants:
        return [TransitionTypes(str(group))]
    output = []
    for v in variants:
        if v:
            output.append(TransitionTypes(str(group) + "_" + str(v)))
        else:
            output.append(TransitionTypes(str(group)))
    return output

def getTransition(name: str):
    val = TransitionTypes(name)

    return val.function

def expandGroups(transitions):
    for i in transitions:
        if i in TransitionTypes:
            yield TransitionTypes(i)
        elif i in TransitionGroups:
            grp = TransitionGroups(i)
            yield from make_transitions(grp)
        else:
            print(f"No group or transitions named {i}")


def test():
    import sys
    import flaschen

    from datetime import datetime

    size = 64

    sys.argv.pop(0)
    # print(sys.argv)
    display = sys.argv.pop(0) if len(sys.argv) > 0 else "localhost"

    f = flaschen.Flaschen(display, 1337, size, size)
    # f = flaschen.Flaschen("jylland.local", 1337, size, size)

    #names = ["cover1.jpg", "cover2.jpg", "cover3.jpg","cover4.jpg","cover5.jpg","cover6.jpg"]
    #names = ["test1.png", "test2.png", "test3.png", "qrcode.png"]
    #names = [Path("art", x) for x in names]

    names = list(Path("/srv/music/FLAC/").glob("**/cover.jpg"))
    #names = list(Path("art").glob("cover*.png"))
    random.shuffle(names)

    #names = ["/srv/music/FLAC/Bob_Mould/The_Last_Dog_and_Pony_Show/cover.jpg", "/srv/music/FLAC/Porcupine_Tree/Recordings/cover.jpg"]

    images = zip(itertools.cycle(Image.open(x).resize([size, size]).convert("RGB") for x in names), itertools.cycle(names))

    def sendArt(f, i):
        px = i.load()
        for x in range(i.width):
            for y in range(i.height):
                f.set(x, y, px[x, y])
        f.send()

    def doTransition(f, transition, pause=0.1):
        start = datetime.now()
        frames = 0
        for i in transition:
            sendArt(f, i)
            time.sleep(pause)
            frames += 1
        end = datetime.now()
        print(frames, end - start)

    # doTransition(f, expandRightDown(cur, next, 10))
    # time.sleep(3)
    transitions = sys.argv if len(sys.argv) > 0 else TransitionTypes
    print(transitions)

    cur = next(images)
    nxt = next(images)
    print(list(expandGroups(transitions)))

    for i in expandGroups(transitions):
        print(f"{i:20}  - {i.description}")
        print(f"\t=> {nxt[1]}")
        sendArt(f, cur[0])
        time.sleep(2.0)
        trans = i.function
        doTransition(f, trans(cur[0], nxt[0], 20))
        cur = nxt
        nxt = next(images)

        time.sleep(2)

    sendArt(f, Image.new("RGB", cur[0].size))

if __name__ == "__main__":
    test()

