#!/usr/bin/env python3
import argparse, random, socket, sys, time

REG_PORT, GAME_PORT = 5001, 5000


def register(server, name):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1.0)
    for attempt in range(1, 6):
        s.sendto(f"REG {name}".encode(), (server, REG_PORT))
        try:
            data, _ = s.recvfrom(1024)
            if data == b"ACK":
                print(f"[{name}] registered (attempt {attempt})", flush=True)
                time.sleep(0.3)
                return True
        except socket.timeout:
            print(f"[{name}] no ACK, retrying ({attempt}/5)", flush=True)
    return False


def play(server, name, count, interval):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0.2)
    rtts = []
    for seq in range(1, count + 1):
        t0 = time.time()
        x, y = random.randint(0, 100), random.randint(0, 100)
        s.sendto(f"UPD {name} {seq} {t0} {x} {y}".encode(), (server, GAME_PORT))
        try:
            while True:
                data, _ = s.recvfrom(1024)
                p = data.decode(errors="ignore").split()
                if len(p) == 4 and p[0] == "STATE" and int(p[1]) == seq:
                    rtts.append((time.time() - t0) * 1000)
                    break
        except socket.timeout:
            pass
        time.sleep(interval)
    got = len(rtts)
    loss = 100.0 * (count - got) / count
    avg = sum(rtts) / got if got else 0.0
    diffs = [abs(rtts[i] - rtts[i - 1]) for i in range(1, got)]
    jitter = sum(diffs) / len(diffs) if diffs else 0.0
    print(f"[{name}] sent={count} received={got} loss={loss:.1f}% "
          f"latency={avg:.2f}ms jitter={jitter:.2f}ms", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--server", default="10.0.0.10")
    ap.add_argument("--name", required=True)
    ap.add_argument("--count", type=int, default=30)
    ap.add_argument("--interval", type=float, default=0.1)
    ap.add_argument("--no-register", action="store_true")
    a = ap.parse_args()
    if not a.no_register and not register(a.server, a.name):
        print(f"[{a.name}] registration FAILED")
        sys.exit(1)
    play(a.server, a.name, a.count, a.interval)
