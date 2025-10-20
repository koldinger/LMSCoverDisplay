from PIL import Image
import time
import rich.traceback
rich.traceback.install()

import random

from icecream import ic 
ic.configureOutput(includeContext=True)

from enum import StrEnum, auto

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
    DownUp = auto()
    Random = auto()



def fade(oimg, nimg, steps):
    ic()
    oimg =  oimg.convert("RGBA")
    nimg =  oimg.convert("RGBA")

    for i in range(steps + 1):
      alpha = float(i / steps)  # Incremental alpha values
      blended = Image.blend(oimg, nimg, alpha).convert("RGB")
      ic(alpha, blended)
      yield blended
      
def doPush(oimg, nimg, steps):
    ic()

    inc = oimg.width / steps
    ic(inc)

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

def pushLeft(oimg, nimg, steps):
    return doPush(oimg, nimg, steps)

def pushRight(oimg, nimg, steps):
    angle = 180
    oimg = oimg.rotate(angle)
    nimg = nimg.rotate(angle)

    return map(lambda x: x.rotate(-angle), doPush(oimg, nimg, steps))

def pushUp(oimg, nimg, steps):
    angle = 90
    oimg = oimg.rotate(angle)
    nimg = nimg.rotate(angle)

    return map(lambda x: x.rotate(-angle), doPush(oimg, nimg, steps))


def pushDown(oimg, nimg, steps):
    angle = -90
    oimg = oimg.rotate(angle)
    nimg = nimg.rotate(angle)

    return map(lambda x: x.rotate(-angle), doPush(oimg, nimg, steps))

def doOver(oimg, nimg, steps):
    width, height = oimg.size
    inc = int(width / steps)
    for i in range(steps, -1, -1):
        shift = inc * i
        img = oimg.copy()
        ic(shift, width)

        over = nimg.crop((shift, 0, width, height))
        img.paste(over, (0, 0))
        yield img

def overRight(oimg, nimg, steps):
    return doOver(oimg, nimg, steps)

def overLeft(oimg, nimg, steps):
    angle = 180
    oimg = oimg.rotate(angle)
    nimg = nimg.rotate(angle)

    return map(lambda x: x.rotate(-angle), doOver(oimg, nimg, steps))

def overUp(oimg, nimg, steps):
    angle = -90
    oimg = oimg.rotate(angle)
    nimg = nimg.rotate(angle)

    return map(lambda x: x.rotate(-angle), doOver(oimg, nimg, steps))

def overDown(oimg, nimg, steps):
    angle = 90
    oimg = oimg.rotate(angle)
    nimg = nimg.rotate(angle)

    return map(lambda x: x.rotate(-angle), doOver(oimg, nimg, steps))

def downUp(oimg, nimg, steps):
    blank = Image.new("RGB", oimg.size)
    yield from pushDown(oimg, blank, int(steps / 2))
    yield from pushUp(blank, nimg, int(steps / 2))


def noTransition(oimg, nimg, steps):
    yield nimg

choices = [x for x in TransitionTypes][:-1]

def getTransition(transition: TransitionTypes):
    match transition:
        case TransitionTypes.none:
            return noTransition
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
        case TransitionTypes.DownUp:
            return downUp
        case TransitionTypes.Random:
            return getTransition(random.choice(choices))


if __name__ == "__main__":
    ic()
    import flaschen
    f = flaschen.Flaschen("raspberrypi.local", 1337, 64, 64)

    img2 = Image.open("726420.ppm")
    img1 = Image.open("750783.ppm")

    def sendArt(f, i):
        ic()
        px = i.load()
        for x in range(64):
            for y in range(64):
                f.set(x, y, px[x, y])
        f.send()

    def doTransition(f, transition, pause=0.1):
        for i in transition:
            sendArt(f, i)
            time.sleep(pause)

    for i in TransitionTypes:
        print(i)
        trans = getTransition(i)
        doTransition(f, trans(img1, img2, 10))
        time.sleep(2)



