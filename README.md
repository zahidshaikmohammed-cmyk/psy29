# PSY29

## Psychic Stock Discovery Engine

PSY29 is a research-first intraday equity selection system designed to discover 29 Indian equities with unusually favorable behavioural characteristics for directional intraday trading.

### Core principle

PSY29 does **not** start with a permanent list of popular stocks. It starts with market data and earns the right to select the 29.

The system measures historical and live behaviour across:

- liquidity and execution quality
- intraday range and volatility
- trend persistence
- directional efficiency
- opening-range behaviour
- VWAP behaviour
- volume shocks and relative volume
- breakout continuation and failure
- market/sector relative strength
- decoupling from benchmark behaviour
- time-of-day behaviour
- adverse/favourable excursion
- anti-chop characteristics

The output is a machine-readable `psy29.json` selection with evidence, scores, confidence and selection reasons.

## Security

Dhan credentials must remain in GitHub Secrets/environment variables. Never commit API keys, tokens, credentials, or private data.

Expected secrets/environment variables:

- `DHAN_CLIENT_ID`
- `DHAN_ACCESS_TOKEN`

## Architecture

```text
Dhan API
   |
   v
Data Acquisition -> Raw Data -> Validation
                         |
                         v
                 Feature Engineering
                         |
          +--------------+--------------+
          |              |              |
       Behaviour      Liquidity      Market Context
          |              |              |
          +--------------+--------------+
                         |
                         v
                Behavioural Fingerprint
                         |
                         v
                  PSY29 Scoring
                         |
                         v
                Robustness / Validation
                         |
                         v
                   PSY29 Selector
                         |
                         v
                    psy29.json
```

## Development rule

Research before optimization. Backtest before live use. No strategy or stock is considered an edge until it survives out-of-sample validation and realistic transaction-cost assumptions.
