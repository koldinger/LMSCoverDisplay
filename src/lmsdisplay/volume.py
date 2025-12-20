from PIL import Image, ImageDraw

def drawVolume(volume, size=(500, 500), color=(255, 255, 255, 255)):
    x, y = size

    canvas = Image.new("RGBA", size, color=(0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    top_x = int(.05 * float(x))
    bot_x = int(.95 * float(x))

    top_y = int(.85 * float(y))
    bot_y = int(.95 * float(y))

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
        vol = drawVolume(volume, size, (211, 211, 211, 200))
        img = background.copy()
        img.paste(vol, (0, 0), vol)
        img.convert("RGB").save(f"test{volume}.jpg")
