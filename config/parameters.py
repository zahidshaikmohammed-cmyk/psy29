"""Central configuration for PSY29 research experiments.

Keep secrets out of this module. Credentials are read from environment variables
by the Dhan client layer.
"""

TIMEFRAMES = ["1m", "5m", "15m"]

# Research universe is intentionally broad. PSY29 is discovered, not hard-coded.
MIN_HISTORY_SESSIONS = 120

# Selection controls; tune only through documented experiments.
TARGET_STOCK_COUNT = 29
TOP_CANDIDATE_BUFFER = 100

# Intraday research windows (IST).
MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:30"

# Costs must be configurable for realistic validation.
DEFAULT_BROKERAGE_BPS = 0.0
DEFAULT_SLIPPAGE_BPS = 3.0

RANDOM_SEED = 29
