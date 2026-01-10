import random
import time
from enum import StrEnum, auto
from contextlib import suppress

from PIL import Image, ImageEnhance
import numpy as np

from numpy.linalg import LinAlgError
import rich.traceback

rich.traceback.install()

from icecream import ic
ic.configureOutput(includeContext=True)


"""
Helper functions.   Perform an action.   In many cases, the images can be rotated before the
transition, and then rotated back to perform the operation in a certain direction.
"""


def _rotate(oimg, nimg, steps, angle, func, *moreargs):
    """Rotate 2 images by 'angle' degrees, perform the transition, and rotate the result back."""
    oimg = oimg.rotate(angle)
    nimg = nimg.rotate(angle)
    return map(lambda x: x.rotate(-angle), func(oimg, nimg, steps, *moreargs))


def _doPush(oimg, nimg, steps):
    """Push an image out from one side to the other."""
    inc = oimg.width / steps

    width, height = oimg.size

    cimage = Image.new("RGB", (width * 2, height))
    cimage.paste(oimg, (0, 0))
    cimage.paste(nimg, (width, 0))
    cpx = cimage.load()

    for i in range(steps + 1):
        res = Image.new("RGB", oimg.size)
        respx = res.load()

        shift = i * inc
        for x in range(width):
            for y in range(height):
                respx[x, y] = cpx[x + shift, y]

        yield res
    yield nimg


def _doOver(oimg: Image, nimg: Image, steps: int, out: bool):
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


def _doCurtain(oimg, nimg, steps):
    """Perform a curtain, closing in with the new image from both sides."""
    left = nimg.crop((0, 0, int(nimg.width / 2), nimg.height))
    right = nimg.crop((int(nimg.width / 2), 0, nimg.width, nimg.height))

    increment = left.width / steps

    for i in range(steps + 1):
        img = oimg.copy()
        width = int(increment * i)
        lc = left.crop((left.width - width, 0, left.width, left.height))
        img.paste(lc, (0, 0))

        rc = right.crop((right.width - width, 0, right.width, right.height))
        img.paste(rc, (img.width - width, 0))

        yield img
    yield nimg


def _doCurtainOut(oimg, nimg, steps):
    """Perform a curtain, opening the old image to the new one"""
    left = oimg.crop((0, 0, int(nimg.width / 2), nimg.height))
    right = oimg.crop((int(nimg.width / 2), 0, nimg.width, nimg.height))

    increment = left.width / steps

    for i in range(steps, -1, -1):
        img = nimg.copy()
        width = int(increment * i)
        lc = left.crop((left.width - width, 0, left.width, left.height))
        img.paste(lc, (0, 0))

        rc = right.crop((right.width - width, 0, right.width, right.height))
        img.paste(rc, (img.width - width, 0))

        yield img
    yield nimg


def _doSpin(oimg, nimg, steps, out):
    """Spin an image in or out, shrinking or growing as it spins"""
    # Load two same-sized images
    oimga = oimg.convert("RGBA")
    nimga = nimg.convert("RGBA")

    rng = range(1, steps + 1) if out else range(steps, 1, -1)

    for i in rng:
        x, y = nimg.size
        x = int(x * i / steps)
        y = int(y * i / steps)

        angle = int(360 * i / steps)

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


"""
Actual functions that do the work.   They'll either call the helper function directly, or use the _rotate function
to make it go in a different direction
"""


def pushLeft(oimg, nimg, steps):
    return _doPush(oimg, nimg, steps)


def pushRight(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, 180, _doPush)


def pushUp(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, 90, _doPush)


def pushDown(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, -90, _doPush)


def overRight(oimg, nimg, steps):
    yield from _doOver(oimg, nimg, steps, True)
    yield nimg


def overLeft(oimg, nimg, steps):
    yield from _rotate(oimg, nimg, steps, 180, _doOver, True)
    yield nimg


def overUp(oimg, nimg, steps):
    yield from _rotate(oimg, nimg, steps, -90, _doOver, True)
    yield nimg


def overDown(oimg, nimg, steps):
    yield from _rotate(oimg, nimg, steps, 90, _doOver, True)
    yield nimg


def unCoverLeft(oimg, nimg, steps):
    yield from _doOver(nimg, oimg, steps, False)
    yield nimg


def unCoverRight(oimg, nimg, steps):
    yield from _rotate(nimg, oimg, steps, 180, _doOver, False)
    yield nimg


