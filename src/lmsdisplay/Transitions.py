import random
import time
from enum import StrEnum, auto

from PIL import Image, ImageEnhance

import rich.traceback

rich.traceback.install()

#from icecream import ic
#ic.configureOutput(includeContext=True)

class TransitionTypes(StrEnum):
    Instant = auto()
    PushLeft = auto()
    PushRight = auto()
    PushUp = auto()
    PushDown = auto()
    OverUp = auto()
    OverDown = auto()
    OverLeft = auto()
    OverRight = auto()
    WipeLeft = auto()
    WipeRight = auto()
    WipeUp = auto()
    WipeDown = auto()
    DownUp = auto()
    SlideRightDown = auto()
    SlideRightUp = auto()
    SlideLeftDown = auto()
    SlideLeftUp = auto()
    ExpandRightDown = auto()
    ExpandRightUp = auto()
    ExpandLeftDown = auto()
    ExpandLeftUp = auto()
    CurtainHoriz = auto()
    CurtainVert = auto()
    CurtainOutHoriz = auto()
    CurtainOutVert = auto()
    ZoomIn = auto()
    ZoomOut = auto()
    ZoomOutIn = auto()
    Fade = auto()
    FadeOutIn = auto()
    SpinOut = auto()
    SpinIn = auto()
    SpinInOut = auto()
    Transporter = auto()
    Glimmer = auto()
    Random = auto()


def fade(oimg, nimg, steps):
    for i in range(steps + 1):
        alpha = float(i / steps)  # Incremental alpha values
        blended = Image.blend(oimg, nimg, alpha).convert("RGB")
        yield blended


"""
Helper functions.   Perform an action.   In many cases, the images can be rotated before the
transition, and then rotated back to perform the operation in a certain direction.
"""


def _rotate(oimg, nimg, steps, angle, func):
    """Rotate 2 images by 'angle' degrees, perform the transition, and rotate the result back."""
    oimg = oimg.rotate(angle)
    nimg = nimg.rotate(angle)
    return map(lambda x: x.rotate(-angle), func(oimg, nimg, steps))


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


def _doOver(oimg, nimg, steps):
    """Push an image over the previous."""
    width, height = oimg.size
    inc = int(width / steps)
    for i in range(steps, -1, -1):
        shift = inc * i
        img = oimg.copy()

        over = nimg.crop((shift, 0, width, height))
        img.paste(over, (0, 0))
        yield img


def _doWipe(oimg, nimg, steps):
    """Wipe between two images, not moving either, but a line across the images."""
    width, height = nimg.size

    for i in range(1, steps + 1):
        amt = int(i * width / steps)
        img = oimg.copy()
        over = nimg.crop((0, 0, amt, height))
        img.paste(over, (0, 0))
        yield img


def _doSlide(oimg, nimg, steps):
    """Slide an image in diagonally from one corner."""
    width, height = nimg.size
    for i in range(1, steps + 1):
        amt = int(i * width / steps)
        img = oimg.copy()
        over = nimg.crop((width - amt, height - amt, width, height))
        img.paste(over, (0, 0))
        yield img


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

    rng = range(1, steps + 1) if out else range(steps, 0, -1)

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


def _doExpand(oimg, nimg, steps):
    """Expand an image from the center out"""
    width = nimg.width
    for i in range(1, steps + 1):
        size = int(i * width / steps)
        img = oimg.copy()
        over = nimg.resize((size, size))
        img.paste(over, (0, 0))
        yield img


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
    return _doOver(oimg, nimg, steps)


def overLeft(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, 180, _doOver)


def overUp(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, -90, _doOver)


def overDown(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, 90, _doOver)


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
    return _doExpand(oimg, nimg, steps)


def expandRightUp(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, -90, _doExpand)


def expandLeftDown(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, 90, _doExpand)


def expandLeftUp(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, 180, _doExpand)


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


"""
Composite functions, which use multiple other effect tests.
"""


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
        csize = (int(nimg.width / steps * i), int(nimg.height / steps * i))
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
        csize = (int(nimg.width / steps * i), int(nimg.height / steps * i))
        cimg = oimg.resize((int(nimg.width / steps * i), int(nimg.height / steps * i)))
        img.paste(cimg, cpos)
        yield img

    yield nimg


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


def glimmer(oimg, nimg, steps):
    """Change from one image to another by replacing pixels with pixels from the new image."""
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


def transporter(oimg, nimg, steps):
    """Do a "beam in" effect where pixels are gradually replaced with pixels from the new image."""

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


def instant(oimg, nimg, steps):
    """ Instantly transition to the new image. """
    yield nimg


choices = list(TransitionTypes)[:-1]


