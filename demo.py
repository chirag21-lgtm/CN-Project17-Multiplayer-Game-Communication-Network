#!/usr/bin/env python3
import os, subprocess, sys, time
from mininet.log import setLogLevel
from topo import build, setup_queues, set_mode, play, HERE

OUT = []


def say(t):
    print(t, flush=True)
    OUT.append(t)


def run(args):
    return subprocess.run(args, capture_output=True, text=True).stdout


if __name__ == "__main__":
    setLogLevel("warning")
    os.chdir(HERE)
    os.makedirs("results", exist_ok=True)
    set_mode("dynamic")
    net = build()
    net.start()
    setup_queues()
    time.sleep(3)
    gs, bg = net.get("gs"), net.get("bg")

    say("=== TEST 1: connectivity (pingall) - expect 0% dropped ===")
    say(f"dropped: {net.pingAll()}%")
    server = gs.popen("python3 game_server.py", stdout=open("results/server.log", "w"), text=True)
    gs.popen("iperf -u -s -p 5002", stdout=subprocess.DEVNULL)
    time.sleep(1)

    say("\n=== TEST 2: UNAUTHORIZED p3 plays without registering - expect 100% loss ===")
    say(str(play(net, ["p3"], "--no-register --count 10")))

    say("\n=== TEST 3: p1,p2,p3 register and play, NO congestion - expect 0% loss ===")
    say(str(play(net, ["p1", "p2", "p3"])))
    say("\nFlow table (priority=30 rules = one per registered player, no set_queue yet):")
    say(run(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "s1"]))

    say("=== TEST 4: CONGESTION, BASELINE mode (no priority) ===")
    set_mode("baseline")
    flood = bg.popen("iperf -u -c 10.0.0.10 -p 5002 -b 20M -t 120", stdout=subprocess.DEVNULL)
    time.sleep(2)
    say(str(play(net, ["p1", "p2"], "--count 60")))
    flood.terminate(); time.sleep(5)

    say("\n=== TEST 5: CONGESTION, DYNAMIC mode (watch controller: congestion_detected) ===")
    set_mode("dynamic")
    flood = bg.popen("iperf -u -c 10.0.0.10 -p 5002 -b 20M -t 120", stdout=subprocess.DEVNULL)
    time.sleep(0.5)
    say(str(play(net, ["p1", "p2"], "--count 60")))
    say("\nFlow table during congestion (now set_queue:1 appears on priority=30 rules):")
    say(run(["ovs-ofctl", "-O", "OpenFlow13", "dump-flows", "s1"]))
    say(run(["tc", "-s", "class", "show", "dev", "s1-eth1"]))
    flood.terminate()
    time.sleep(5)
    say("(after the flood stops, controller prints congestion_cleared)")

    server.send_signal(2)
    time.sleep(1)
    say(open("results/server.log").read())
    net.stop()
    subprocess.run(["pkill", "iperf"])
    open("results/d1_output.txt", "w").write("\n".join(OUT))
    print("Saved results/d1_output.txt")
