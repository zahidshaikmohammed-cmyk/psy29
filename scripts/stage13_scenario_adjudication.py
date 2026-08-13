#!/usr/bin/env python3
"""PSY29 Stage 13 - Live Scenario Adjudication & Trigger-Integrity Gate.

Stage 13 is descriptive only. It adjudicates a coherent live scenario from
verified Stage 5-12 evidence and never generates or authorizes a trade.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

STATES = {
    "SCENARIO_CONFIRMED", "SCENARIO_CONDITIONAL", "SCENARIO_UNCONFIRMED",
    "SCENARIO_CONFLICTED", "DATA_STALE", "DATA_INVALID", "UPSTREAM_INVALID",
}
SCENARIOS = {
    "CONTINUATION", "BREAKOUT", "BREAKDOWN", "RETEST",
    "REVERSAL_RISK", "RANGE", "TRANSITION", "UNCLEAR",
}
SAFETY_FALSE = {
    "trade_ready_output": False, "trade_authorized": False,
    "trade_signal_generated": False, "ce_pe_selection": False,
    "entry_calculation": False, "stop_loss_calculation": False,
    "target_calculation": False, "position_size_calculation": False,
    "risk_calculation": False, "capital_allocation": False,
    "order_generation": False, "execution": False,
}


def load_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing JSON: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def symbols_from_universe(path: str) -> tuple[list[str], dict[str, int]]:
    data = load_json(path)
    rows = data.get("universe", [])
    if len(rows) != 29:
        raise ValueError(f"Canonical universe must contain 29 rows; got {len(rows)}")
    symbols = [str(r.get("symbol", "")).upper().strip() for r in rows]
    ranks = [int(r.get("rank", 0)) for r in rows]
    if any(not s for s in symbols) or len(set(symbols)) != 29:
        raise ValueError("Canonical universe has empty or duplicate symbols")
    if ranks != list(range(1, 30)):
        raise ValueError("Canonical ranks must be exactly 1-29")
    return symbols, dict(zip(symbols, ranks))


def load_profiles(path: str, symbols: set[str]) -> dict[str, dict[str, Any]]:
    data = load_json(path)
    rows = data.get("profiles", [])
    if len(rows) != 29:
        raise ValueError("Stage 5 must contain exactly 29 profiles")
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        s = str(row.get("symbol", "")).upper().strip()
        if not s or s in out:
            raise ValueError("Stage 5 has empty or duplicate symbols")
        out[s] = row
    if set(out) != symbols:
        raise ValueError("Stage 5 universe does not equal canonical universe")
    return out


def load_table(path: str, name: str, symbols: set[str], fields: set[str]) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Missing {name}: {p}")
    df = pd.read_csv(p)
    missing = fields - set(df.columns)
    if missing:
        raise ValueError(f"{name} missing fields: {sorted(missing)}")
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    if len(df) != 29 or df["symbol"].nunique() != 29:
        raise ValueError(f"{name} must contain 29 unique rows")
    if set(df["symbol"]) != symbols:
        raise ValueError(f"{name} universe mismatch")
    return df.set_index("symbol")


def nonempty(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip().lower()
    return text not in {"", "nan", "none", "null"}


def parse_ts(value: Any) -> datetime:
    text = str(value).strip()
    if not text:
        raise ValueError("empty timestamp")
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timestamp is not timezone-aware")
    return dt.astimezone(timezone.utc)


def freshness(value: Any, now: datetime) -> str:
    age = (now - parse_ts(value)).total_seconds()
    if age < -5:
        raise ValueError("live timestamp is materially in the future")
    if age <= 180:
        return "FRESH"
    return "STALE"


def normalize_stage12_scenario(value: Any) -> str:
    text = str(value).strip().upper()
    mapping = {
        "CONTINUATION_SCENARIO": "CONTINUATION",
        "BREAKOUT_SCENARIO": "BREAKOUT",
        "BREAKDOWN_SCENARIO": "BREAKDOWN",
        "RETEST_SCENARIO": "RETEST",
        "REVERSAL_RISK_SCENARIO": "REVERSAL_RISK",
        "RANGE_SCENARIO": "RANGE",
        "TRANSITION_SCENARIO": "TRANSITION",
        "UNCLEAR_SCENARIO": "UNCLEAR",
    }
    return mapping.get(text, text if text in SCENARIOS else "UNCLEAR")


def structure_scenario(stage11: pd.Series) -> str:
    mapping = {
        "BREAKOUT_STRUCTURE": "BREAKOUT",
        "BREAKDOWN_STRUCTURE": "BREAKDOWN",
        "TRENDING_UP": "CONTINUATION",
        "TRENDING_DOWN": "CONTINUATION",
        "RANGE": "RANGE",
        "TRANSITION": "TRANSITION",
        "UNCLEAR": "UNCLEAR",
    }
    return mapping.get(str(stage11["structure_state"]).upper().strip(), "UNCLEAR")


def regime_family(regime: Any) -> str:
    r = str(regime).upper().strip()
    if "BREAKOUT" in r:
        return "BREAKOUT"
    if "BREAKDOWN" in r:
        return "BREAKDOWN"
    if "RANGE" in r or "NEUTRAL" in r:
        return "RANGE"
    if "TRANSITION" in r:
        return "TRANSITION"
    if "BULL" in r or "UP" in r:
        return "CONTINUATION"
    if "BEAR" in r or "DOWN" in r:
        return "CONTINUATION"
    return "UNCLEAR"


def evidence(label: str, state: str, detail: str) -> dict[str, str]:
    return {"source": label, "state": state, "detail": detail}


def conditions(scenario: str, stage11: pd.Series) -> tuple[str, str]:
    structure = str(stage11["structure_state"]).upper().strip()
    event = str(stage11["event_state"]).upper().strip()
    if scenario == "BREAKOUT":
        return (
            "Breakout structure remains intact with confirming live price/volume behaviour.",
            "Breakout structure fails and price returns into the prior structural range.",
        )
    if scenario == "BREAKDOWN":
        return (
            "Breakdown structure remains intact with confirming live price/volume behaviour.",
            "Breakdown structure fails and price returns into the prior structural range.",
        )
    if scenario == "CONTINUATION":
        return (
            "Directional structure remains coherent with continued supporting price/volume behaviour.",
            "Directional structure loses coherence or develops material contradictory evidence.",
        )
    if scenario == "RETEST":
        return (
            "The retest holds the referenced structural level and subsequent structure remains coherent.",
            "The referenced structural level fails and the retest loses structural validity.",
        )
    if scenario == "RANGE":
        return (
            "Price remains contained within the identified range with no decisive structural break.",
            "A decisive structural break invalidates the range scenario.",
        )
    if scenario == "TRANSITION":
        return (
            "Additional live structure confirms a stable directional or range regime.",
            "Transition evidence becomes contradictory or remains unresolved.",
        )
    if scenario == "REVERSAL_RISK":
        return (
            "Reversal-risk evidence persists with a coherent opposing structural development.",
            "The opposing structural evidence disappears or continuation structure resumes.",
        )
    return (
        "Additional live evidence establishes one coherent dominant scenario.",
        "Conflicting or insufficient evidence persists, preventing coherent classification.",
    )


def adjudicate(row: dict[str, Any], stage11: pd.Series) -> tuple[str, str, float, list[dict[str, str]], list[dict[str, str]], str, str]:
    readiness = str(row["stage12_state"]).upper().strip()
    stage12_scenario = normalize_stage12_scenario(row["scenario_classification"])
    stage11_scenario = structure_scenario(stage11)
    regime = regime_family(row["stage6_regime"])
    alignment = str(stage11["research_live_alignment"]).upper().strip()
    quality = str(row["scenario_quality"]).upper().strip()
    coherence = str(row.get("stage12_structural_coherence", "")).upper().strip()
    pv = str(stage11["price_volume_quality"]).upper().strip()
    event = str(stage11["event_state"]).upper().strip()

    supporting: list[dict[str, str]] = []
    conflicting: list[dict[str, str]] = []
    score = 0.0

    if stage12_scenario != "UNCLEAR":
        supporting.append(evidence("Stage 12 scenario", "SUPPORTING", stage12_scenario))
        score += 0.25
    else:
        supporting.append(evidence("Stage 12 scenario", "NEUTRAL", "Scenario remains unclear"))

    if stage11_scenario == stage12_scenario and stage12_scenario != "UNCLEAR":
        supporting.append(evidence("Stage 11 structure", "SUPPORTING", stage11_scenario))
        score += 0.20
    elif stage11_scenario != "UNCLEAR" and stage12_scenario != "UNCLEAR":
        conflicting.append(evidence("Stage 11 vs Stage 12", "CONFLICTING", f"{stage11_scenario} vs {stage12_scenario}"))

    if regime == stage12_scenario or (regime == "CONTINUATION" and stage12_scenario == "CONTINUATION"):
        supporting.append(evidence("Stage 6 regime", "SUPPORTING", regime))
        score += 0.15
    elif regime != "UNCLEAR" and stage12_scenario != "UNCLEAR":
        conflicting.append(evidence("Stage 6 regime", "CONFLICTING", f"regime={regime}; scenario={stage12_scenario}"))

    if alignment == "HIGH":
        supporting.append(evidence("Stage 11 research/live alignment", "SUPPORTING", "HIGH"))
        score += 0.15
    elif alignment in {"PARTIAL", "MODERATE"}:
        supporting.append(evidence("Stage 11 research/live alignment", "NEUTRAL", alignment))
        score += 0.08
    elif alignment in {"LOW", "UNCONFIRMED"}:
        conflicting.append(evidence("Stage 11 research/live alignment", "CONFLICTING", alignment))

    if pv == "STRONG":
        supporting.append(evidence("Stage 11 price/volume", "SUPPORTING", "STRONG"))
        score += 0.10
    elif pv == "MODERATE":
        supporting.append(evidence("Stage 11 price/volume", "NEUTRAL", "MODERATE"))
        score += 0.05
    else:
        conflicting.append(evidence("Stage 11 price/volume", "CONFLICTING", pv))

    if event in {"BREAKOUT_OBSERVED", "BREAKDOWN_OBSERVED", "CONTINUATION", "RETEST"}:
        supporting.append(evidence("Stage 11 event", "SUPPORTING", event))
        score += 0.05

    if quality == "HIGH":
        score += 0.10
        supporting.append(evidence("Stage 12 scenario quality", "SUPPORTING", "HIGH"))
    elif quality == "MODERATE":
        score += 0.05
        supporting.append(evidence("Stage 12 scenario quality", "NEUTRAL", "MODERATE"))

    scenario = stage12_scenario if stage12_scenario != "UNCLEAR" else stage11_scenario
    if scenario not in SCENARIOS:
        scenario = "UNCLEAR"

    if conflicting and len(conflicting) >= 2:
        state = "SCENARIO_CONFLICTED"
        confidence = round(max(0.0, min(0.99, score)), 4)
    elif readiness in {"DATA_STALE"}:
        state = "DATA_STALE"
        confidence = 0.0
    elif readiness in {"DATA_INVALID"}:
        state = "DATA_INVALID"
        confidence = 0.0
    elif readiness == "UPSTREAM_INVALID":
        state = "UPSTREAM_INVALID"
        confidence = 0.0
    elif scenario == "UNCLEAR":
        state = "SCENARIO_UNCONFIRMED"
        confidence = round(max(0.0, min(0.99, score)), 4)
    elif readiness == "EXECUTION_SCENARIO_READY" and not conflicting and score >= 0.70:
        state = "SCENARIO_CONFIRMED"
        confidence = round(min(0.99, score), 4)
    elif readiness in {"EXECUTION_SCENARIO_READY", "EXECUTION_SCENARIO_CONDITIONAL"}:
        state = "SCENARIO_CONDITIONAL"
        confidence = round(min(0.99, score), 4)
    else:
        state = "SCENARIO_UNCONFIRMED"
        confidence = round(min(0.99, score), 4)

    confirm, invalidate = conditions(scenario, stage11)
    return state, scenario, confidence, supporting, conflicting, confirm, invalidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", required=True)
    parser.add_argument("--profiles", required=True)
    parser.add_argument("--stage6", required=True)
    parser.add_argument("--stage7", required=True)
    parser.add_argument("--stage8", required=True)
    parser.add_argument("--stage9", required=True)
    parser.add_argument("--stage10", required=True)
    parser.add_argument("--stage11", required=True)
    parser.add_argument("--stage12", required=True)
    parser.add_argument("--contract", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    outdir = Path(args.output)
    outdir.mkdir(parents=True, exist_ok=True)

    engine_status = "FAIL"
    validation_status = "FAIL"
    rows: list[dict[str, Any]] = []

    try:
        contract = load_json(args.contract)
        if contract.get("coverage") != 29 or contract.get("status") not in {"IMPLEMENTED", "LOCKED"}:
            raise ValueError("Invalid Stage 13 contract")
        symbols, ranks = symbols_from_universe(args.universe)
        symbol_set = set(symbols)
        load_profiles(args.profiles, symbol_set)

        s6 = load_table(args.stage6, "Stage 6", symbol_set, {"symbol", "regime", "data_status"})
        s7 = load_table(args.stage7, "Stage 7", symbol_set, {"symbol", "activation", "data_status", "reason_code"})
        s8 = load_table(args.stage8, "Stage 8", symbol_set, {"symbol", "activation", "data_status", "portfolio_rank", "ranking_score"})
        s9 = load_table(args.stage9, "Stage 9", symbol_set, {"symbol", "activation", "data_status", "candidate_quality_score"})
        s10 = load_table(args.stage10, "Stage 10", symbol_set, {"symbol", "integrity_state", "activation", "data_status", "research_provenance", "stage6_provenance", "stage7_provenance", "stage8_provenance", "stage9_provenance"})
        s11 = load_table(args.stage11, "Stage 11", symbol_set, {"symbol", "analysis_state", "structure_state", "price_volume_quality", "event_state", "research_live_alignment", "live_data_timestamp", "research_provenance", "stage6_provenance", "stage7_provenance", "stage8_provenance", "stage9_provenance", "stage10_provenance", "stage11_provenance"})
        s12 = load_table(args.stage12, "Stage 12", symbol_set, {"symbol", "stage12_state", "scenario_classification", "scenario_quality", "research_live_match", "execution_environment_quality", "upstream_integrity", "live_analysis_state", "research_provenance", "stage6_provenance", "stage7_provenance", "stage8_provenance", "stage9_provenance", "stage10_provenance", "stage11_provenance", "stage12_provenance", "live_data_timestamp", "trade_ready_output", "trade_authorized", "trade_signal_generated"})

        now = datetime.now(timezone.utc)
        for symbol in symbols:
            r6, r7, r8, r9 = s6.loc[symbol], s7.loc[symbol], s8.loc[symbol], s9.loc[symbol]
            r10, r11, r12 = s10.loc[symbol], s11.loc[symbol], s12.loc[symbol]

            # Complete provenance is mandatory.
            provenance_fields = {
                "research_provenance": r12["research_provenance"],
                "stage6_provenance": r12["stage6_provenance"],
                "stage7_provenance": r12["stage7_provenance"],
                "stage8_provenance": r12["stage8_provenance"],
                "stage9_provenance": r12["stage9_provenance"],
                "stage10_provenance": r12["stage10_provenance"],
                "stage11_provenance": r12["stage11_provenance"],
                "stage12_provenance": r12["stage12_provenance"],
            }
            if not all(nonempty(v) for v in provenance_fields.values()):
                raise ValueError(f"{symbol}: incomplete Stage 12 provenance")

            freshness_state = freshness(r12["live_data_timestamp"], now)
            if freshness_state == "STALE":
                state = "DATA_STALE"
                scenario = "UNCLEAR"
                conf = 0.0
                support = []
                conflict = [evidence("live_data", "STALE", "Stage 12 live timestamp is older than 180 seconds")]
                confirm, invalidate = conditions(scenario, r11)
            elif str(r10["integrity_state"]).upper().strip() == "DATA_INVALID":
                state = "DATA_INVALID"
                scenario = "UNCLEAR"
                conf = 0.0
                support = []
                conflict = [evidence("Stage 10", "INVALID", "Integrity state is DATA_INVALID")]
                confirm, invalidate = conditions(scenario, r11)
            else:
                row = {
                    "stage12_state": r12["stage12_state"],
                    "scenario_classification": r12["scenario_classification"],
                    "scenario_quality": r12["scenario_quality"],
                    "stage6_regime": r6["regime"],
                    "stage12_structural_coherence": "",
                }
                state, scenario, conf, support, conflict, confirm, invalidate = adjudicate(row, r11)

            stack = support + conflict
            rows.append({
                "canonical_rank": ranks[symbol],
                "symbol": symbol,
                "stage13_state": state,
                "dominant_scenario": scenario,
                "scenario_confidence": conf,
                "evidence_stack": json.dumps(stack, separators=(",", ":")),
                "supporting_evidence": json.dumps(support, separators=(",", ":")),
                "conflicting_evidence": json.dumps(conflict, separators=(",", ":")),
                "confirmation_condition": confirm,
                "invalidation_condition": invalidate,
                "stage6_regime": str(r6["regime"]),
                "stage7_edge_state": str(r7["activation"]),
                "stage8_portfolio_rank": r8["portfolio_rank"],
                "stage9_quality": r9["candidate_quality_score"],
                "stage10_integrity": str(r10["integrity_state"]),
                "stage11_analysis_state": str(r11["analysis_state"]),
                "stage12_readiness_state": str(r12["stage12_state"]),
                **provenance_fields,
                "live_data_timestamp": str(r12["live_data_timestamp"]),
                **SAFETY_FALSE,
            })

        df = pd.DataFrame(rows)
        if len(df) != 29 or df["symbol"].nunique() != 29 or set(df["symbol"]) != symbol_set:
            raise ValueError("Stage 13 output failed 29/29 coverage validation")
        if not set(df["stage13_state"]).issubset(STATES):
            raise ValueError("Invalid Stage 13 state emitted")
        if not set(df["dominant_scenario"]).issubset(SCENARIOS):
            raise ValueError("Invalid scenario emitted")
        for col in SAFETY_FALSE:
            if not (df[col] == False).all():  # noqa: E712
                raise ValueError(f"Safety violation: {col}")
        if any(not nonempty(v) for v in df["stage13_provenance"]):
            pass
        df["stage13_provenance"] = "Stage 13 PSY29 Live Scenario Adjudication & Trigger-Integrity Gate v1.0"
        df.to_csv(outdir / "PSY29_STAGE13_SCENARIO_ADJUDICATION.csv", index=False)

        engine_status = "PASS"
        validation_status = "PASS"

    except Exception as exc:
        (outdir / "stage13_error.txt").write_text(str(exc), encoding="utf-8")
        engine_status = "FAIL"
        validation_status = "FAIL"

    summary = {
        "contract": "PSY29_LIVE_SCENARIO_ADJUDICATION_TRIGGER_INTEGRITY_GATE",
        "version": "1.0",
        "engine_execution_status": engine_status,
        "validation_status": validation_status,
        "status": "PASS" if engine_status == "PASS" and validation_status == "PASS" else "FAIL",
        "coverage": len(rows),
        "expected_coverage": 29,
        "fail_closed": True,
        "trade_ready_output": False,
        "trade_authorized": False,
        "trade_signal_generated": False,
        "ce_pe_selection": False,
        "entry_calculation": False,
        "stop_loss_calculation": False,
        "target_calculation": False,
        "position_size_calculation": False,
        "risk_calculation": False,
        "capital_allocation": False,
        "order_generation": False,
        "execution": False,
        "provenance_complete": engine_status == "PASS" and validation_status == "PASS",
        "scenario_states": sorted(set(r["stage13_state"] for r in rows)) if rows else [],
    }
    (outdir / "stage13_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if summary["status"] != "PASS":
        raise SystemExit(1)
    print("PSY29 STAGE 13: PASS")
    print("29/29 coverage: PASS")
    print("Fail-closed safety: PASS")
    print("Trade authorization: FALSE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
