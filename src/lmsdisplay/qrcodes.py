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

import qrcode
import psutil
import socket

from PIL import Image, ImageOps

CONFIG_PORT=80

def get_ip_address(ifname):
    interfaces = psutil.net_if_addrs()
    if ifname in interfaces:
        for addr in interfaces[ifname]:
            if addr.family == socket.AF_INET:
                return addr.address
    return None


def generate_config_qrcode(ifname:str, size) -> Image.Image:
    qr = qrcode.QRCode(version=2, box_size=2, border=3)
    hostaddr = get_ip_address(ifname)
    #hostaddr = socket.gethostname()
    url = f"http://{hostaddr}:{CONFIG_PORT}"
    print(url)
    qr.add_data(url)
    q = qr.make_image(fill_color="black", back_color="cyan")

    return ImageOps.pad(q.get_image(), (size, size), color="cyan")
    #return q.get_image().resize((size, size))

def generate_wifi_qrcode(ssid:str, size:int) -> Image.Image:
    qr = qrcode.QRCode(version=2, box_size=2, border=1)
    data = f"WIFI:S:{ssid};T:nopass;P:;;"
    print(data, len(data))
    qr.add_data(data)
    q = qr.make_image(fill_color="black", back_color="green")

    return ImageOps.pad(q.get_image(), (size, size), color="green")

if __name__ == "__main__":
    import flaschen
    import time
    def sendArt(f, i):
        px = i.load()
        for x in range(i.width):
            for y in range(i.height):
                f.set(x, y, px[x, y])
        f.send()

    import imgcat
    #q = generate_config_qrcode("enp7s0")
    q = generate_wifi_qrcode("SetupPortal")
    imgcat.imgcat(q)

    display = "coverpi.local"
    f = flaschen.Flaschen(display, 1337, 64, 64)
    sendArt(f, q)

    time.sleep(5)

    q = generate_config_qrcode("enp7s0")
    imgcat.imgcat(q)
    sendArt(f, q)

