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

import socket

from collections import namedtuple


DISCOVERY_PORT = 3483
DEFAULT_DISCOVERY_TIMEOUT = .5

ATTR_HOST = "host"
ATTR_PORT = "port"

LmsInstance = namedtuple("LmsInstance", [ATTR_HOST, ATTR_PORT])

def discover_lms(timeout=DEFAULT_DISCOVERY_TIMEOUT):
    """ Scan network for Logitech Media Servers. """
    lms_msg = b"eJSON\0"

    entries = set()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    sock.bind(("", 0))

    try:
        sock.sendto(lms_msg, ("<broadcast>", DISCOVERY_PORT))

        while True:
            try:
                data, server = sock.recvfrom(1024)
                if data.startswith(b"E"):
                    # Full response is EJSON\xYYXXXX
                    # Where YY is length of port string (ie 4)
                    # And XXXX is the web interface port (ie 9000)
                    port = None
                    if data.startswith(b"JSON", 1):
                        length = data[5:6][0]
                        port = int(data[0-length:])
                    entries.add(LmsInstance(server[0], port))
            except TimeoutError:
                break
    finally:
        sock.close()
    return entries

if __name__ == "__main__":
    servers = discover_lms(timeout=0.5)
    print(servers)
