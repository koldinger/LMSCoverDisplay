import random
import time
from enum import StrEnum, auto

from PIL import Image, ImageEnhance

#import rich.traceback
#rich.traceback.install()
#from icecream import ic 
#ic.configureOutput(includeContext=True)


class TransitionTypes(StrEnum):
    none = auto()
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
    Fade = auto()
    FadeOutIn = auto()
    Transporter = auto()
    Random = auto()


def fade(oimg, nimg, steps):
    for i in range(steps + 1):
      alpha = float(i / steps)  # Incremental alpha values
      blended = Image.blend(oimg, nimg, alpha).convert("RGB")
      yield blended
      
def _rotate(oimg, nimg, steps, angle, func):
    oimg = oimg.rotate(angle)
    nimg = nimg.rotate(angle)
    return map(lambda x: x.rotate(-angle), func(oimg, nimg, steps))

def _doPush(oimg, nimg, steps):
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
    width, height = oimg.size
    inc = int(width / steps)
    for i in range(steps, -1, -1):
        shift = inc * i
        img = oimg.copy()

        over = nimg.crop((shift, 0, width, height))
        img.paste(over, (0, 0))
        yield img

def _doSlide(oimg, nimg, steps):
    width, height = nimg.size
    for i in range(1, steps + 1):
        amt = int(i * width / steps)
        img = oimg.copy()
        over = nimg.crop((width - amt, height - amt, width, height))
        img.paste(over, (0, 0))
        yield img

def _doWipe(oimg, nimg, steps):
    width, height = nimg.size

    for i in range(1, steps + 1):
        amt = int(i * width / steps)
        img = oimg.copy()
        over = nimg.crop((0, 0, amt, height))
        img.paste(over, (0, 0))
        yield img

def _doCurtain(oimg, nimg, steps):
    left = nimg.crop((0, 0, int(nimg.width / 2), nimg.height))
    right = nimg.crop((int(nimg.width / 2), 0, nimg.width, nimg.height))

    increment = left.width / steps

    for i in range(steps + 1):
        img = oimg.copy()
        width = int(increment * i)
        lc = left.crop((left.width - width, 0, left.width, left.height))
        img.paste(lc, (0, 0))

        rc = right.crop((right.width - width, 0, right.width, right.height))
        img.paste(rc, (img.width-width, 0))

        yield img

def _doCurtainOut(oimg, nimg, steps):
    left = oimg.crop((0, 0, int(nimg.width / 2), nimg.height))
    right = oimg.crop((int(nimg.width / 2), 0, nimg.width, nimg.height))

    increment = left.width / steps

    for i in range(steps, -1, -1):
        img = nimg.copy()
        width = int(increment * i)
        lc = left.crop((left.width - width, 0, left.width, left.height))
        img.paste(lc, (0, 0))

        rc = right.crop((right.width - width, 0, right.width, right.height))
        img.paste(rc, (img.width-width, 0))

        yield img

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

def _doExpand(oimg, nimg, steps):
    width, height = nimg.size
    for i in range(1, steps + 1):
        size = int(i * width / steps)
        img = oimg.copy()
        over = nimg.resize((size, size))
        img.paste(over, (0, 0))
        yield img

def expandRightDown(oimg, nimg, steps):
    return _doExpand(oimg, nimg, steps)

def expandRightUp(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, -90, _doExpand)

def expandLeftDown(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, 90, _doExpand)

def expandLeftUp(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, 180, _doExpand)

def zoomIn(oimg, nimg, steps):
    w = oimg.width / steps
    h = oimg.height / steps

    cw = nimg.width / 2
    ch = nimg.height / 2

    yield oimg

    for i in range(1, steps + 1):
        img = oimg.copy()
        cpos = (int(cw - (w * i / 2)), int(ch - (h * i / 2)))
        csize = ((int(nimg.width / steps * i), int(nimg.height / steps * i)))
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
        csize = ((int(nimg.width / steps * i), int(nimg.height / steps * i)))
        cimg = oimg.resize((int(nimg.width / steps * i), int(nimg.height / steps * i)))
        img.paste(cimg, cpos)
        yield img

    yield nimg

def downUp(oimg, nimg, steps):
    blank = Image.new("RGB", oimg.size)
    yield from pushDown(oimg, blank, int(steps / 2))
    yield from pushUp(blank, nimg, int(steps / 2))


def curtainHoriz(oimg, nimg, steps):
    return _doCurtain(oimg, nimg, steps)

def curtainVert(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, 90, _doCurtain)

def curtainOutHoriz(oimg, nimg, steps):
    return _doCurtainOut(oimg, nimg, steps)

def curtainOutVert(oimg, nimg, steps):
    return _rotate(oimg, nimg, steps, 90, _doCurtainOut)

def fadeOutIn(oimg, nimg, steps):
    steps = int(steps / 2)

    for i in range(steps + 1, 0, -1):
        enhancer = ImageEnhance.Brightness(oimg)
        enchanced = enhancer.enhance(float(i / steps))
        yield enchanced
    for i in range(steps + 1):
        enhancer = ImageEnhance.Brightness(nimg)
        enchanced = enhancer.enhance(float(i / steps))
        yield enchanced

def transporter(oimg, nimg, steps):
    px = nimg.load()
    for i in range(steps + 1):
        threshold = i / steps
        img = oimg.copy()
        ipx = oimg.load()
        for x in range(oimg.width):
            for y in range(oimg.height):
                if random.random() < threshold:
                    ipx[x, y] = px[x, y]
        yield img

def noTransition(oimg, nimg, steps):
    yield nimg

choices = [x for x in TransitionTypes][:-1]

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
        case TransitionTypes.Fade:
            return fade
        case TransitionTypes.FadeOutIn:
            return fadeOutIn
        case TransitionTypes.Transporter:
            return transporter
        case TransitionTypes.Random:
            return getTransition(random.choice(choices))
        case TransitionTypes.none:
            return noTransition
        case _:
            raise Exception(f"Unknown transition: {transition}")


if __name__ == "__main__":
    import flaschen
    import sys
    size = 128

    f = flaschen.Flaschen("localhost", 1337, size, size)

    img1 = Image.open("cover1.jpg").resize((size, size))
    img2 = Image.open("cover2.jpg").resize((size, size))

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

    # doTransition(f, expandRightDown(img1, img2, 10))
    # time.sleep(3)
    if len(sys.argv) > 1:
        transitions = sys.argv[1:]
    else:
        transitions = TransitionTypes

    for i in transitions:
        print(i)
        sendArt(f, img1)
        time.sleep(0.5)
        trans = getTransition(i)
        doTransition(f, trans(img1, img2, 20))
        time.sleep(2)

    sendArt(f, Image.new("RGB", img1.size))

