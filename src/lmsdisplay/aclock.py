# vim: set et sw=4 sts=4 fileencoding=utf-8:
#
# Copyright 2026, Eric Koldinger, All Rights Reserved.
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
#
import math
from datetime import datetime, time, tzinfo
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw, ImageFont

from icecream import ic
#from imgcat import imgcat

type Color = str|tuple[int, int, int]|tuple[int,int,int,int]
type Number = int|float
type OptColor = Color|None
type OptInt = int|None
type OptNumber = Number|None

class AnalogClock:
    """
    Draw an analog clock into an image.

    Very configurable.
    Length and width options generally take either an int, or a float.  If given an int, it will use that as the
    absolute length or width being specified.   If given a float, the length or width will be calculated as a ratio
    of the radius.
    Options are:
        size:           [Required]The size of the canvas the clock is being drawn on.   Tuple(width, height)
        timezone:       Timezone to generate the time in.   Default: current locale
        center:         Center point of the clock.   Default: center of the canvas.   Tuple(width, height)
        radius:         Radius of the clock circle.  Default: half the smaller of height or width of the canvas
        ticks:          Draw tick marks at every hour marker. Default: True
        tick_length:    Length of each tick.   Default: 0.05
        tick_width:     Width of each tick.   Default: 1
        tick_color:     Color of each tick.   Default: white
        edge_color:     Color of the outer circle.   Default: white
        edge_width:     Width of the outer circle.   Default: 1
        hand_color:     Color of hands.  Default: white
        seconds:        Draw a second hand.  Default: False
        hr_hand_color:  Color of the hour hand.   Default: hand_color
        mn_hand_color:  Color of the minute hand.   Default: hand_color
        sec_hand_color: Color of the second hand.   Default: hand_color
        hand_width:     Width of hands. Default: 1
        hr_hand_width:  Width of the hour hand. Default: hand_width
        mn_hand_width:  Width of the minute hand. Default: hand_width
        sec_hand_width: Width of the second hand. Default: hand_width
        hr_hand_length: Length of the hour hand.  Default: .6
        mn_hand_length: Length of the minute hand.  Default: .9
        sec_hand_length:Length of the second hand.  Default: .8
        tail:           Length of the tail of the hands. Default: 0
        hr_tail:        Length of the tail of the hour hand. Default: tail
        mn_tail:        Length of the tail of the minute, hand. Default: tail
        sec_tail:       Length of the tail of the second hand. Default: tail
        arrow_width:    Width of an arrow at the end of the hands.  Default: None (no arrow)
        arrow_length:   Length of an arrow at the end of the hands.  Default: None (no arrow)
        hr_arrow_width: Width of an arrow at the end of the hour hand.  Default: arrow_width
        hr_arrow_length:Length of an arrow at the end of the hour hand.  Default: arrow_length
        mn_arrow_width: Width of an arrow at the end of the minute hand.  Default: arrow_width
        mn_arrow_length:Length of an arrow at the end of the minute hand.  Default: arrow_length
        sec_arrow_width:Width of an arrow at the end of the second hand.  Default: arrow_width
        sec_arrow_length:   Length of an arrow at the end of the second hand.  Default: arrow_length
        background_color:   Base color of the canvas.  Default: black
        background_image:   An image to draw the clock over.  Default: None
        image_pos:      A position tuple for the upper left corner of the image.
        hub_radius:     Radius of a circle drawn at the center.  Default: None
        hub_color:      Color of the hub.  Default: hand_color
        alpha:          Alpha value for the clock.  Default 255 (opaque).
        bg_alpha:       Alpha value for the backgroutnd.   Default: 0 (transparent)
        show_numerals:  Show numbers at the 3, 6, 9, and 12 positions:  Default: False
        numerals:       The numerals to use. Default: (12, 3, 6, 9)
        numerals_color: Color to draw the numbers in.   Default: 
        numerals_font: str|None = None,
        numerals_size: OptInt = None,

        Notes:
        For arrows, both a width and length must be specified, although one can be grabbed from the general value,
        and one from the specific (ie, minute hand could have mn_arrow_length, and arrow_width)

        Background should be the size of the canvas, and won't be rescaled.  If the size is different, it may leave blank
        areas (if smaller) or be cropped (if larger)

        Colors can be specified as either a name (as recogntized by the PILLOW.ImageColor module), a hexadecimal RGB or RGBA string,
        (eg. #ff00cc or #ff00ccff) or a 3 or 4 number RGB or RGBA tuple (eg (255, 255, 0) or (255, 255, 0, 128)).
        If no alpha value is specified, the value of the alpha parameter will be used.
    """

    def __init__(self,
                 size = tuple[int, int],
                 *,
                 timezone: tzinfo|None = None,
                 center: tuple[int, int]|None = None,
                 radius: OptInt = None,
                 ticks: bool = True,
                 tick_length: Number = 0.05,
                 seconds: bool = False,
                 tick_color: Color = "white",
                 edge_color: Color = "white",
                 hand_color: Color = "white",
                 hr_hand_color: OptColor = None,
                 mn_hand_color: OptColor = None,
                 sec_hand_color: OptColor = None,
                 edge_width: int = 1,
                 tick_width: int = 1,
                 hand_width: int = 1,
                 hr_hand_width: OptNumber = None,
                 mn_hand_width: OptNumber = None,
                 sec_hand_width: OptNumber = None,
                 hr_hand_length: OptNumber = .6,
                 mn_hand_length: OptNumber = .9,
                 sec_hand_length: OptNumber = .8,
                 tail_len: Number = 0,
                 hr_tail_len: OptNumber = None,
                 mn_tail_len: OptNumber = None,
                 sec_tail_len: OptNumber = None,
                 arrow_width: OptNumber = None,
                 arrow_length: OptNumber = None,
                 hr_arrow_width: OptNumber = None,
                 hr_arrow_length: OptNumber = None,
                 mn_arrow_width: OptNumber = None,
                 mn_arrow_length: OptNumber = None,
                 sec_arrow_width: OptNumber = None,
                 sec_arrow_length: OptNumber = None,
                 background_color: Color = "black",
                 hub_radius: OptInt = None,
                 hub_color: OptColor = None,
                 alpha = 255,
                 bg_alpha = 0,
                 background_image: Image.Image|str|Path|None = None,
                 image_pos: tuple[int, int] = (0, 0),
                 show_numerals: bool = False,
                 numerals: tuple[str, str, str, str] = ("12", "3", "6", "9"),
                 numerals_color: OptColor = None,
                 numerals_font: str|None = None,
                 numerals_size: OptInt = None,
                 ):

        # Covert a color specification to RGBA format, with a specified alpha channel.
        def _toRGBA(color, alpha):
            if type(color) is tuple:
                if len(color) == 3:
                    return color
                return (*color, alpha)
            rgb = ImageColor.getrgb(color)
            if len(rgb) != 4:
                rgb = (*rgb, alpha)
            return rgb

        def _lenOrRatio(x):
            if type(x) is int:
                return x
            if type(x) is float:
                # Always round up.   make sure anything is at least 1 long
                return math.ceil(x * self.radius)
            if x is None:
                return None
            raise ValueError(str(type(x)))

        self.size = size
        self.center = center or (int(self.size[0] / 2), int(self.size[1] / 2))
        self.radius = radius or min(size[0], size[1]) / 2

        self.timezone = timezone

        self.edge_color = _toRGBA(edge_color, alpha)
        self.tick_color = _toRGBA(tick_color, alpha)

        self.edge_width = _lenOrRatio(edge_width)
        self.tick_width = _lenOrRatio(tick_width)
        self.tick_length = _lenOrRatio(tick_length)

        self.ticks = ticks
        self.seconds = seconds

        self.minute_hand_color = _toRGBA(mn_hand_color or hand_color, alpha)
        self.hour_hand_color   = _toRGBA(hr_hand_color or hand_color, alpha)
        self.second_hand_color = _toRGBA(sec_hand_color or hand_color, alpha)

        self.hour_hand_width   = _lenOrRatio(hr_hand_width or hand_width)
        self.minute_hand_width = _lenOrRatio(mn_hand_width or hand_width)
        self.second_hand_width = _lenOrRatio(sec_hand_width or hand_width)

        self.background_color = _toRGBA(background_color, bg_alpha)
        self.background_image = background_image

        self.hour_hand_len = _lenOrRatio(hr_hand_length)
        self.minute_hand_len = _lenOrRatio(mn_hand_length)
        self.second_hand_len = _lenOrRatio(sec_hand_length)

        self.hr_tail_len = _lenOrRatio(hr_tail_len or tail_len)
        self.mn_tail_len = _lenOrRatio(mn_tail_len or tail_len)
        self.sec_tail_len = _lenOrRatio(sec_tail_len or tail_len)

        self.hub_radius = _lenOrRatio(hub_radius)
        self.hub_color = hub_color or hand_color

        self.arrow_width = _lenOrRatio(arrow_width or hand_width) if arrow_width else None
        self.arrow_length = _lenOrRatio(arrow_length) if arrow_length else None

        self.hr_arrow_width = _lenOrRatio(hr_arrow_width or arrow_width)
        self.hr_arrow_length = _lenOrRatio(hr_arrow_length or arrow_width)
        self.mn_arrow_width = _lenOrRatio(mn_arrow_width or arrow_width)
        self.mn_arrow_length = _lenOrRatio(mn_arrow_length or arrow_width)
        self.sec_arrow_width = _lenOrRatio(sec_arrow_width or arrow_width)
        self.sec_arrow_length = _lenOrRatio(sec_arrow_length or arrow_width)

        self.image_pos = (_lenOrRatio(image_pos[0]), _lenOrRatio(image_pos[1]))
        if isinstance(background_image, (str, Path)):
            self.background_image = Image.open(background_image)
        elif isinstance(background_image, Image.Image):
            self.background_image = background_image
        elif background_image is None:
            self.background_image = None
        else:
            raise ValueError(f"Unknown type for {background_image}")

        self.show_numerals = show_numerals
        self.numerals = numerals
        self.numerals_color = _toRGBA(numerals_color or edge_color, alpha)

        if show_numerals and numerals_font and numerals_size:
            self.font = ImageFont.truetype(numerals_font, numerals_size)


    def perp_points(self, distance, angle, base):
        a = math.radians((angle + 270) % 360)
        # Find the point where the perpendicular line starts
        px, py = self.point(distance, angle)

        # Direction perpendicular to the original line
        perp_x = -math.sin(a)
        perp_y =  math.cos(a)

        # Center the perpendicular line on (px, py)
        half_length = base / 2

        x1 = px - half_length * perp_x
        y1 = py - half_length * perp_y

        x2 = px + half_length * perp_x
        y2 = py + half_length * perp_y

        return (x1, y1), (x2, y2)

    def point(self, length, angle):
        a = math.radians((angle + 270) % 360)
        x = length * math.cos(a) + self.center[0]
        y = length * math.sin(a) + self.center[1]
        #ic(angle, a, x, y)
        return (x, y)

    def base_clock(self) -> tuple[Image.Image, ImageDraw.Draw]:
        image = Image.new("RGBA", self.size, color=self.background_color)
        ic(self.size, self.background_color)
        canvas = ImageDraw.Draw(image)
        canvas.circle(self.center, self.radius, outline=self.edge_color, width=self.edge_width)

        if self.ticks:
            for a in range(0, 360, 30):
                p1 = self.point(self.radius, a)
                p2 = self.point(self.radius - self.tick_length, a)
                canvas.line([p1, p2], fill=self.tick_color, width=self.tick_width)

        if self.show_numerals:
            anchors = ["mt", "rm", "mb", "lm"]
            distance = self.radius - 2
            if self.ticks:
                distance = distance - self.tick_length
            for i in [0, 1, 2, 3]:
                pos = self.point(distance, i * 90)
                ic(i, pos, self.numerals[i], anchors[i])
                canvas.text(pos, self.numerals[i], fill=self.numerals_color, font=self.font, anchor=anchors[i])

        return image, canvas

    def arrow_points(self, distance, angle, width, length):
        return ic(self.perp_points(distance, angle, width) + tuple(self.point(distance + length, angle)))

    def draw(self, hours:int, minutes:int, seconds:int) -> Image.Image:
        image, canvas = self.base_clock()

        # Calculate angles for each hand.
        a_hr = hours * 30
        a_mn = minutes * 6
        a_sc = seconds * 6
        a_hm = a_hr + minutes/2

        # Calculate the line endpoints
        hp = self.point(self.hour_hand_len,   a_hm)
        mp = self.point(self.minute_hand_len, a_mn)
        sp = self.point(self.second_hand_len, a_sc)

        htp = self.point(self.hr_tail_len,  a_hm + 180)
        mtp = self.point(self.mn_tail_len,  a_mn + 180)
        stp = self.point(self.sec_tail_len, a_sc + 180)
        #ic(hours, minutes, a_hr, a_mn, hp, mp)

        canvas.line([mtp, mp], fill=self.minute_hand_color, width=self.minute_hand_width)
        canvas.line([htp, hp], fill=self.hour_hand_color, width=self.hour_hand_width)
        if self.seconds:
            canvas.line([stp, sp], fill=self.second_hand_color, width=self.second_hand_width)

        if self.hub_radius:
            canvas.circle(self.center, self.hub_radius, fill=self.hub_color)

        # draw arrow heads
        if self.hr_arrow_length and self.hr_arrow_width:
            canvas.polygon(self.arrow_points(self.hour_hand_len, a_hm, self.hr_arrow_width, self.hr_arrow_length),
                           fill=self.hour_hand_color)
        if self.mn_arrow_length and self.mn_arrow_width:
            canvas.polygon(self.arrow_points(self.minute_hand_len, a_mn, self.mn_arrow_width, self.mn_arrow_length),
                           fill=self.minute_hand_color)

        if self.seconds and self.sec_arrow_length and self.sec_arrow_width:
            canvas.polygon(self.arrow_points(self.second_hand_len, a_sc, self.sec_arrow_width, self.sec_arrow_length),
                        fill=self.second_hand_color)

        # Finally, put it over a background image, if specified
        if self.background_image:
            print("Pasting onto background image")
            img = self.background_image.copy()
            img.paste(image, self.image_pos, image)
            image = img

        #imgcat(image)
        return image

    def draw_now(self) -> Image.Image:
        now = datetime.now(self.timezone).time()
        return self.draw(now.hour, now.minute, now.second)

    def draw_time(self, now: time) -> Image.Image:
        return self.draw(now.hour, now.minute, now.second)

