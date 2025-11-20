import math
from PIL import Image, ImageDraw
from datetime import datetime
#from icecream import ic

class AnalogClockGenerator:
    def __init__(self, radius = 500, hour_hand_color: tuple = (255, 255, 255, 255),
                 minute_hand_color: tuple = (255, 255, 255, 255),
                 second_hand_color: tuple = (255, 255, 255, 255),
                 show_second_hand: bool = True,
                 origin_color: tuple = (255, 255, 255, 255),
                 background_color: tuple = (0, 0, 0, 0)):

        self.radius = radius
        self.hour_hand_color = hour_hand_color
        self.minute_hand_color = minute_hand_color
        self.second_hand_color = second_hand_color
        self.origin_color = origin_color
        self.background_color = background_color
        self.show_second_hand = show_second_hand

    def get_current_clock(self) -> Image.Image:
        now = datetime.now(tz=None)

        return self.get_clock(now.hour, now.minute, now.second)

    def get_clock(self, hour: int, minute: int, second: int) -> Image.Image:
        canvas = Image.new("RGBA", (self.radius * 2, self.radius * 2), color=self.background_color)
        draw = ImageDraw.Draw(canvas)

        center = canvas.size[0] / 2

        # Draw hour markings
        length = int(self.radius * .1)
        start_distance = int(self.radius * .85)
        self.draw_hour_markings(draw, center, start_distance, length)

        # Draw origin in the center
        radius = int(self.radius * .05)
        draw.ellipse((center - radius, center - radius, center + radius, center + radius), fill=self.origin_color)

        # Draw hour hand
        length = int(self.radius * .6)
        angle = hour * (360 / 12) + minute * (360 / 12) / 60
        self.draw_hand(draw, center, angle, length, self.hour_hand_color, 7)

        # Draw minute hand
        length = int(self.radius * .7)
        angle = minute * (360 / 60) + second * (360 / 60) / 60
        self.draw_hand(draw, center, angle, length, self.minute_hand_color, 5)

        # Draw second hand
        if self.show_second_hand:
            length = int(self.radius * .8)
            angle = second * (360 / 60)
            self.draw_hand(draw, center, angle, length, self.second_hand_color, 3)

        return canvas

    # -------------- #
    # Helper methods #
    # -------------- #

    def draw_hand(self, draw: ImageDraw.ImageDraw, center, angle, length, color: tuple = (255, 255, 255, 255), width: int = 1):
        x_end = center + length * math.sin(math.radians(angle))
        y_end = center - length * math.cos(math.radians(angle))
        draw.line((center, center, x_end, y_end), fill=color, width=width)

    def draw_hour_markings(self, draw: ImageDraw.ImageDraw, center, start_distance: int = 170, length: int = 50, color: tuple = (255, 255, 255, 255), width: int = 5):
        for i in range(0, 12):
            angle = i * (360 / 12)
            x_start = center + start_distance * math.sin(math.radians(angle))
            y_start = center + start_distance * math.cos(math.radians(angle))

            x_end = center + (start_distance + length) * math.sin(math.radians(angle))
            y_end = center + (start_distance + length) * math.cos(math.radians(angle))
            draw.line((x_start, y_start, x_end, y_end), fill=color, width=width)
