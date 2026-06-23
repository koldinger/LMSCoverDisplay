import socket

from collections import namedtuple


DISCOVERY_PORT = 3483
DEFAULT_DISCOVERY_TIMEOUT = 1

ATTR_HOST = "host"
ATTR_PORT = "port"

LmsInstance = namedtuple("LmsInstance", [ATTR_HOST, ATTR_PORT])

def discover_lms(timeout=DEFAULT_DISCOVERY_TIMEOUT):
    """ Scan network for Logitech Media Servers. """
    lms_ip = "<broadcast>"
    lms_port = DISCOVERY_PORT
    lms_msg = b"eJSON\0"

    entries = set()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    sock.bind(("", 0))

    try:
        sock.sendto(lms_msg, (lms_ip, lms_port))

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
