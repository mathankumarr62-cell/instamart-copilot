"""Run every implemented part in order: python run_all.py (requires python generate_data.py first)."""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from instamart import io_utils  # noqa: E402
from instamart.part_a import pipeline as part_a  # noqa: E402
from instamart.part_b import pipeline as part_b  # noqa: E402
from instamart.part_c import pipeline as part_c  # noqa: E402
from instamart.part_d import pipeline as part_d  # noqa: E402

PARTS = [("A", part_a.run), ("B", part_b.run), ("C", part_c.run), ("D", part_d.run)]

if __name__ == "__main__":
    io_utils.setup_logging()
    for name, run in PARTS:
        logging.getLogger("run_all").info("running Part %s", name)
        run()
