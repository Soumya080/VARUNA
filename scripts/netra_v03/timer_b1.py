"""NETRA v0.3-B1 LIVE TIMER — refreshes in place, shows epoch progress.

Run in your own terminal:
    ./.venv/Scripts/python.exe scripts/netra_v03/timer_b1.py
    ./.venv/Scripts/python.exe scripts/netra_v03/timer_b1.py --interval 5

Read-only. Ctrl+C to quit; it never touches the training run.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import time
from pathlib import Path

OUT = Path(os.environ.get("B1_OUT", "artifacts/experiments/netra_v03/pilot_01_run2"))
EPOCHS = 30


def gpu():
    try:
        o = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used",
             "--format=csv,noheader,nounits"], text=True).strip().split(", ")
        return int(o[0]), int(o[1])
    except Exception:
        return None, None


def bar(frac, width=42):
    frac = max(0.0, min(1.0, frac))
    n = int(frac * width)
    return "#" * n + "-" * (width - n)


def hms(seconds):
    if seconds is None or seconds < 0:
        return "--:--:--"
    s = int(seconds)
    return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=10, help="refresh seconds")
    args = ap.parse_args()

    steps_per_epoch = json.load(open(OUT / "runtime_estimate.json"))["steps_per_epoch"]
    total = EPOCHS * steps_per_epoch
    mf = OUT / "metrics.jsonl"

    while True:
        rows = []
        if mf.exists():
            for line in mf.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if "step" in r and "loss_total" in r:
                    rows.append(r)
        if not rows:
            print("waiting for first metrics...", end="\r")
            time.sleep(args.interval)
            continue

        last = rows[-1]
        ep, st = last["epoch"], last["step"]
        done = ep * steps_per_epoch + st
        elapsed = last["elapsed_s"]
        sps = elapsed / max(done, 1)
        eta = (total - done) * sps
        epoch_eta = (steps_per_epoch - st) * sps

        # recent MIL activity: last 25 logged steps that actually had a box
        # alias-proof: window means cover EVERY step since the previous log
        if "win_loss_mil" in last:
            mil_txt = (f"{last['win_loss_mil']:.4f}  "
                       f"[{last['win_steps_with_box']}/{last['win_steps']} steps had a box, "
                       f"{last['win_boxes']} boxes]")
            wneg_txt = f"{last['win_loss_weak_negative']:.4f}"
            strong_txt = f"{last['win_loss_strong']:.4f}"
            total_txt = f"{last['win_loss_total']:.4f}"
        else:
            mil_txt = "n/a (pre-fix run)"
            wneg_txt = f"{last['loss_weak_negative']:.4f}"
            strong_txt = f"{last['loss_strong']:.4f}"
            total_txt = f"{last['loss_total']:.4f}"

        util, vram = gpu()
        du = shutil.disk_usage(".")
        ck = OUT / "last.pt"
        ck_age = (time.time() - ck.stat().st_mtime) / 60 if ck.exists() else None
        nan_trips = sum(1 for l in mf.read_text().splitlines()
                        if l.strip() and '"nan_guard"' in l)
        eta_done = datetime.datetime.now() + datetime.timedelta(seconds=eta)

        os.system("cls" if os.name == "nt" else "clear")
        print("=" * 62)
        print("  NETRA v0.3-B1  ·  LIVE TRAINING TIMER   (window means)")
        print("=" * 62)
        print(f"  EPOCH  {ep+1:>2}/{EPOCHS}   [{bar(st/steps_per_epoch)}] {100*st/steps_per_epoch:5.1f}%")
        print(f"         step {st:>5}/{steps_per_epoch}      epoch ETA  {hms(epoch_eta)}")
        print()
        print(f"  TOTAL        [{bar(done/total)}] {100*done/total:5.2f}%")
        print(f"         step {done:>6}/{total}")
        print("-" * 62)
        print(f"  Elapsed            {hms(elapsed)}")
        print(f"  Remaining          {hms(eta)}   ({eta/3600:.2f} h)")
        print(f"  Expected finish    {eta_done.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Measured s/step    {sps:.4f}")
        print("-" * 62)
        print(f"  Loss total         {total_txt}")
        print(f"  Loss strong        {strong_txt}")
        print(f"  Loss weak-neg      {wneg_txt}")
        print(f"  Loss MIL           {mil_txt}")
        print(f"  Grad norm          {last['grad_norm']:.3f}   (clip 5.0)")
        print("-" * 62)
        print(f"  GPU                {util}%   VRAM {vram} MiB")
        print(f"  Disk free          {du.free/1e9:.1f} GB")
        print(f"  Last checkpoint    {f'{ck_age:.1f} min ago' if ck_age is not None else 'none yet (written at epoch end)'}")
        print(f"  NaN-guard trips    {nan_trips}")
        print("=" * 62)
        print(f"  refreshing every {args.interval}s · Ctrl+C to exit")
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
