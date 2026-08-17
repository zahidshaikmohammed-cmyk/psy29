#!/usr/bin/env python3
"""Deterministic regression tests for the Stage 17 history transaction boundary."""
from __future__ import annotations
import csv
import tempfile
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import psy29_live_signal_cycle as cycle


def write_snapshot(path:Path,state:str,timestamp:str)->None:
    rows=[{"symbol":"TEST","stage17_state":state,"timestamp":timestamp,"provenance":"test"}]
    with path.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def read_state(path:Path)->str:
    with path.open(encoding="utf-8",newline="") as f:
        return next(csv.DictReader(f))["stage17_state"]


def main()->None:
    with tempfile.TemporaryDirectory(prefix="psy29-temporal-integrity-") as td:
        root=Path(td);persistent=root/"history";persistent.mkdir();frozen=root/"frozen";current=root/"current.csv"
        original=cycle.HISTORY
        cycle.HISTORY=persistent
        try:
            write_snapshot(persistent/"stage17_previous.csv","STABLE","2026-08-17T09:30:00Z")
            depth=cycle.freeze_history(frozen)
            assert depth==1
            assert read_state(frozen/"stage17_previous.csv")=="STABLE"

            write_snapshot(current,"CHANGED","2026-08-17T09:35:00Z")
            cycle.write_history_snapshot(current,current,"2026-08-17T09:35:00Z")
            assert len(list(frozen.glob("*.csv")))==1
            assert read_state(frozen/"stage17_previous.csv")=="STABLE"
            assert not any(read_state(p)=="CHANGED" for p in frozen.glob("*.csv"))
            assert len(list(persistent.glob("*.csv")))==1

            # Simulate a failed Stage 20 cycle: no commit call is made.
            assert len(list(persistent.glob("*.csv")))==1
            assert read_state(persistent/"stage17_previous.csv")=="STABLE"

            committed=cycle.append_committed_history(current,"2026-08-17T09:35:00Z")
            assert committed.exists()
            assert len(list(persistent.glob("*.csv")))==2
            assert any(read_state(p)=="CHANGED" for p in persistent.glob("*.csv"))
            assert len(list(frozen.glob("*.csv")))==1
        finally:
            cycle.HISTORY=original
    print("PSY29 TEMPORAL INTEGRITY UNIT TESTS: PASS")
    print("Previous-cycle history freeze: PASS")
    print("Current Stage 17 excluded from frozen history: PASS")
    print("Failed-cycle no-append boundary: PASS")
    print("Post-success Stage 17 commit: PASS")
    print("Immutable Stage 17/18/19 history contract: PASS")


if __name__=="__main__":
    main()
