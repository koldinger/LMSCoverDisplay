import qrcode
import psutil
import socket

CONFIG_PORT=5000

def get_ip_address(ifname):
    interfaces = psutil.net_if_addrs()
    if ifname in interfaces:
        for addr in interfaces[ifname]:
            if addr.family == socket.AF_INET:
                return addr.address
    return None


def generate_config_qrcode(ifname):
    qr = qrcode.QRCode(version=2, box_size=2, border=3)
    hostaddr = get_ip_address(ifname)
    #hostaddr = socket.gethostname()
    url = f"http:{hostaddr}:{CONFIG_PORT}"
    print(url)
    qr.add_data(url)
    q = qr.make_image(fill_color="black", back_color="cyan")

    return q.get_image()

def generate_wifi_qrcode(ssid):
    qr = qrcode.QRCode(version=2, box_size=2, border=1)
    data = f"WIFI:T:nopass;P:S:{ssid};;"
    print(data, len(data))
    qr.add_data(data)
    q = qr.make_image(fill_color="black", back_color="green")

    return q.get_image()


if __name__ == "__main__":
    import flaschen
    def sendArt(f, i):
        px = i.load()
        for x in range(i.width):
            for y in range(i.height):
                f.set(x, y, px[x, y])
        f.send()

    import imgcat
    #q = generate_config_qrcode("enp7s0")
    q = generate_wifi_qrcode("cover-connect123")
    imgcat.imgcat(q)

    display = "coverpi2.local"
    f = flaschen.Flaschen(display, 1337, 64, 64)
    sendArt(f, q)