def unCoverUp(oimg, nimg, steps):
    yield from _rotate(nimg, oimg, steps, 90, _doOver, False)
    yield nimg


def unCoverDown(oimg, nimg, steps):
    yield from _rotate(nimg, oimg, steps, -90, _doOver, False)
    yield nimg


def wipeRight(oimg, nimg, steps):
    return _doWipe(oimg, nimg, steps)


def wipeLeft(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, 180, _doWipe)


def wipeUp(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, -90, _doWipe)


def wipeDown(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, 90, _doWipe)


def slideRightDown(oimg, nimg, steps):
    return _doSlide(oimg, nimg, steps)


def slideRightUp(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, -90, _doSlide)


def slideLeftDown(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, 90, _doSlide)


def slideLeftUp(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, 180, _doSlide)


def expandRightDown(oimg, nimg, steps):
    yield from _doExpand(oimg, nimg, steps, True)
    yield nimg


def expandRightUp(oimg, nimg, steps):
    yield from _rotate(oimg, nimg, steps, -90, _doExpand, True)
    yield nimg


def expandLeftDown(oimg, nimg, steps):
    yield from _rotate(oimg, nimg, steps, 90, _doExpand, True)
    yield nimg


def expandLeftUp(oimg, nimg, steps):
    yield from _rotate(oimg, nimg, steps, 180, _doExpand, True)
    yield nimg


def shrinkLeftUp(oimg, nimg, steps):
    yield from _doExpand(nimg, oimg, steps, False)
    yield nimg


def shrinkRightDown(oimg, nimg, steps):
    yield from _rotate(nimg, oimg, steps, 180, _doExpand, False)
    yield nimg


def shrinkRightUp(oimg, nimg, steps):
    yield from _rotate(nimg, oimg, steps, 90, _doExpand, False)
    yield nimg


def shrinkLeftDown(oimg, nimg, steps):
    yield from _rotate(nimg, oimg, steps, -90, _doExpand, False)
    yield nimg



def curtainHoriz(oimg, nimg, steps):
    return _doCurtain(oimg, nimg, steps)


def curtainVert(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, 90, _doCurtain)


def curtainOutHoriz(oimg, nimg, steps):
    return _doCurtainOut(oimg, nimg, steps)


def curtainOutVert(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, 90, _doCurtainOut)


def spinOut(oimg, nimg, steps):
    return _doSpin(oimg, nimg, steps, True)


def spinIn(oimg, nimg, steps):
    yield from _doSpin(nimg, oimg, steps, False)
    yield nimg


def leanOut(oimg, nimg, steps):
    yield from _doLean(oimg, nimg, steps, True)
    yield nimg

def leanIn(oimg, nimg, steps):
    yield from _doLean(nimg, oimg, steps, False)
    yield nimg

def flipIn(oimg, nimg, steps):
    yield from _rotate(oimg, nimg, steps, 180, _doLean, True)
    yield nimg

def flipOut(oimg, nimg, steps):
    yield from _rotate(nimg, oimg, steps, 180, _doLean, False)
    yield nimg

""" Composite functions, which use multiple other effect tests. """

def downUp(oimg, nimg, steps):
    """Lower the current image, and then raise the new image up."""
    blank = Image.new("RGB", oimg.size)
    yield from pushDown(oimg, blank, int(steps / 2))
    yield from pushUp(blank, nimg, int(steps / 2))


def zoomOutIn(oimg, nimg, steps):
    """Zoom one image out to black, and then zoom the new image in."""
    blank = Image.new("RGB", oimg.size)
    yield from zoomOut(oimg, blank, int(steps / 2))
    yield from zoomIn(blank, nimg, int(steps / 2))


def spinInOut(oimg, nimg, steps):
    """Spin one image out to black, and then spin the new one in."""
    blank = Image.new("RGB", oimg.size)
    yield from spinIn(oimg, blank, int(steps / 2))
    yield from spinOut(blank, nimg, int(steps / 2))
    yield nimg

def leanOutIn(oimg, nimg, steps):
    blank = Image.new("RGB", oimg.size)
    yield from _doLean(oimg, blank, steps, True)
    yield from _doLean(nimg, blank, steps, False)
    yield nimg

def leanflip(oimg, nimg, steps):
    blank = Image.new("RGB", oimg.size)
    yield from _doLean(oimg, blank, steps, True)
    yield blank
    yield from _rotate(nimg, blank, steps, 180, _doLean, False)
    yield nimg


