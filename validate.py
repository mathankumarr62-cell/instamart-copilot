"""Assert every reference checkpoint: python validate.py (run after run_all.py).

Prints one PASS/FAIL line per check and exactly ALL CHECKPOINTS PASSED when all hold (exit code 0)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from instamart import checkpoints  # noqa: E402
from instamart.validation import format_line  # noqa: E402


def main() -> int:
    """Run every registered check, print the results and return the process exit code."""
    failures, current = 0, None
    for part, check in checkpoints.collect():
        if part != current:
            print(f"== {part} ==")
            current = part
        print(format_line(check))
        failures += not check.passed
    if failures:
        print(f"{failures} CHECKPOINT(S) FAILED")
        return 1
    print("ALL CHECKPOINTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
