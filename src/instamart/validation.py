"""Generic checkpoint machinery shared by every part's validation checks."""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Check:
    """One named reference checkpoint; tol > 0 compares numbers within an absolute tolerance.
    gating=False marks an informational comparison that is printed as INFO and never fails the run."""

    name: str
    expected: Any
    actual: Any
    tol: float = 0.0
    gating: bool = True

    @property
    def passed(self) -> bool:
        """True when actual equals expected (or is within tol for numeric checks)."""
        if not self.gating:
            return True
        if self.tol and isinstance(self.expected, (int, float)) and isinstance(self.actual, (int, float)):
            return abs(self.actual - self.expected) <= self.tol
        return self.actual == self.expected


def money(value: float) -> float:
    """Round a monetary INR value to paise for exact comparison."""
    return round(float(value), 2)


def format_line(check: Check) -> str:
    """Render one check as 'PASS|FAIL|INFO  name: expected=..., actual=...'."""
    status = "INFO" if not check.gating else "PASS" if check.passed else "FAIL"
    tol = f" (tol {check.tol:.4g})" if check.tol else ""
    return f"{status}  {check.name}: expected={check.expected!r}, actual={check.actual!r}{tol}"