def leanfliphoriz(oimg, nimg, steps):
    blank = Image.new("RGB", oimg.size)
    yield from _rotate(oimg, blank, steps, 90, _doLean,True)
    yield blank
    yield from _rotate(nimg, blank, steps, 270, _doLean, False)
    yield nimg
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

def shimmer(oimg, nimg, steps):
    """
    Change from one image to another by replacing pixels with pixels from the new image.
    Pixels can shift back and forth between the two images, with the percentage of new pixels
    increasing until all pixels have changed.
    """
    px = nimg.load()
    for i in range(steps + 1):
        threshold = i / steps
        img = oimg.copy()
        ipx = img.load()
        for x in range(oimg.width):
            for y in range(oimg.height):
                if random.random() < threshold:
                    ipx[x, y] = px[x, y]
        yield img
    yield nimg


def transporter(oimg, nimg, steps):
    """ Do a 'beam in' effect where pixels are gradually replaced with pixels from the new image. """
    px = nimg.load()
    img = oimg.copy()
    ipx = img.load()
    for i in range(steps + 1):
        threshold = i / steps
        for x in range(oimg.width):
            for y in range(oimg.height):
                if random.random() < threshold:
                    ipx[x, y] = px[x, y]
        yield img
    yield nimg

def _makeSquares(chunk, size):
    squares = []
    for y in range(0,  size[1], chunk):
        for x in range(0, size[0], chunk):
            squares.append((x, y, x + chunk, y + chunk))
    return squares

def _doBoxes(oimg, nimg, squares):
    image = oimg.copy()
    for i in squares:
        chunk = nimg.crop(i)
        image.paste(chunk, i)
        yield image


def boxes(oimg, nimg, _):
    squares = _makeSquares(16, oimg.size)
    yield oimg
    yield from _doBoxes(oimg, nimg, squares)
    yield nimg

def boxesrandom(oimg, nimg, _):
    squares = _makeSquares(16, oimg.size)
    random.shuffle(squares)
    yield oimg
    yield from _doBoxes(oimg, nimg, squares)
    yield nimg


def instant(oimg, nimg, _):
    """ Instantly transition to the new image. """
    yield oimg
    yield nimg

def doRandom(oimg, nimg, steps):
    transition = random.choice(list(TransitionTypes)[:-1]).function
    return transition(oimg, nimg, steps)


