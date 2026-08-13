#!/usr/bin/env python3
"""PSY29 Stage 13 - Live Scenario Adjudication & Trigger-Integrity Gate."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

STATES = {
    "SCENARIO_CONFIRMED", "SCENARIO_CONDITIONAL", "SCENARIO_UNCONFIRMED",
    "SCENARIO_CONFLICTED", "DATA_STALE", "DATA_INVALID", "UPSTREAM_INVALID",
}
SCENARIOS = {"CONTINUATION", "BREAKOUT", "BREAKDOWN", "RETEST", "REVERSAL_RISK", "RANGE", "TRANSITION", "UNCLEAR"}
SAFETY = {
    "trade_ready_output": False, "trade_authorized": False,
    "trade_signal_generated": False, "ce_pe_selection": False,
    "entry_calculation": False, "stop_loss_calculation": False,
    "target_calculation": False, "position_size_calculation": False,
    "risk_calculation": False, "capital_allocation": False,
    "order_generation": False, "execution": False,
}
PROV = [
    "research_provenance", "stage6_provenance", "stage7_provenance", "stage8_provenance",
    "stage9_provenance", "stage10_provenance", "stage11_provenance", "stage12_provenance",
]


def load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def universe(path: str) -> tuple[list[str], dict[str, int]]:
    rows = load_json(path).get("universe", [])
    if len(rows) != 29:
        raise ValueError("Canonical universe must contain exactly 29 rows")
    symbols = [str(r.get("symbol", "")).upper().strip() for r in rows]
    ranks = [int(r.get("rank", 0)) for r in rows]
    if any(not s for s in symbols) or len(set(symbols)) != 29:
        raise ValueError("Canonical universe has empty/duplicate symbols")
    if ranks != list(range(1, 30)):
        raise ValueError("Canonical ranks must be 1-29")
    return symbols, dict(zip(symbols, ranks))


def profiles(path: str, expected: set[str]) -> None:
    rows = load_json(path).get("profiles", [])
    if len(rows) != 29:
        raise ValueError("Stage 5 must contain 29 profiles")
    actual = [str(r.get("symbol", "")).upper().strip() for r in rows]
    if len(set(actual)) != 29 or set(actual) != expected:
        raise ValueError("Stage 5 profile coverage mismatch")


def table(path: str, name: str, expected: set[str], fields: set[str]) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing {name}: {p}")
    df = pd.read_csv(p)
    missing = fields - set(df.columns)
    if missing:
        raise ValueError(f"{name} missing fields: {sorted(missing)}")
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    if len(df) != 29 or df["symbol"].nunique() != 29 or set(df["symbol"]) != expected:
        raise ValueError(f"{name} must have exactly the canonical 29")
    return df.set_index("symbol")


def nonempty(v: Any) -> bool:
    return str(v).strip().lower() not in {"", "nan", "none", "null"}


def fresh(ts: Any, now: datetime) -> bool:
    dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("live timestamp must be timezone-aware")
    age = (now - dt.astimezone(timezone.utc)).total_seconds()
    if age < -5:
        raise ValueError("live timestamp is materially in the future")
    return age <= 180


def scenario_from_stage12(v: Any) -> str:
    s = str(v).upper().strip()
    return {
        "CONTINUATION_SCENARIO": "CONTINUATION", "BREAKOUT_SCENARIO": "BREAKOUT",
        "BREAKDOWN_SCENARIO": "BREAKDOWN", "RETEST_SCENARIO": "RETEST",
        "REVERSAL_RISK_SCENARIO": "REVERSAL_RISK", "RANGE_SCENARIO": "RANGE",
        "TRANSITION_SCENARIO": "TRANSITION", "UNCLEAR_SCENARIO": "UNCLEAR",
    }.get(s, s if s in SCENARIOS else "UNCLEAR")


def scenario_from_structure(v: Any) -> str:
    return {
        "BREAKOUT_STRUCTURE": "BREAKOUT", "BREAKDOWN_STRUCTURE": "BREAKDOWN",
        "TRENDING_UP": "CONTINUATION", "TRENDING_DOWN": "CONTINUATION",
        "RANGE": "RANGE", "TRANSITION": "TRANSITION", "UNCLEAR": "UNCLEAR",
    }.get(str(v).upper().strip(), "UNCLEAR")


def regime_family(v: Any) -> str:
    s = str(v).upper().strip()
    if "BREAKOUT" in s: return "BREAKOUT"
    if "BREAKDOWN" in s: return "BREAKDOWN"
    if "RANGE" in s or "NEUTRAL" in s: return "RANGE"
    if "TRANSITION" in s: return "TRANSITION"
    if "BULL" in s or "BEAR" in s or "UP" in s or "DOWN" in s: return "CONTINUATION"
    return "UNCLEAR"


def ev(source: str, state: str, detail: str) -> dict[str, str]:
    return {"source": source, "state": state, "detail": detail}


def conditions(s: str) -> tuple[str, str]:
    return {
        "BREAKOUT": ("Breakout structure remains intact with confirming live price/volume behaviour.", "Breakout structure fails and price returns into the prior structural range."),
        "BREAKDOWN": ("Breakdown structure remains intact with confirming live price/volume behaviour.", "Breakdown structure fails and price returns into the prior structural range."),
        "CONTINUATION": ("Directional structure remains coherent with continued supporting price/volume behaviour.", "Directional structure loses coherence or develops material contradictory evidence."),
        "RETEST": ("The retest holds the referenced structural level and subsequent structure remains coherent.", "The referenced structural level fails and the retest loses structural validity."),
        "RANGE": ("Price remains contained within the identified range with no decisive structural break.", "A decisive structural break invalidates the range scenario."),
        "TRANSITION": ("Additional live structure confirms a stable directional or range regime.", "Transition evidence becomes contradictory or remains unresolved."),
        "REVERSAL_RISK": ("Reversal-risk evidence persists with coherent opposing structure.", "Opposing evidence disappears or continuation structure resumes."),
    }.get(s, ("Additional live evidence establishes one coherent dominant scenario.", "Conflicting or insufficient evidence persists."))


def adjudicate(r6: pd.Series, r11: pd.Series, r12: pd.Series) -> tuple[str, str, float, list[dict[str, str]], list[dict[str, str]]]:
    s12 = scenario_from_stage12(r12["scenario_classification"])
    s11 = scenario_from_structure(r11["structure_state"])
    reg = regime_family(r6["regime"])
    align = str(r11["research_live_alignment"]).upper().strip()
    quality = str(r12["scenario_quality"]).upper().strip()
    pv = str(r11["price_volume_quality"]).upper().strip()
    supporting: list[dict[str, str]] = []
    conflicting: list[dict[str, str]] = []
    score = 0.0

    if s12 != "UNCLEAR":
        supporting.append(ev("Stage 12 scenario", "SUPPORTING", s12)); score += 0.25
    else:
        supporting.append(ev("Stage 12 scenario", "NEUTRAL", "UNCLEAR"))
    if s11 == s12 and s12 != "UNCLEAR":
        supporting.append(ev("Stage 11 structure", "SUPPORTING", s11)); score += 0.20
    elif s11 != "UNCLEAR" and s12 != "UNCLEAR":
        conflicting.append(ev("Stage 11 structure", "CONFLICTING", f"{s11} vs {s12}"))
    if reg == s12 or (reg == "CONTINUATION" and s12 == "CONTINUATION"):
        supporting.append(ev("Stage 6 regime", "SUPPORTING", reg)); score += 0.15
    elif reg != "UNCLEAR" and s12 != "UNCLEAR":
        conflicting.append(ev("Stage 6 regime", "CONFLICTING", f"{reg} vs {s12}"))
    if align == "HIGH":
        supporting.append(ev("Stage 11 research/live alignment", "SUPPORTING", align)); score += 0.15
    elif align in {"PARTIAL", "MODERATE"}:
        supporting.append(ev("Stage 11 research/live alignment", "NEUTRAL", align)); score += 0.08
    else:
        conflicting.append(ev("Stage 11 research/live alignment", "CONFLICTING", align))
    if pv == "STRONG":
        supporting.append(ev("Stage 11 price/volume", "SUPPORTING", pv)); score += 0.10
    elif pv == "MODERATE":
        supporting.append(ev("Stage 11 price/volume", "NEUTRAL", pv)); score += 0.05
    else:
        conflicting.append(ev("Stage 11 price/volume", "CONFLICTING", pv))
    if quality == "HIGH": score += 0.10
    elif quality == "MODERATE": score += 0.05

    scenario = s12 if s12 != "UNCLEAR" else s11
    if len(conflicting) >= 2:
        state = "SCENARIO_CONFLICTED"
    elif scenario == "UNCLEAR":
        state = "SCENARIO_UNCONFIRMED"
    elif str(r12["stage12_state"]).upper().strip() == "EXECUTION_SCENARIO_READY" and not conflicting and score >= 0.70:
        state = "SCENARIO_CONFIRMED"
    elif str(r12["stage12_state"]).upper().strip() == "EXECUTION_SCENARIO_CONDITIONAL":
        state = "SCENARIO_CONDITIONAL"
    else:
        state = "SCENARIO_UNCONFIRMED"
    return state, scenario, round(min(0.99, score), 4), supporting, conflicting


def main() -> int:
    ap = argparse.ArgumentParser()
    for n in ("universe", "profiles", "stage6", "stage7", "stage8", "stage9", "stage10", "stage11", "stage12", "contract", "output"):
        ap.add_argument(f"--{n}", required=True)
    a = ap.parse_args()
    out = Path(a.output); out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    engine = validation = "FAIL"
    try:
        c = load_json(a.contract)
        if c.get("coverage") != 29: raise ValueError("Stage 13 contract coverage is not 29")
        symbols, ranks = universe(a.universe); expected = set(symbols); profiles(a.profiles, expected)
        s6 = table(a.stage6, "Stage 6", expected, {"symbol", "regime", "data_status"})
        s7 = table(a.stage7, "Stage 7", expected, {"symbol", "activation", "data_status"})
        s8 = table(a.stage8, "Stage 8", expected, {"symbol", "activation", "data_status", "portfolio_rank"})
        s9 = table(a.stage9, "Stage 9", expected, {"symbol", "activation", "data_status", "candidate_quality_score"})
        s10 = table(a.stage10, "Stage 10", expected, {"symbol", "integrity_state", "data_status", *PROV[:4]})
        s11 = table(a.stage11, "Stage 11", expected, {"symbol", "analysis_state", "structure_state", "price_volume_quality", "event_state", "research_live_alignment", "live_data_timestamp", *PROV[:7]})
        s12 = table(a.stage12, "Stage 12", expected, {"symbol", "stage12_state", "scenario_classification", "scenario_quality", "research_live_match", "execution_environment_quality", "upstream_integrity", "live_analysis_state", *PROV, "live_data_timestamp", "trade_ready_output", "trade_authorized", "trade_signal_generated"})
        now = datetime.now(timezone.utc)
        for symbol in symbols:
            r6,r7,r8,r9,r10,r11,r12 = s6.loc[symbol],s7.loc[symbol],s8.loc[symbol],s9.loc[symbol],s10.loc[symbol],s11.loc[symbol],s12.loc[symbol]
            if not fresh(r12["live_data_timestamp"], now):
                state,scenario,conf = "DATA_STALE","UNCLEAR",0.0; support=[]; conflict=[ev("live_data","STALE","Stage 12 live timestamp is stale")]
            elif str(r10["integrity_state"]).upper().strip() == "DATA_INVALID":
                state,scenario,conf = "DATA_INVALID","UNCLEAR",0.0; support=[]; conflict=[ev("Stage 10","INVALID","Integrity state is DATA_INVALID")]
            elif str(r10["integrity_state"]).upper().strip() != "INTEGRITY_PASS":
                state,scenario,conf = "UPSTREAM_INVALID","UNCLEAR",0.0; support=[]; conflict=[ev("Stage 10","INVALID","Integrity is not INTEGRITY_PASS")]
            else:
                for col in PROV:
                    if not nonempty(r12[col]): raise ValueError(f"{symbol}: missing provenance {col}")
                state,scenario,conf,support,conflict = adjudicate(r6,r11,r12)
            confirm,invalidate = conditions(scenario)
            row = {
                "canonical_rank": ranks[symbol], "symbol": symbol, "stage13_state": state,
                "dominant_scenario": scenario, "scenario_confidence": conf,
                "evidence_stack": json.dumps(support+conflict, separators=(",",":")),
                "supporting_evidence": json.dumps(support, separators=(",",":")),
                "conflicting_evidence": json.dumps(conflict, separators=(",",":")),
                "confirmation_condition": confirm, "invalidation_condition": invalidate,
                "stage6_regime": str(r6["regime"]), "stage7_edge_state": str(r7["activation"]),
                "stage8_portfolio_rank": r8["portfolio_rank"], "stage9_quality": r9["candidate_quality_score"],
                "stage10_integrity": str(r10["integrity_state"]), "stage11_analysis_state": str(r11["analysis_state"]),
                "stage12_readiness_state": str(r12["stage12_state"]),
                **{p: str(r12[p]) for p in PROV},
                "stage13_provenance": "Stage 13 PSY29 Live Scenario Adjudication & Trigger-Integrity Gate v1.0",
                "live_data_timestamp": str(r12["live_data_timestamp"]), **SAFETY,
            }
            rows.append(row)
        df = pd.DataFrame(rows)
        if len(df)!=29 or df["symbol"].nunique()!=29 or set(df.symbol)!=expected: raise ValueError("29/29 coverage failed")
        if not set(df.stage13_state).issubset(STATES): raise ValueError("Invalid Stage 13 state")
        if not set(df.dominant_scenario).issubset(SCENARIOS): raise ValueError("Invalid scenario")
        for col in PROV+["stage13_provenance"]:
            if not df[col].map(nonempty).all(): raise ValueError(f"Incomplete provenance: {col}")
        for col in SAFETY:
            if not (df[col] == False).all(): raise ValueError(f"Safety violation: {col}")  # noqa: E712
        df.to_csv(out/"PSY29_STAGE13_SCENARIO_ADJUDICATION.csv", index=False)
        engine = validation = "PASS"
    except Exception as exc:
        (out/"stage13_error.txt").write_text(str(exc), encoding="utf-8")
    summary = {
        "contract":"PSY29_LIVE_SCENARIO_ADJUDICATION_TRIGGER_INTEGRITY_GATE", "version":"1.0",
        "engine_execution_status":engine, "validation_status":validation,
        "status":"PASS" if engine==validation=="PASS" else "FAIL", "coverage":len(rows), "expected_coverage":29,
        "fail_closed":True, **SAFETY, "provenance_complete": engine==validation=="PASS",
        "scenario_states":sorted(set(r["stage13_state"] for r in rows)) if rows else [],
    }
    (out/"stage13_summary.json").write_text(json.dumps(summary,indent=2), encoding="utf-8")
    if summary["status"] != "PASS": return 1
    print("PSY29 STAGE 13: PASS | 29/29 | FAIL-CLOSED | NO TRADE AUTHORIZATION")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