descriptions = {
    TransitionTypes.Instant:            "Instant Transition",
    TransitionTypes.PushLeft:           "Push the old image out to the left",
    TransitionTypes.PushRight:          "Push the old image out to the right",
    TransitionTypes.PushUp:             "Push the old image up from the bottom",
    TransitionTypes.PushDown:           "Push the old image down from the top",
    TransitionTypes.OverUp:             "Pull the new image up from the bottom",
    TransitionTypes.OverDown:           "Pull the new image down from the top",
    TransitionTypes.OverLeft:           "Pull the new image in from the right",
    TransitionTypes.OverRight:          "Pull the new image in from the left",
    TransitionTypes.WipeLeft:           "Wipe left from the right side",
    TransitionTypes.WipeRight:          "Wipe right from the left side",
    TransitionTypes.WipeUp:             "Wipe up from the bottom",
    TransitionTypes.WipeDown:           "Wipe down from the top",
    TransitionTypes.DownUp:             "Push the old image down, and the new image up",
    TransitionTypes.SlideRightDown:     "Slide the new image down from the top left corner",
    TransitionTypes.SlideRightUp:       "Slide the new image up from the bottom left corner",
    TransitionTypes.SlideLeftDown:      "Slide the new image down from the top left corner",
    TransitionTypes.SlideLeftUp:        "Slide the new image up from the bottom left corner",
    TransitionTypes.ExpandRightDown:    "Expand the image down from the top left corner",
    TransitionTypes.ExpandRightUp:      "Expand the image up from the bottom left corner",
    TransitionTypes.ExpandLeftDown:     "Expand the image down from the top right corner",
    TransitionTypes.ExpandLeftUp:       "Expand the image up from the bottom right corner",
    TransitionTypes.CurtainHoriz:       "Pull the new image in from the left and right",
    TransitionTypes.CurtainVert:        "Pull the new image in from the op and bottom",
    TransitionTypes.CurtainOutHoriz:    "Push the old image out to both sides",
    TransitionTypes.CurtainOutVert:     "Push the old image out to the top and bottom",
    TransitionTypes.ZoomIn:             "Expand the new in from the center",
    TransitionTypes.ZoomOut:            "Shrink the old image out to the center.",
    TransitionTypes.ZoomOutIn:          "Zoom the old image out, then the new image in",
    TransitionTypes.Fade:               "Fade from the old image to the new",
    TransitionTypes.FadeOutIn:          "Fade the old image out, then the new one in",
    TransitionTypes.SpinOut:            "Spin and expand the new image in to the center",
    TransitionTypes.SpinIn:             "Spin and shrink the old image out from the center",
    TransitionTypes.SpinInOut:          "Spin and shrink the old image to the center, then spin and expand the new image in",
    TransitionTypes.Transporter:        "Replace the old image pixel by pixel, randomly",
    TransitionTypes.Glimmer:            "Replace pixels randomly, switching between old and new until the new image is complete",
    TransitionTypes.Random:             "Pick a random transition",
}

def getTransition(transition: TransitionTypes):
    match transition:
        case TransitionTypes.PushUp:
            return pushUp
        case TransitionTypes.PushDown:
            return pushDown
        case TransitionTypes.PushLeft:
            return pushLeft
        case TransitionTypes.PushRight:
            return pushRight
        case TransitionTypes.OverUp:
            return overUp
        case TransitionTypes.OverDown:
            return overDown
        case TransitionTypes.OverLeft:
            return overLeft
        case TransitionTypes.OverRight:
            return overRight
        case TransitionTypes.WipeUp:
            return wipeUp
        case TransitionTypes.WipeDown:
            return wipeDown
        case TransitionTypes.WipeLeft:
            return wipeLeft
        case TransitionTypes.WipeRight:
            return wipeRight
        case TransitionTypes.DownUp:
            return downUp
        case TransitionTypes.SlideRightDown:
            return slideRightDown
        case TransitionTypes.SlideRightUp:
            return slideRightUp
        case TransitionTypes.SlideLeftDown:
            return slideLeftDown
        case TransitionTypes.SlideLeftUp:
            return slideLeftUp
        case TransitionTypes.ExpandRightDown:
            return expandRightDown
        case TransitionTypes.ExpandRightUp:
            return expandRightUp
        case TransitionTypes.ExpandLeftDown:
            return expandLeftDown
        case TransitionTypes.ExpandLeftUp:
            return expandLeftUp
        case TransitionTypes.CurtainHoriz:
            return curtainHoriz
        case TransitionTypes.CurtainVert:
            return curtainVert
        case TransitionTypes.CurtainOutHoriz:
            return curtainOutHoriz
        case TransitionTypes.CurtainOutVert:
            return curtainOutVert
        case TransitionTypes.ZoomIn:
            return zoomIn
        case TransitionTypes.ZoomOut:
            return zoomOut
        case TransitionTypes.ZoomOutIn:
            return zoomOutIn
        case TransitionTypes.Fade:
            return fade
        case TransitionTypes.FadeOutIn:
            return fadeOutIn
        case TransitionTypes.Transporter:
            return transporter
        case TransitionTypes.Glimmer:
            return glimmer
        case TransitionTypes.SpinOut:
            return spinOut
        case TransitionTypes.SpinIn:
            return spinIn
        case TransitionTypes.SpinInOut:
            return spinInOut
        case TransitionTypes.Random:
            return getTransition(random.choice(choices))
        case TransitionTypes.Instant:
            return instant
        case _:
            raise ValueError(transition)


if __name__ == "__main__":
    import flaschen
    import sys
    import itertools
    import random
    from pathlib import Path

    size = 64

    f = flaschen.Flaschen("coverpi.local", 1337, size, size)

    # names = ["cover1.jpg", "cover2.jpg", "cover3.jpg","cover4.jpg","cover5.jpg","cover6.jpg"]
    names = list(Path("/srv/music/FLAC/").glob("**/cover.jpg"))
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
    transitions = sys.argv[1:] if len(sys.argv) > 1 else TransitionTypes

    cur = next(images)
    nxt = next(images)
    for i in transitions:
        print(f"{i:20}  - {descriptions[i]}")
        sendArt(f, cur)
        time.sleep(0.5)
        trans = getTransition(i)
        doTransition(f, trans(cur, nxt, 20))
        cur = nxt
        nxt = next(images)
        time.sleep(2)

    sendArt(f, Image.new("RGB", cur.size))