if __name__ == "__main__":
    from imgcat import imgcat
    img = Image.open("art/cover3.jpg").resize((500,500))
    clock = AnalogClock((512, 512),
                        seconds=True,
                        edge_color="blue",
                        edge_width=1,
                        tick_color="gold",
                        tick_width=1,
                        tick_length=1,
                        hand_color="silver",
                        hand_width=1,
                        hr_hand_color="green",
                        sec_hand_color="yellow",
                        hr_hand_width=.05,
                        alpha=255,
                        bg_alpha=255,
                        background_color="black",
                        mn_arrow_width=.06,
                        mn_arrow_length=.1,
                        hr_arrow_width=.0630,
                        hr_arrow_length=.1,
                        mn_hand_length=.75,
                        tail_len = 0,
                        sec_tail_len=0,
                        mn_tail_len=0,
                        hub_radius=.1,
                        hub_color="gold",
                        #background_image=Path("art/cover4.jpg"),
                        show_numerals=True,
                        numerals = ("XII", "III", "VI", "IX"),
                        numerals_font="LiberationSerif-Regular",
                        numerals_size=16,
                        numerals_color="darkblue",
                        )

    now = datetime.now().time()
    print(now)
    #i = clock.draw_now()
    #i = clock.draw(11, 5, 0)
    i = clock.draw_now()
    imgcat(i)

    # i = clock.draw_time(now)
    # imgcat(i)
    # i = clock.draw(12, 32, 45)
    # imgcat(i)
    # imgcat(i.resize((128, 128)))

