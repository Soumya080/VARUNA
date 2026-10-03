"""NETRA v0.3-B1 long-run monitor. Appends a status record to
monitor.jsonl and prints the human-readable panel. Read-only w.r.t. training."""
import json
import os, os, shutil, subprocess, sys, time, datetime
from pathlib import Path
OUT = Path(os.environ.get("B1_OUT", "artifacts/experiments/netra_v03/pilot_01_run2"))
EPOCHS = 30

def gpu():
    try:
        o = subprocess.check_output(["nvidia-smi",
            "--query-gpu=utilization.gpu,memory.used,memory.free","--format=csv,noheader,nounits"],
            text=True).strip().split(", ")
        return {"gpu_util_pct": int(o[0]), "vram_used_mb": int(o[1]), "vram_free_mb": int(o[2])}
    except Exception:
        return {"gpu_util_pct": None, "vram_used_mb": None, "vram_free_mb": None}

def alive():
    try:
        o = subprocess.check_output(["tasklist","/FI","IMAGENAME eq python.exe"],text=True)
        return "python.exe" in o
    except Exception:
        return None

def main():
    mf = OUT/"metrics.jsonl"
    if not mf.exists():
        print("no metrics yet"); return
    rows = [json.loads(l) for l in mf.read_text().splitlines() if l.strip()]
    rows = [r for r in rows if "step" in r and "loss_total" in r]
    if not rows:
        print("no metric rows yet"); return
    last = rows[-1]
    steps_per_epoch = json.load(open(OUT/"runtime_estimate.json"))["steps_per_epoch"]
    done = last["epoch"]*steps_per_epoch + last["step"]
    total = EPOCHS*steps_per_epoch
    elapsed = last["elapsed_s"]
    sps = elapsed/max(done,1)                      # measured, recomputed every poll
    remain = (total-done)*sps
    start = datetime.datetime.fromtimestamp(os.path.getmtime(OUT/"run_metadata.json"))
    nant = sum(1 for l in mf.read_text().splitlines() if l.strip() and json.loads(l).get("nan_guard"))
    ck = OUT/"last.pt"
    ck_age = (time.time()-ck.stat().st_mtime)/60 if ck.exists() else None
    du = shutil.disk_usage(".")
    try:
        import psutil; ram = psutil.virtual_memory()
        ram_used, ram_tot = ram.used/1e9, ram.total/1e9
    except Exception:
        ram_used = ram_tot = None
    g = gpu()
    rec = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
           "epoch": last["epoch"], "step": last["step"], "global_step": done,
           "progress_pct": round(100*done/total,2), "elapsed_s": elapsed,
           "measured_s_per_step": round(sps,4), "eta_s": round(remain),
           "eta_h": round(remain/3600,2),
           "expected_completion": (datetime.datetime.now()+datetime.timedelta(seconds=remain)).isoformat(timespec="seconds"),
           "loss_total": last["loss_total"], "loss_strong": last["loss_strong"],
           "loss_weak_negative": last["loss_weak_negative"], "loss_mil": last["loss_mil"],
           "grad_norm": last["grad_norm"], "n_boxes": last.get("n_boxes"),
           "disk_free_gb": round(du.free/1e9,1), "ram_used_gb": round(ram_used,1) if ram_used else None,
           "ram_total_gb": round(ram_tot,1) if ram_tot else None,
           "checkpoint_age_min": round(ck_age,1) if ck_age is not None else None,
           "nan_guard_trips": nant, "process_alive": alive(), **g}
    with open(OUT/"monitor.jsonl","a") as fh: fh.write(json.dumps(rec)+"\n")
    print("-"*50)
    print("NETRA v0.3-B1 TRAINING STATUS")
    print("-"*50)
    print(f"Started:              {start.isoformat(timespec='seconds')}")
    print(f"Elapsed:              {elapsed/3600:.2f} h")
    print(f"ETA:                  {rec['eta_h']:.2f} h")
    print(f"Expected completion:  {rec['expected_completion']}")
    print(f"Epoch:                {rec['epoch']+1}/{EPOCHS}")
    print(f"Step:                 {rec['step']}/{steps_per_epoch}")
    print(f"Progress:             {rec['progress_pct']:.2f}%   ({done}/{total} steps)")
    print(f"Train loss:           {rec['loss_total']:.4f}")
    print(f"Strong loss:          {rec['loss_strong']:.4f}")
    print(f"Weak loss:            {rec['loss_weak_negative']:.4f}")
    print(f"MIL loss:             {rec['loss_mil']:.4f}")
    print(f"Grad norm:            {rec['grad_norm']:.3f}")
    print(f"GPU:                  {g['gpu_util_pct']}%")
    print(f"VRAM:                 {g['vram_used_mb']} MiB used / {g['vram_free_mb']} MiB free")
    print(f"RAM:                  {rec['ram_used_gb']}/{rec['ram_total_gb']} GB")
    print(f"Disk:                 {rec['disk_free_gb']} GB free")
    print(f"Checkpoint:           {rec['checkpoint_age_min']} min old" if rec['checkpoint_age_min'] is not None else "Checkpoint:           none yet (written at epoch end)")
    print(f"NaN guard trips:      {rec['nan_guard_trips']}")
    print(f"Status:               {'RUNNING' if rec['process_alive'] else 'NOT DETECTED'}")
    print("-"*50)

if __name__ == "__main__":
    main()
