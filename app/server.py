"""Optional dashboard: python app/server.py [--port 8000], then open http://127.0.0.1:8000 (Ctrl+C stops it).

Read-mostly view of the graded outputs; live demos write only to state/demo/. Run run_all.py first."""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from instamart import config, io_utils  # noqa: E402
from instamart.dashboard.server import make_server  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Instamart Copilot dashboard (127.0.0.1 only)")
    parser.add_argument("--port", type=int, default=config.APP_PORT)
    args = parser.parse_args()
    io_utils.setup_logging()
    server = make_server(args.port)
    logging.getLogger("app").info("dashboard on http://%s:%d (Ctrl+C to stop)", *server.server_address[:2])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.getLogger("app").info("stopping")
    finally:
        server.server_close()
