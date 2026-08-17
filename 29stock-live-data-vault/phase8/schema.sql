CREATE TABLE IF NOT EXISTS raw_market_snapshots (
  snapshot_id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  security_id INTEGER NOT NULL,
  snapshot_minute TIMESTAMPTZ NOT NULL,
  payload JSONB NOT NULL,
  provider TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(symbol, snapshot_minute)
);

CREATE TABLE IF NOT EXISTS candles (
  candle_id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  candle_start TIMESTAMPTZ NOT NULL,
  candle_end TIMESTAMPTZ NOT NULL,
  open NUMERIC NOT NULL, high NUMERIC NOT NULL, low NUMERIC NOT NULL, close NUMERIC NOT NULL,
  volume BIGINT NOT NULL,
  complete BOOLEAN NOT NULL,
  source TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(symbol, timeframe, candle_start)
);

CREATE TABLE IF NOT EXISTS indicators (
  indicator_id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  candle_start TIMESTAMPTZ NOT NULL,
  vwap NUMERIC, ema9 NUMERIC, ema20 NUMERIC,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(symbol, timeframe, candle_start)
);

CREATE TABLE IF NOT EXISTS session_features (
  feature_id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  trading_date DATE NOT NULL,
  candle_start TIMESTAMPTZ NOT NULL,
  session_open NUMERIC, session_high NUMERIC, session_low NUMERIC, session_close NUMERIC,
  session_volume BIGINT, first_5m_high NUMERIC, first_5m_low NUMERIC, first_5m_range NUMERIC,
  first_15m_high NUMERIC, first_15m_low NUMERIC, first_15m_range NUMERIC,
  running_high NUMERIC, running_low NUMERIC, running_volume BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(symbol, trading_date, candle_start)
);

CREATE TABLE IF NOT EXISTS derivative_data (
  derivative_id BIGSERIAL PRIMARY KEY,
  symbol TEXT NOT NULL,
  observed_at TIMESTAMPTZ NOT NULL,
  expiry DATE,
  strike NUMERIC,
  option_type TEXT,
  last_price NUMERIC,
  oi BIGINT,
  volume BIGINT,
  iv NUMERIC,
  delta NUMERIC, gamma NUMERIC, theta NUMERIC, vega NUMERIC,
  bid_price NUMERIC, ask_price NUMERIC, bid_qty BIGINT, ask_qty BIGINT,
  payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS archive_manifest (
  archive_id BIGSERIAL PRIMARY KEY,
  trading_date DATE NOT NULL UNIQUE,
  object_uri TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  byte_size BIGINT NOT NULL,
  verified_at TIMESTAMPTZ NOT NULL,
  source_row_counts JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_raw_symbol_minute ON raw_market_snapshots(symbol, snapshot_minute);
CREATE INDEX IF NOT EXISTS idx_candles_symbol_tf_start ON candles(symbol, timeframe, candle_start);
CREATE INDEX IF NOT EXISTS idx_indicators_symbol_tf_start ON indicators(symbol, timeframe, candle_start);
CREATE INDEX IF NOT EXISTS idx_features_symbol_date_start ON session_features(symbol, trading_date, candle_start);
CREATE INDEX IF NOT EXISTS idx_derivatives_symbol_observed ON derivative_data(symbol, observed_at);
CREATE INDEX IF NOT EXISTS idx_derivatives_expiry_strike ON derivative_data(expiry, strike, option_type);

-- Immutable-history policy: ingestion uses INSERT ... ON CONFLICT DO NOTHING.
-- Archive deletion is permitted only after archive_manifest verification.
