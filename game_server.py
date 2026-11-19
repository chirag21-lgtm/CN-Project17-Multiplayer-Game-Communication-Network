#!/usr/bin/env python3
import socket, sys, threading, time

REG_PORT, GAME_PORT = 5001, 5000
registered = {}
stats = {}
lock = threading.Lock()


def log(msg):
    print(f"[server {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def registration_loop():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", REG_PORT))
    log(f"registration socket on UDP {REG_PORT}")
    while True:
        data, addr = s.recvfrom(1024)
        p = data.decode(errors="ignore").split()
        if len(p) == 2 and p[0] == "REG":
            with lock:
                registered[addr[0]] = p[1]
                stats.setdefault(p[1], {"rx": 0, "last": 0, "lost": 0, "pos": None})
            log(f"REGISTERED {p[1]} ({addr[0]})")
            s.sendto(b"ACK", addr)


def game_loop():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", GAME_PORT))
    log(f"game socket on UDP {GAME_PORT}")
    while True:
        data, addr = s.recvfrom(1024)
        p = data.decode(errors="ignore").split()
        if len(p) != 6 or p[0] != "UPD" or not p[2].isdigit():
            continue
        seq, ts = int(p[2]), p[3]
        with lock:
            if addr[0] not in registered:
                log(f"IGNORED unregistered {addr[0]}")
                continue
            st = stats[registered[addr[0]]]
            st["rx"] += 1
            if seq > st["last"] + 1:
                st["lost"] += seq - st["last"] - 1
            st["last"] = max(st["last"], seq)
            st["pos"] = (p[4], p[5])
            players = len(registered)
        s.sendto(f"STATE {seq} {ts} {players}".encode(), addr)


if __name__ == "__main__":
    threading.Thread(target=registration_loop, daemon=True).start()
    threading.Thread(target=game_loop, daemon=True).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log("------- SUMMARY -------")
        with lock:
            for n, st in stats.items():
                log(f"{n}: received={st['rx']} lost={st['lost']} last_pos={st['pos']}")
        sys.exit(0)
