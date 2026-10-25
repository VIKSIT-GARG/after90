"""Bounded TTL cache with per-key single-flight work outside its bookkeeping lock."""

from __future__ import annotations

import copy
import time
from collections import OrderedDict
from concurrent.futures import Future, TimeoutError
from threading import Lock
from typing import Callable, Hashable


class TTLCache:
    def __init__(self, *, max_entries: int = 128, max_inflight: int = 16,
                 wait_timeout: float = 5.0, clock: Callable[[], float] = time.monotonic):
        if max_entries < 1 or max_inflight < 1 or wait_timeout <= 0:
            raise ValueError("cache limits must be positive")
        self.max_entries = max_entries
        self.max_inflight = max_inflight
        self.wait_timeout = wait_timeout
        self.clock = clock
        self._entries: OrderedDict[Hashable, tuple[float, dict]] = OrderedDict()
        self._flights: dict[Hashable, Future] = {}
        self._lock = Lock()

    def clear(self) -> None:
        # Existing flights may finish normally; clear is a testing/maintenance
        # hook rather than cancellation of active provider requests.
        with self._lock:
            self._entries.clear()

    def _purge(self, now: float) -> None:
        for key in [key for key, (expires, _) in self._entries.items() if expires <= now]:
            del self._entries[key]

    def get_or_create(self, key: Hashable, factory: Callable[[], dict], *,
                      ttl: Callable[[dict], float], fallback: Callable[[str], dict]) -> tuple[dict, float]:
        with self._lock:
            now = self.clock()
            self._purge(now)
            if key in self._entries:
                expires, value = self._entries[key]
                self._entries.move_to_end(key)
                return copy.deepcopy(value), max(0.0, expires - now)
            flight = self._flights.get(key)
            owner = flight is None
            capacity = owner and len(self._flights) >= self.max_inflight
            if owner and not capacity:
                flight = Future()
                self._flights[key] = flight
        if capacity:
            return fallback("concurrency_limit"), 0.0
        if not owner:
            try:
                value, expires = flight.result(timeout=self.wait_timeout)
                return copy.deepcopy(value), max(0.0, expires - self.clock())
            except TimeoutError:
                return fallback("inflight_timeout"), 0.0
        try:
            try:
                value = factory()
            except Exception:
                value = fallback("generation_error")
            lifetime = max(0.0, float(ttl(value)))
            expires = self.clock() + lifetime
            with self._lock:
                self._purge(self.clock())
                self._entries[key] = (expires, copy.deepcopy(value))
                self._entries.move_to_end(key)
                while len(self._entries) > self.max_entries:
                    self._entries.popitem(last=False)
            flight.set_result((copy.deepcopy(value), expires))
            return copy.deepcopy(value), lifetime
        except BaseException as exc:
            # Never strand waiters if rendering the fallback itself fails.
            flight.set_exception(exc)
            raise
        finally:
            with self._lock:
                self._flights.pop(key, None)
