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

defaults = {
    "player" : "",
    "transitions" : [],
    "color_saturation" : 1.6,
    "contrast_enhancement" : 1.6,
    "transition_frames" : 25,
    "frame_delay" : 0.05,
    "pause_delay" : 30,
    "show_volume_bar" : True,
    "dim_at_night" : True,
    "dim_start_time" : "22:00",
    "dim_end_time" : "07:00",
    "dimmed_brightness" : 0.41,
    "orientation" : 0,
    "image_size" : 64,
    "enable_screensaver": False,
    "disable_screensaver_dimmed": True,
    "screensaver_delay": 30,
    "display_time": 80,
    "screensavers": {
        "screensaver": "covers",
        "brightness" : 1,
        "covers": { "display_time": 30 },
        "clock": { "hour_format": 12, "font": "regular" }
    },
    "drivers": {
        "driver": "internal",
        "flaschen": {
            "display_host" : "localhost",
            "display_port" : 1337,
        },
        "internal": {
            "gpio_slowdown": 2,
            "max_framerate": 120,
            "brightness": 75,
            "hw_mapping": "adafruit-hat-pwm",
        },
    },
}