class TransitionTypes(StrEnum):
    def __new__(cls, value, description, function):
        member = str.__new__(cls, value)
        member._value_ = value
        member.description = description
        member.function = function
        return member

    Instant = auto(), "Instant Transition", instant
    PushLeft = auto(), "Push the old image out to the left", pushLeft
    PushRight = auto(),"Push the old image out to the right", pushRight
    PushUp = auto(), "Push the old image up from the bottom", pushUp
    PushDown = auto(),"Push the old image down from the top", pushDown
    OverUp = auto(),"Pull the new image up from the bottom", overUp
    OverDown = auto(), "Pull the new image down from the top", overDown
    OverLeft = auto(), "Pull the new image in from the right", overLeft
    OverRight = auto(), "Pull the new image in from the left", overRight
    UncoverLeft = auto(), "Pull the old image away to the left", unCoverLeft
    UncoverRight = auto(), "Pull the old image away to the right", unCoverRight
    UncoverUp = auto(), "Pull the old image away to the top", unCoverUp
    UncoverDown = auto(), "Pull the old image away to the bottom", unCoverDown
    WipeLeft = auto(), "Wipe left from the right side", wipeLeft
    WipeRight = auto(), "Pull the new image in from the left", wipeRight
    WipeUp = auto(), "Wipe up from the bottom", wipeUp
    WipeDown = auto(), "Wipe down from the top", wipeDown
    DownUp = auto(), "Push the old image down, and the new image up", downUp
    SlideRightDown = auto(), "Slide the new image down from the top left corner", slideRightDown
    SlideRightUp = auto(), "Slide the new image up from the bottom left corner", slideRightUp
    SlideLeftDown = auto(), "Slide the new image down from the top left corner", slideLeftDown
    SlideLeftUp = auto(), "Slide the new image up from the bottom left corner", slideLeftUp
    ExpandRightDown = auto(), "Expand the image down from the top left corner", expandRightDown
    ExpandRightUp = auto(), "Expand the image up from the bottom left corner", expandRightUp
    ExpandLeftDown = auto(), "Expand the image down from the top right corner", expandLeftDown
    ExpandLeftUp = auto(), "Expand the image up from the bottom right corner", expandLeftUp
    ShrinkRightDown = auto(), "Shrink the image down from the top left corner", shrinkRightDown
    ShrinkRightUp = auto(), "Shrink the image up from the bottom left corner", shrinkRightUp
    ShrinkLeftDown = auto(), "Shrink the image down from the top right corner", shrinkLeftDown
    ShrinkLeftUp = auto(), "Shrink the image up from the bottom right corner", shrinkLeftUp
    CurtainHoriz = auto(), "Pull the new image in from the left and right", curtainHoriz
    CurtainVert = auto(), "Pull the new image in from the op and bottom", curtainVert
    CurtainOutHoriz = auto(), "Push the old image out to both sides", curtainOutHoriz
    CurtainOutVert = auto(), "Push the old image out to the top and bottom", curtainOutVert
    ZoomIn = auto(), "Expand the new in from the center", zoomIn
    ZoomOut = auto(), "Shrink the old image out to the center.", zoomOut
    ZoomOutIn = auto(), "Zoom the old image out, then the new image in", zoomOutIn
    Fade = auto(), "Fade from the old image to the new", fade
    FadeOutIn = auto(), "Fade the old image out, then the new one in", fadeOutIn
    SpinOut = auto(), "Spin and expand the new image in to the center", spinOut
    SpinIn = auto(), "Spin and shrink the old image out from the center", spinIn
    SpinInOut = auto(), "Spin and shrink the old image to the center, then spin and expand the new image in", spinInOut
    Transporter = auto(), "Replace the old image pixel by pixel, randomly", transporter
    Shimmer = auto(), "Replace pixels randomly, switching between old and new until the new image is complete", shimmer
    LeanOut = auto(), "Lean the image out to the back", leanOut
    LeanIn = auto(),"Raise the image in from the back", leanIn
    LeanOutIn = auto(), "Lower the image out to the back, then raise the new image in from the back", leanOutIn
    FlipOut = auto(), "Lean the image out to the back", flipOut
    FlipIn = auto(),"Raise the image in from the back", flipIn
    #FlipOutIn = auto(), "Lower the image out to the back, then raise the new image in from the back", flipOutIn
    LeanFlip = auto(), "Yeah, whatever", leanflip
    LeanFlipHoriz = auto(), "Yeah, whatever", leanfliphoriz
    Boxes = auto(), "Replace boxes one at a time", boxes
    BoxesRandom = auto(), "Replace boxes one at a time", boxesrandom
    # Make sure the Random transition goes last
    Random = auto(), "Pick a random transition", doRandom

choices = list(TransitionTypes)[:-1]

def getTransition(name: str):
    val = TransitionTypes(name)

    return val.function

if __name__ == "__main__":
    import flaschen
    import sys
    import itertools
    import random
    from pathlib import Path

    size = 64

    f = flaschen.Flaschen("coverpi2.local", 1337, size, size)
    #f = flaschen.Flaschen("jylland.local", 1337, size, size)

    # names = ["cover1.jpg", "cover2.jpg", "cover3.jpg","cover4.jpg","cover5.jpg","cover6.jpg"]
    names = list(Path("/srv/music/FLAC/").glob("**/cover.jpg"))
    #names = list(Path("art").glob("cover*.jpg"))
    random.shuffle(names)

    images = itertools.cycle(map(lambda x: Image.open(x).resize([size, size]), names))

    def sendArt(f, i):
        px = i.load()
        for x in range(size):
            for y in range(size):
                f.set(x, y, px[x, y])
        f.send()

    def doTransition(f, transition, pause=0.1):
        for i in transition:
            sendArt(f, i)
            time.sleep(pause)

    # doTransition(f, expandRightDown(cur, next, 10))
    # time.sleep(3)
    transitions = map(TransitionTypes, sys.argv[1:]) if len(sys.argv) > 1 else TransitionTypes

    cur = next(images)
    nxt = next(images)
    for i in transitions:
        print(f"{i:20}  - {i.description}")
        sendArt(f, cur)
        time.sleep(0.5)
        trans = i.function
        doTransition(f, trans(cur, nxt, 21))
        cur = nxt
        nxt = next(images)

        time.sleep(2)

    sendArt(f, Image.new("RGB", cur.size))
