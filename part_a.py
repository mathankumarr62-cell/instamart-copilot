"""Entry script for Part A: python part_a.py (requires python generate_data.py first)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from instamart import io_utils  # noqa: E402
from instamart.part_a import pipeline  # noqa: E402

if __name__ == "__main__":
    io_utils.setup_logging()
    pipeline.run()
