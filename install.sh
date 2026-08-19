#! /bin/bash
#
# Install the LMSCoverDisplay program.
# Run as root.

# Disable sound
sed -i s/dtparam=audio=on/dtparam=audio=off/ /boot/firmware/config.txt
sed -i s/#dtparam=i2c_arm/dtparam=i2c_arm/ /boot/firmware/config.txt

# Enable isolcpus=3
sed -i "s/$/ isolcpus=domain,managed_irq,3 nohz_full=3 rcu_nocbs=3 irqaffinity=0,1,2/" /boot/firmware/cmdline.txt

cat << EOF >> /etc/modprobe.d/blacklist-custom.conf
blacklist snd_bcm2835
EOF

cat << EOF >> /etc/modules-load.d/i2c_dev.conf
i2c_dev
EOF

# Import important packages
apt update -y
apt upgrade -y
apt install -y git i2c-tools python3-pip python3-setuptools procs btop fd-find bat

# Disable Externally Managed Python sntuff
rm /usr/lib/python3*/EXTERNALLY-MANAGED

# Install uv
pip install uv 

# Start installing files
#cp ft-server /usr/local/bin

#uv pip install --system LMSTools

#uv pip install --system git+https://github.com/hzeller/rpi-rgb-led-matrix.git
#uv pip install --system .

uv pip install --system git+https://github.com/koldinger/WifiSelect
#uv pip install --system git+https://github.com/koldinger/WifiSelect

# Install service files
SERVICES=("ft-server.service" "lmsconfig.service" "lmsdisplay.service" "lmsremote.service" "wifiselect.service")

cp "${SERVICES[@]}" /usr/lib/systemd/system
systemctl enable "${SERVICES[@]}"
