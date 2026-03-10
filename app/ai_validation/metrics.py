from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass
class AIMetrics:
    tests_generated: int = 0
    tests_fixed: int = 0
    tests_failed: int = 0

    @property
    def fix_rate(self) -> float:
        if self.tests_generated == 0:
            return 0.0
        return self.tests_fixed / self.tests_generated

    def as_dict(self) -> dict[str, float | int]:
        return {
            "tests_generated": self.tests_generated,
            "tests_fixed": self.tests_fixed,
            "tests_failed": self.tests_failed,
            "fix_rate": round(self.fix_rate, 4),
        }


class AIMetricsRegistry:
    _instance: "AIMetricsRegistry | None" = None
    _instance_lock = Lock()

    def __init__(self) -> None:
        self._lock = Lock()
        self._metrics = AIMetrics()

    @classmethod
    def instance(cls) -> "AIMetricsRegistry":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def inc_generated(self) -> None:
        with self._lock:
            self._metrics.tests_generated += 1

    def inc_fixed(self) -> None:
        with self._lock:
            self._metrics.tests_fixed += 1

    def inc_failed(self) -> None:
        with self._lock:
            self._metrics.tests_failed += 1

    def snapshot(self) -> AIMetrics:
        with self._lock:
            return AIMetrics(
                tests_generated=self._metrics.tests_generated,
                tests_fixed=self._metrics.tests_fixed,
                tests_failed=self._metrics.tests_failed,
            )

    def as_dict(self) -> dict[str, float | int]:
        return self.snapshot().as_dict()
