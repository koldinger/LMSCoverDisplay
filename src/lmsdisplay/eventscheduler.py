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

import time
import heapq
from threading import Event, RLock, Thread
from dataclasses import dataclass, field
from collections.abc import Callable
import datetime as dt

from icecream import ic

@dataclass(order=True)
class EventData:
    runtime: int
    event_id: int
    action: Callable=field(compare=False)
    arguments: list=field(compare=False)
    kwargs : dict=field(compare=False)
    valid: bool=field(compare=False, default=True)

class EventScheduler:
    def __init__(self):
        self._queue = []
        self._lock = RLock()
        self._event = Event()
        self._sequence = 0  # Unique ID provider for entries and cancellation
        self._stop = False

    def enterabs(self, time_to_run, action, argument=(), kwargs=None) -> EventData:
        """Schedule an event at an absolute timestamp (e.g., time.time() + 10)."""
        if kwargs is None:
            kwargs = {}

        with self._lock:
            event_id = self._sequence
            self._sequence += 1

            # Entry format: (time_to_run, sequence, action, argument, kwargs, active)
            # The 'active' list wrapper allows cancellation without expensive heap removal
            ic(time_to_run, event_id, action, argument)
            entry = EventData(time_to_run, event_id, action, argument, kwargs)
            heapq.heappush(self._queue, entry)

            # Wake up the run loop in case this new event is now the earliest
            self._event.set()
            return entry  # Return the entry handle for cancellation

    def enter(self, delay, action, argument=(), kwargs=None) -> EventData:
        """Schedule an event to run after a relative delay in seconds."""
        return self.enterabs(time.time() + delay, action, argument, kwargs)

    def cancel(self, event_handle):
        """Cancel a scheduled event using its returned handle."""
        if not event_handle:
            return
        with self._lock:
            # Mark the inner active flag as False
            event_handle.valid = False
            # Wake up loop to clean it up if it was at the top of the queue
            self._event.set()

    def stop(self):
        with self._lock:
            self._stop = True
            self._event.set()

    def run(self, once=False, until_empty=False):
        """Run the scheduler loop continuously."""
        while True:
            if self._stop:
                break

            with self._lock:
                # Discard canceled or invalid items sitting at the top of the heap
                while self._queue and not self._queue[0].valid:
                    heapq.heappop(self._queue)

                if not self._queue:
                    # Clear the event and wait indefinitely until a new item is added
                    self._event.clear()
                    wait_time = None
                else:
                    time_to_run = self._queue[0].runtime
                    now = time.time()

                    if now >= time_to_run:
                        # Time to execute: pop item from heap
                        # _, _, _, action, argument, kwargs, active = heapq.heappop(self._queue)
                        event  = heapq.heappop(self._queue)
                        wait_time = 0
                    else:
                        wait_time = time_to_run - now
                        self._event.clear()

            # Wait outside the lock if we aren't executing an item immediately
            if wait_time is None:
                self._event.wait()
                continue
            elif wait_time > 0:
                self._event.wait(timeout=wait_time)
                continue

            # Execute the action safely outside the lock to prevent deadlocks
            event.action(*event.arguments, **event.kwargs)

            if once or (until_empty and self.empty()):
                break


    def empty(self):
        """Return True if the scheduler has no active events remaining."""
        with self._lock:
            # Clean up canceled items from the top of the heap to get an accurate count
            while self._queue and not self._queue[0].valid:
                heapq.heappop(self._queue)
            return len(self._queue) == 0

    def start_background(self):
        """Start the scheduler loop inside a background daemon thread."""
        thread = Thread(target=self.run, daemon=True)
        thread.start()
        return thread


if __name__ == "__main__":
    def doit(num):
        print(f"{num} -- {int(time.time() - start)}")

    s = EventScheduler()
    start = time.time()
    s.enter(30, doit, ("d 30 A", ))
    xx = s.enter(30, 0, doit, ("d 30 B", ))
    s.enter(20, doit, ("d 20 C", ))
    s.start_background()
    s.enter(10, doit, ("d 10 D", ))
    s.enter(5, doit, ("d 10 E", ))
    later = time.time() + 10
    s.enterabs(later, doit, ("a F", ))
    s.enterabs(later, doit, ("a G", ))
    s.enterabs(later, doit, ("a H", ))

    time.sleep(10)
    s.cancel(xx)

    while not s.empty():
        print("-")
        time.sleep(5)
