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

from datetime import datetime
from contextlib import suppress

def parsetime(timestr):
    with suppress(ValueError):
        return datetime.strptime(timestr, "%H:%M",).time()
    with suppress(ValueError):
        return datetime.strptime(timestr, "%I:%M%p").time()
    with suppress(ValueError):
        return datetime.strptime(timestr, "%H").time()
    with suppress(ValueError):
        return datetime.strptime(timestr, "%I%p").time()
    raise ValueError(f"Unable to parse time string: {timestr}")

def betweentimes(now, start, end):
    if not (start and end):
        return False
    if start <= end:
        return start <= now <= end
    return now <= end or now >= start


if __name__ == "__main__":
    for i in ["11pm", "23", "11:30pm", "11:30", "23:30", "24:30", "13pm"]:
        try:
            print(i, parsetime(i))
        except ValueError as e:
            print(e)

    print(betweentimes(parsetime("11"), parsetime("1"), parsetime("13")))
    print(betweentimes(parsetime("11"), parsetime("13"), parsetime("1")))
    print(betweentimes(parsetime("11"), parsetime("10"), parsetime("1")))
