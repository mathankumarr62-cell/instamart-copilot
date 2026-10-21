"""The full reference-checkpoint list for Parts A-D, shared by validate.py and the dashboard."""
from instamart.part_a import checks as part_a_checks
from instamart.part_b import checks as part_b_checks
from instamart.part_c import checks as part_c_checks
from instamart.part_d import checks as part_d_checks
from instamart.validation import Check

CHECK_BUILDERS = [("Part A", part_a_checks.build_checks), ("Part B", part_b_checks.build_checks),
                  ("Part C", part_c_checks.build_checks), ("Part D", part_d_checks.build_checks)]


def collect() -> list[tuple[str, Check]]:
    """Build every registered check in part order and return (part, check) pairs; never exits."""
    return [(part, check) for part, build in CHECK_BUILDERS for check in build()]
