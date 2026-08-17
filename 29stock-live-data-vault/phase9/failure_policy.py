from __future__ import annotations
import time
from typing import Callable, TypeVar
T = TypeVar('T')

class TransientAcquisitionError(Exception): pass
class DatabaseWriteError(Exception): pass


def retry_with_backoff(operation: Callable[[], T], *, attempts: int = 3, base_delay: float = 0.01) -> T:
    last = None
    for n in range(attempts):
        try:
            return operation()
        except (TransientAcquisitionError, DatabaseWriteError) as exc:
            last = exc
            if n + 1 < attempts:
                time.sleep(base_delay * (2 ** n))
    raise last


def isolate_stock_failure(symbol: str, error: Exception) -> dict:
    return {'symbol': symbol, 'status': 'failed', 'isolated': True, 'error_type': type(error).__name__}


def no_fabrication_on_failure(symbol: str, error: Exception) -> dict:
    return {'symbol': symbol, 'status': 'missing', 'fabricated': False, 'reason': type(error).__name__}
