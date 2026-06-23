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

import queue
import re
import threading
import time
from collections import namedtuple
from urllib.parse import unquote

from telnetlib3 import telnetlib

#from datetime import datetime
# def time_format():
#     now = datetime.now()
#     return f'{now.strftime("%H:%M:%S")} --> '

#from icecream import ic
#$ic.configureOutput(includeContext=True)

idpat = re.compile(r" id:\s*(\d+)")
playpat = re.compile(r" mode:\s*(\w+)")
volpat = re.compile(r" volume:\s*(\d+)")

MAX_BACKOFF = 120

LMS_TELNET_PORT = 9090

def command_string(string, query=False):
    if query:
        string = string + " ?"
    return string + "\r\n"

PlayEvent = namedtuple("PlayEvent", ["mode", "song", "volume"])

class PlayerMonitor(threading.Thread):
    def __init__(self, player_id: str, server: str, queue: queue.Queue, login=None, password=None):
        super().__init__()
        # ic(player_id, server, login, password)
        self.player_id = player_id
        self.server = server
        self.queue = queue
        self.login = login
        self.password = password
        self.tn: telnetlib.Telnet
        self.backoff = 1
        self.closed = False

        self.daemon = True

    def getLine(self):
        try:
            line = self.tn.read_until(b"\n")
            if line:
                line = unquote(line.strip())
                return line

            #ic("EOF")
            raise EOFError
        except AttributeError:
            # This is where we end up when the telnet session has been closed by another
            # thread.   Doesn't quite seem right, but it's what happens.
            raise ConnectionError("Closed")

    def sendLine(self, line):
        self.tn.write(bytes(line, "ascii"))

    def run(self):
        while True:
            # Try to connect with the server.  If not successful, try again,
            # but backoff exponentially for up to MAX_BACKOFF seconds
            try:
                self.tn = telnetlib.Telnet(self.server, LMS_TELNET_PORT)
                if self.login:
                    self.sendLine(command_string(f"login {self.login} {self.password}"))
                self.backoff = 1            # Reset the backoff time
                print(f"Connection complete with {self.server}")
            except Exception as e:
                print(e)
                print(f"Could not make connection.  Backing off for {self.backoff} seconds")
                time.sleep(self.backoff)
                self.backoff = min(MAX_BACKOFF, self.backoff * 2)
                continue

            try:
                # Try to get the player name for the player.
                # This will return nothing until the player is recognized.
                while True:
                    name_cmd = f"player name {self.player_id}"
                    self.sendLine(command_string(name_cmd, True))
                    line = self.getLine()
                    if line != name_cmd:
                        # if the returned line does not equal the command, it's got a name, indicatirng the player exists
                        #
                        break
                    time.sleep(.5)

                subscribe_cmd = command_string(f"{self.player_id} status - 1 subscribe:10")
                self.sendLine(subscribe_cmd)

                while True:
                    line = self.getLine()
                    # TODO: Check if we're the status command.

                    playmatch = playpat.search(line)
                    idmatch = idpat.search(line)
                    volmatch = volpat.search(line)

                    play = playmatch.group(1) if playmatch else None
                    song_id = idmatch.group(1) if idmatch else None
                    volume = volmatch.group(1) if volmatch else None

                    p = PlayEvent(play, song_id, volume)
                    self.queue.put(p)

            except (EOFError, ConnectionResetError) as e:
                print(f"Connection ended, retrying: {e}, {type(e)}")
            except ConnectionError as e:
                print(f"Other connection error: {e}")
            finally:
                if self.closed:
                    return


    def close(self):
        self.closed = True
        self.tn.close()


if __name__ == "__main__":
    q = queue.Queue()
    mon = PlayerMonitor("d8:3a:dd:55:b2:c9", "localhost", q)
    mon.start()

    for _ in range(5):
        thing = q.get()
        print(thing)

    mon.close()

