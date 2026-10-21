"""Entry script for Part B: python part_b.py (requires part_a.py to have run)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from instamart import io_utils  # noqa: E402
from instamart.part_b import pipeline  # noqa: E402

if __name__ == "__main__":
    io_utils.setup_logging()
    pipeline.run()
