#!/bin/bash
set -e
sudo apt update
sudo apt install -y mininet openvswitch-switch python3-pip netcat-openbsd iperf
sudo systemctl enable --now openvswitch-switch || true
if ! command -v ryu-manager >/dev/null; then
  sudo apt install -y python3-ryu || pip3 install --user setuptools==67.6.1 eventlet==0.30.2 ryu
fi
export PATH=$PATH:$HOME/.local/bin
grep -q '.local/bin' ~/.bashrc || echo 'export PATH=$PATH:$HOME/.local/bin' >> ~/.bashrc
echo "---- checks ----"; which mn ryu-manager ovs-vsctl
