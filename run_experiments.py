#!/usr/bin/env python3
import argparse, csv, os, subprocess, sys, time
from mininet.log import setLogLevel
from topo import build, setup_queues, set_mode, play, HERE

GROUP_A = [("idle", "dynamic", False), ("flood_baseline", "baseline", True),
           ("flood_static", "static", True), ("flood_dynamic", "dynamic", True)]
GROUP_B = [("loss5_flood_baseline", "baseline", True), ("loss5_flood_dynamic", "dynamic", True)]


def run_group(scenarios, loss, runs, rows):
    net = build(loss)
    net.start()
    setup_queues()
    time.sleep(3)
    gs, bg = net.get("gs"), net.get("bg")
    server = gs.popen("python3 game_server.py", cwd=HERE, stdout=subprocess.DEVNULL)
    gs.popen("iperf -u -s -p 5002", stdout=subprocess.DEVNULL)
    time.sleep(1)
    for name, mode, flood in scenarios:
        for r in range(1, runs + 1):
            print(f"\n=== {name} (run {r}/{runs}) ===", flush=True)
            set_mode(mode)
            f = None
            if flood:
                f = bg.popen("iperf -u -c 10.0.0.10 -p 5002 -b 20M -t 120", stdout=subprocess.DEVNULL)
                time.sleep(0.5)
            for (p, sent, got, loss_pct, lat, jit) in play(net, ["p1", "p2"], "--count 100"):
                rows.append((name, r, p, loss_pct, lat, jit))
            if f:
                f.terminate()
            time.sleep(5)
    server.terminate()
    net.stop()
    subprocess.run(["pkill", "iperf"])


def summarise(rows):
    keys = []
    for row in rows:
        k = (row[0], row[2])
        if k not in keys:
            keys.append(k)
    lines = ["| Scenario | Player | Loss % | Latency ms | Jitter ms |", "|---|---|---|---|---|"]
    table = []
    for (sc, pl) in keys:
        sel = [x for x in rows if x[0] == sc and x[2] == pl]
        avg = [sum(x[i] for x in sel) / len(sel) for i in (3, 4, 5)]
        table.append((sc, pl, *avg))
        lines.append(f"| {sc} | {pl} | {avg[0]:.1f} | {avg[1]:.1f} | {avg[2]:.1f} |")
    return "\n".join(lines), table


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    a = ap.parse_args()
    setLogLevel("warning")
    os.chdir(HERE)
    os.makedirs("results", exist_ok=True)
    rows = []
    run_group(GROUP_A, 0, a.runs, rows)
    run_group(GROUP_B, 5, a.runs, rows)
    with open("results/results.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scenario", "run", "player", "loss_pct", "latency_ms", "jitter_ms"])
        w.writerows(rows)
    md, table = summarise(rows)
    open("results/summary.md", "w").write(md + "\n")
    print("\n" + md)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        sel = [t for t in table if t[1] == "p2"]
        fig, ax = plt.subplots(1, 3, figsize=(13, 4))
        for i, (title, unit) in enumerate([("Latency", "ms"), ("Jitter", "ms"), ("Packet loss", "%")]):
            col = [4, 5, 3][i]
            ax[i].bar([t[0] for t in sel], [t[col] for t in sel])
            ax[i].set_title(f"{title} ({unit}) - player p2")
            ax[i].tick_params(axis="x", rotation=60)
        plt.tight_layout()
        plt.savefig("results/comparison.png", dpi=150)
    except Exception as e:
        print("plot skipped:", e)
    print("Saved results/results.csv, summary.md, comparison.png")
