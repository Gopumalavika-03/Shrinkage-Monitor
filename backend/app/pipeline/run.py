"""One command for the whole pipeline.

    python -m app.pipeline.run --size small            # seconds, same code as full
    python -m app.pipeline.run --size full             # 100 stores, 5,000 SKUs, 1M baseline movements
    python -m app.pipeline.run --size full --repro     # run twice with the same seed, compare row counts + checksums
    python -m app.pipeline.run --size small --llm      # also write LLM plain-language alert summaries (needs LLM_* env vars)

Run from backend/. Output folder (default backend/output/<size>/):
    data/csv, data/json, data/shrinkage.sqlite   input tables (no anomaly labels anywhere)
    ground_truth/                                answer key -- the detector never reads it
    alerts/                                      shrinkage_alert, alert_evidence, investigation
    reports/                                     validation_summary.json, evaluation.json, manifest.json
"""
import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

from . import config
from . import detect
from . import generate
from . import validate
from .schema import TABLES, ddl

from .. import settings

OUTPUT_ROOT = settings.OUTPUT_DIR   # backend/output/<size> unless OUTPUT_DIR is set in backend/.env


def for_export(df):
    df = df.copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%Y-%m-%d %H:%M:%S")
    return df


def write(tables, folder):
    for sub in ("csv", "json"):
        (folder / sub).mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df = for_export(df)
        df.to_csv(folder / "csv" / f"{name}.csv", index=False, lineterminator="\n")
        df.to_json(folder / "json" / f"{name}.jsonl", orient="records", lines=True, force_ascii=False)


def write_sqlite(tables, path):
    """Schema with PK/FK constraints, then data; returns the number of foreign-key violations."""
    con = sqlite3.connect(path)
    con.executescript(ddl())
    for name in TABLES:
        if name in tables:
            for_export(tables[name]).to_sql(name, con, if_exists="append", index=False, chunksize=50_000)
    con.commit()
    bad = len(con.execute("PRAGMA foreign_key_check").fetchall())
    con.close()
    return bad


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def make_manifest(out, size):
    files = {}
    for p in sorted(out.rglob("*")):
        if p.suffix in (".csv", ".jsonl") or (p.parent.name == "reports" and p.name not in ("manifest.json", "reproducibility.json")):
            with open(p, "rb") as f:
                lines = sum(1 for _ in f)
            rows = lines - 1 if p.suffix == ".csv" else lines
            files[p.relative_to(out).as_posix()] = {"rows": rows if p.suffix in (".csv", ".jsonl") else None,
                                                    "sha256": sha256(p)}
    combined = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {"seed": config.SEED, "size": size, "combined_sha256": combined, "files": files}


def dump(obj, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8", newline="\n")


def run(size="small", out=None, llm=False, quiet=False):
    out = Path(out) if out else OUTPUT_ROOT / size
    shutil.rmtree(out, ignore_errors=True)
    t0 = time.time()
    say = (lambda *a: None) if quiet else (lambda msg: print(f"[{time.time() - t0:6.1f}s] {msg}", flush=True))

    tables, gt = generate.generate(size)
    say(f"generated {len(tables['inventory_movement']):,} movements, {len(gt)} ground-truth cases")
    write(tables, out / "data")
    write({"anomalies": gt}, out / "ground_truth")
    say("exported input data + ground truth")

    alerts = detect.detect(out / "data")          # reads the CSVs only
    write(alerts, out / "alerts")
    say(f"detector raised {len(alerts['shrinkage_alert'])} alerts")

    summary = validate.validate({**tables, **alerts})
    summary["sqlite_foreign_key_violations"] = write_sqlite({**tables, **alerts}, out / "data" / "shrinkage.sqlite")
    summary["integrity_passed"] &= summary["sqlite_foreign_key_violations"] == 0
    dump(summary, out / "reports" / "validation_summary.json")
    ev = detect.evaluate(alerts, gt, out / "data")
    dump(ev, out / "reports" / "evaluation.json")
    say(f"validation integrity passed: {summary['integrity_passed']}")

    if llm:
        from . import llm as llm_mod
        llm_mod.narrate(alerts["shrinkage_alert"], out / "alerts" / "alert_narratives_llm.json")
        say("wrote LLM alert summaries (not checksummed)")

    manifest = make_manifest(out, size)
    dump(manifest, out / "reports" / "manifest.json")
    if not quiet:
        print(pd.DataFrame(ev["per_type"]).to_string(index=False))
        print("innocent checks:", ev["innocent_checks"])
        say(f"done -> {out}  (combined sha256 {manifest['combined_sha256'][:16]}...)")
    return summary, ev, manifest


def repro(size, out=None, quiet=False):
    """Run into `out`, run again in a *separate Python process* into a scratch folder (so nothing in memory,
    e.g. hash order, is shared), compare every file's rows + SHA-256, keep only `out`."""
    out = Path(out) if out else OUTPUT_ROOT / size
    check = out.with_name(out.name + "_repro_check")
    a = run(size, out, quiet=quiet)[2]
    subprocess.run([sys.executable, "-m", "app.pipeline.run", "--size", size, "--out", str(check)],
                   cwd=Path(__file__).resolve().parents[2], check=True, capture_output=True)
    b = json.loads((check / "reports" / "manifest.json").read_text(encoding="utf-8"))
    shutil.rmtree(check, ignore_errors=True)
    diff = sorted(k for k in a["files"].keys() | b["files"].keys() if a["files"].get(k) != b["files"].get(k))
    result = {"seed": config.SEED, "size": size, "files_compared": len(a["files"]), "identical": not diff,
              "differences": diff, "combined_sha256_run_a": a["combined_sha256"], "combined_sha256_run_b": b["combined_sha256"],
              "row_counts": {k: v["rows"] for k, v in a["files"].items() if k.endswith(".csv")}}
    dump(result, out / "reports" / "reproducibility.json")   # written after the manifest, so not part of it
    print(f"reproducible: {result['identical']} ({len(a['files'])} files, combined sha256 {a['combined_sha256'][:16]}...)")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--size", choices=list(config.SIZES), default="small")
    ap.add_argument("--out", help="output folder (default OUTPUT_DIR/<size>, i.e. backend/output/<size>)")
    ap.add_argument("--repro", action="store_true", help="run twice and compare checksums")
    ap.add_argument("--llm", action="store_true", help="add LLM plain-language alert summaries")
    args = ap.parse_args()
    if args.repro:
        sys.exit(0 if repro(args.size, args.out)["identical"] else 1)
    summary = run(args.size, args.out, llm=args.llm)[0]
    sys.exit(0 if summary["integrity_passed"] else 1)
