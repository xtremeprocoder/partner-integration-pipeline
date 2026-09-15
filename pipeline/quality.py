"""Pass/fail data quality checks on a normalized batch.

Checks run before anything is written, so a bad batch is loud and never
silently lands in the database. Each check returns a result; the batch passes
only if every check does.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from .normalize import CanonicalOrder


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class QualityReport:
    results: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    def summary(self) -> str:
        lines = [f"[{'PASS' if r.passed else 'FAIL'}] {r.name}: {r.detail}" for r in self.results]
        lines.append(f"Overall: {'PASS' if self.passed else 'FAIL'}")
        return "\n".join(lines)


# Thresholds: the mock partner drops ~1 in 4 amounts, ~1 in 8 statuses,
# ~1 in 5 dates, and skips customer_id on every 11th record. Real partners
# are worse, so these are deliberately lenient; tighten them as the
# integration matures.
MAX_NULL_AMOUNT_RATIO = 0.40
MAX_NULL_STATUS_RATIO = 0.25
MAX_NULL_DATE_RATIO = 0.35
MAX_NULL_CUSTOMER_RATIO = 0.25


def _null_ratio(orders: list[CanonicalOrder], field: str) -> float:
    if not orders:
        return 0.0
    return sum(1 for o in orders if getattr(o, field) is None) / len(orders)


def run_quality_checks(orders: list[CanonicalOrder]) -> QualityReport:
    report = QualityReport()
    report.results.append(CheckResult(
        name="non_empty_batch",
        passed=len(orders) > 0,
        detail=f"{len(orders)} records in batch",
    ))

    counts = Counter(o.order_id for o in orders)
    dupes = {oid: n for oid, n in counts.items() if n > 1}
    report.results.append(CheckResult(
        name="no_duplicate_order_ids",
        passed=not dupes,
        detail=f"{len(dupes)} duplicate order ids" if dupes else "all order ids unique",
    ))

    for field_name, limit in (
        ("amount", MAX_NULL_AMOUNT_RATIO),
        ("status", MAX_NULL_STATUS_RATIO),
        ("ordered_at", MAX_NULL_DATE_RATIO),
        ("customer_id", MAX_NULL_CUSTOMER_RATIO),
    ):
        ratio = _null_ratio(orders, field_name)
        report.results.append(CheckResult(
            name=f"{field_name}_null_ratio_below_{int(limit * 100)}pct",
            passed=ratio <= limit,
            detail=f"{ratio:.1%} null (limit {limit:.0%})",
        ))
    return report
