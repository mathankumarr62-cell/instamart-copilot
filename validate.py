"""Assert every reference checkpoint: python validate.py (run after run_all.py).

Prints one PASS/FAIL line per check and exactly ALL CHECKPOINTS PASSED when all hold (exit code 0)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from instamart.part_a import checks as part_a_checks  # noqa: E402
from instamart.part_b import checks as part_b_checks  # noqa: E402
from instamart.part_c import checks as part_c_checks  # noqa: E402
from instamart.validation import format_line  # noqa: E402

# Each later phase appends its own ("Part X", build_checks) entry here.
CHECK_BUILDERS = [("Part A", part_a_checks.build_checks), ("Part B", part_b_checks.build_checks),
                  ("Part C", part_c_checks.build_checks)]


def main() -> int:
    """Run every registered check, print the results and return the process exit code."""
    failures = 0
    for part, build in CHECK_BUILDERS:
        print(f"== {part} ==")
        for check in build():
            print(format_line(check))
            failures += not check.passed
    if failures:
        print(f"{failures} CHECKPOINT(S) FAILED")
        return 1
    print("ALL CHECKPOINTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
