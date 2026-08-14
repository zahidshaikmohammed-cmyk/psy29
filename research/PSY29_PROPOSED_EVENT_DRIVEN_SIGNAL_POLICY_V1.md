# PSY29 — Proposed Event-Driven Signal Policy V1

**STATUS: PROPOSED / REVIEW REQUIRED — NOT IMPLEMENTED**

## Scope

This document records the research conclusion from the completed PSY29 event-time and post-detection expectancy studies. It is a research/operational policy proposal only. It does not modify production code, `main`, Stage 20, or any locked contract.

## Authority

- Stage 20 remains the sole final trade-signal authority.
- This policy controls signal eligibility and emission timing only.
- Historical timing profiles never override Stage 20 authority.
- Real DHAN data is mandatory for live signal generation.
- Fixture data is forbidden in the live signal path.
- Missing or invalid data/dependencies fail closed.

## Proposed operating policy

### 1. Signal model

PSY29 is event-driven, not fixed-time-driven. The system continuously monitors eligible instruments during the NSE session, but a signal is emitted only when a genuine event is detected, all existing upstream dependencies are satisfied, and Stage 20 authorizes it.

### 2. Hard earliest eligibility

- Trend: eligible from the first completed observation for which all existing upstream prerequisites are available.
- Strong Trend: eligible from the first completed observation for which all existing upstream prerequisites are available.
- OR Continuation: eligible only after the opening range has been completely established.
- Historical earliest timestamps do not suppress an earlier genuine event when the live prerequisites are objectively satisfied.

### 3. Stock × event historical priority windows

Each of the 29 instruments retains its own historical timing profile for Trend, Strong Trend, and OR Continuation.

- Q25–Q75: **soft historical priority window only**.
- Q75–P90: **late but historically valid**.
- P90 to the hard cutoff: **extreme-late but still eligible**; no validation relaxation is permitted.
- These windows may affect Control Tower ranking/telemetry only. They must **never** reduce polling frequency, defer event evaluation, delay detection, suppress an event, or act as a hard signal gate.

### 4. Proposed final hard new-signal cutoff

**15:00:00 IST inclusive.**

- If the objectively detected event timestamp is **<= 15:00:00 IST**, the event remains eligible for the existing Stage 6–20 chain and, if Stage 20 authorizes it, the emission layer may emit the signal subject to the daily emission lock.
- If the objectively detected event timestamp is **> 15:00:00 IST**, no new Stage 20-authorized signal may be emitted for that NSE session.
- Existing monitoring/telemetry may continue for research and state tracking, but it cannot create a new trade signal after the cutoff.

### 5. Stage 20 authority versus emission gate

The policy does **not** alter, reinterpret, downgrade, or replace Stage 20 authority.

The sequence is strictly:

**Existing upstream stages → Stage 20 authorization → emission gate → emitted signal.**

- Stage 20 remains the sole authority that determines whether a trade is authorized.
- The emission gate only determines whether an already-authorized signal may be emitted under this policy's timing and daily-lock constraints.
- The emission gate must never convert a Stage 20 rejection into an approval or modify the content/meaning of a Stage 20 authorization.

### 6. One-signal-per-instrument-per-day

The emission layer shall enforce:

**Maximum 1 emitted signal per instrument per NSE trading session-date.**

The lock key is explicitly:

**`instrument + NSE trading-session-date`**

Once a genuine Stage 20-authorized signal is emitted for an instrument:

- that instrument/session key enters a daily emission lock;
- later qualifying events may be observed internally but cannot produce a second emitted signal for that same instrument/session-date;
- the lock resets only when a new valid NSE trading session-date begins, including correct handling of weekends and exchange holidays.

This is an emission-layer rule and does not alter Stage 20's internal authority or contract.

## Research evidence

### Event-time study

- Exact locked 29-stock universe.
- 60-session training / 20-session test / 20-session step walk-forward methodology.
- Event-time detection was evaluated without hindsight.
- Canonical event counts were reproduced.

### Post-detection expectancy study

- **1,934 historical event detections.**
- **87/87 stock × event-type validation cells passed.**
- 29 stocks × 3 event types.
- Outcome measurement began at the objectively detected event timestamp.
- MFE, MAE, 5/15/30/60-minute returns, time-to-MFE, time-to-MAE, and remaining-session runway were evaluated.

### Detection-time bucket evidence

Aggregate observations:

| Detection bucket | Events | 5m return | 15m return | 30m return | MFE | MAE | Median runway | Close win rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Before 14:30 | 1,791 | +0.054% | +0.093% | +0.162% | +1.598% | -0.741% | 311m | 86.5% |
| 14:30–14:45 | 29 | +0.028% | +0.085% | +0.243% | +0.594% | -0.219% | 52m | 96.6% |
| 14:45–15:00 | 29 | +0.061% | +0.366% | +0.487% | +0.817% | -0.314% | 38.5m | 86.2% |
| After 15:00 | 85 | +0.143% | +0.281% | — | +0.642% | -0.234% | 17m | 77.6% |

The missing 30/60-minute values in late buckets are structurally unavailable where insufficient session time remained.

### Evidence qualification

The overall post-15:00 bucket contains **85 events**, but its event-type subsets are uneven and some are small; in particular, the post-15:00 OR Continuation subset contains only **9 events**. Therefore the evidence supports an operational cutoff based on distribution degradation and execution runway, but does **not** establish that every individual post-15:00 event type is intrinsically unprofitable or worthless.

### Distribution comparison

- Before 14:30 vs 14:30–15:00 close-return distributions: **p = 5.49 × 10⁻⁶**.
- Before 14:30 vs after 15:00: **p = 3.87 × 10⁻¹²**.
- 14:30–15:00 vs after 15:00: **p = 0.0424**.
- Median close return: **+0.708% before 14:30** vs **+0.296% at 14:30–15:00** vs **+0.170% after 15:00**.
- Median remaining runway: **38.5 minutes at 14:45–15:00** vs **17 minutes after 15:00**.

## Research conclusion

15:00 is recommended as the final hard cutoff because post-15:00 events retain positive expectancy but show materially compressed execution runway and degraded close-return distribution relative to earlier detections. The evidence does **not** support the claim that post-15:00 events are worthless; it supports the operational conclusion that their remaining-session economics are no longer attractive enough to permit new live signal emission, while acknowledging the smaller late-event samples.

## Implementation status

**NOT IMPLEMENTED.**

No production code, production workflow, `main`, Stage 20, or locked contract is changed by this document. Any future implementation requires an explicit review/approval step and must preserve Stage 20 as the sole final trade authority.
