#!/usr/bin/env python3
import os, re, subprocess
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel

HERE = os.path.dirname(os.path.abspath(__file__))
LINE = re.compile(r"\[(\w+)\] sent=(\d+) received=(\d+) loss=([\d.]+)% "
                  r"latency=([\d.]+)ms jitter=([\d.]+)ms")


def set_mode(mode):
    open(os.path.join(HERE, "mode.txt"), "w").write(mode)


def build(loss=0):
    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=True)
    net.addController("c0", controller=RemoteController, ip="127.0.0.1", port=6653)
    s1 = net.addSwitch("s1", protocols="OpenFlow13")
    for name, ip in [("gs", "10.0.0.10"), ("p1", "10.0.0.1"), ("p2", "10.0.0.2"),
                     ("p3", "10.0.0.3"), ("bg", "10.0.0.20")]:
        opts = {"loss": loss} if (name == "p1" and loss) else {}
        net.addLink(net.addHost(name, ip=ip + "/24"), s1, **opts)
    return net


def setup_queues():
    for what in ("qos", "queue"):
        subprocess.run(["ovs-vsctl", "--all", "destroy", what], capture_output=True)
    subprocess.run([
        "ovs-vsctl", "set", "port", "s1-eth1", "qos=@q", "--",
        "--id=@q", "create", "qos", "type=linux-htb", "other-config:max-rate=10000000",
        "queues:0=@q0", "queues:1=@q1", "--",
        "--id=@q0", "create", "queue", "other-config:min-rate=1000000",
        "other-config:max-rate=10000000", "other-config:priority=1", "--",
        "--id=@q1", "create", "queue", "other-config:min-rate=5000000",
        "other-config:max-rate=10000000", "other-config:priority=0"], check=True)


def play(net, players, extra=""):
    procs = [net.get(h).popen(f"python3 game_client.py --name {h} {extra}",
                              cwd=HERE, stdout=subprocess.PIPE, text=True) for h in players]
    out = []
    for pr in procs:
        text = pr.communicate()[0].strip()
        print(text, flush=True)
        m = LINE.search(text)
        if m:
            out.append((m[1], int(m[2]), int(m[3]), float(m[4]), float(m[5]), float(m[6])))
    return out


if __name__ == "__main__":
    setLogLevel("info")
    net = build()
    net.start()
    setup_queues()
    CLI(net)
    net.stop()
