#! /bin/bash
#
# Install the LMSCoverDisplay program.
# Run as root.

# Disable sound
sed -i s/dtparam=audio=on/dtparam=audio=off/ /boot/firmware/config.txt

# Enable isolcpus=3
sed -i "s/$/ isolcpus=3/" /boot/firmware/cmdline.txt

cat << EOF >> /etc/modprobe.d/blacklist-custom.conf
blacklist snd_bcm2835
EOF

# Import important packages
apt-get update
apt-get upgrade
apt install -y git i2c-tools python3-pip python3-setuptools procs btop fd-find bat

# Disable Externally Managed Python sntuff
rm /usr/lib/python3*/EXTERNALLY-MANAGED

# Install uv
pip install uv 

# Start installing files
cp ft-server /usr/local/bin

#uv pip install --system LMSTools
#uv pip install --system .

# Install service files
SERVICES=("ft-server.service" "lmsconfig.service" "lmsdisplay.service" "lmsremote.service")
cp "${SERVICES[@]}" /usr/lib/systemd/system
systemctl enable "${SERVICES[@]}"
