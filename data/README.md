# Data layer

Raw provider data is intentionally excluded from Git.

Canonical flow:

provider -> raw -> validation -> processed bars -> feature tables

All timestamps must be normalized to Asia/Kolkata and all source records must retain provenance metadata.
