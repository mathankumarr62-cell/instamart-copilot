"""Standard-library HTTP server for the dashboard: static files from app/static plus a small JSON API.

Binds to 127.0.0.1 only, accepts JSON bodies of at most MAX_BODY_CHARS characters, answers every error
as JSON with a proper status code and never serves a file outside app/static."""
import json
import logging
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from instamart import config
from instamart.dashboard import data, live

log = logging.getLogger(__name__)

STATIC_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                ".js": "text/javascript; charset=utf-8"}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                                "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"),
}
MAX_TEXT_FIELD = 4000
CUSTOMER_PATH = re.compile(r"/api/customers/([^/]+)")      # used with fullmatch


class ApiError(Exception):
    """An error answered as {"error": message} with the given HTTP status."""

    def __init__(self, status: HTTPStatus, message: str):
        super().__init__(message)
        self.status, self.message = status, message


def _text_field(body: dict, name: str, required: bool = True) -> str | None:
    """A non-empty string field of at most MAX_TEXT_FIELD characters (or None when optional and absent)."""
    value = body.get(name)
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise ApiError(HTTPStatus.BAD_REQUEST, f"'{name}' must be a string")
    if len(value) > MAX_TEXT_FIELD:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"'{name}' is longer than {MAX_TEXT_FIELD} characters")
    return value


def _int_field(body: dict, name: str, default: int, low: int, high: int) -> int:
    """An optional integer field within [low, high]."""
    value = body.get(name, default)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ApiError(HTTPStatus.BAD_REQUEST, f"'{name}' must be an integer from {low} to {high}")
    return value


def _customer_field(body: dict) -> str | None:
    """Optional customer id such as C0007 (blank means none)."""
    value = _text_field(body, "customer_id", required=False)
    if value is None or not value.strip():
        return None
    value = value.strip().upper()
    if not data.CUSTOMER_ID.fullmatch(value):
        raise ApiError(HTTPStatus.BAD_REQUEST, "'customer_id' must look like C0007")
    return value


def post_triage(body: dict) -> dict:
    """POST /api/triage/try {text, prompt?, customer_id?}."""
    prompt = body.get("prompt", "few_shot")
    if prompt not in live.PROMPTS:
        raise ApiError(HTTPStatus.BAD_REQUEST, "'prompt' must be few_shot or zero_shot")
    return live.try_ticket(_text_field(body, "text"), prompt, _customer_field(body))


def post_policy(body: dict) -> dict:
    """POST /api/policy/ask {question}."""
    question = _text_field(body, "question")
    if not question.strip():
        raise ApiError(HTTPStatus.BAD_REQUEST, "'question' must not be empty")
    return live.ask_policy(question)


def post_agent(body: dict) -> dict:
    """POST /api/agent/run {customer_id?, message, max_iterations?, token_limit?} (demo ledger only)."""
    message = _text_field(body, "message")
    if not message.strip():
        raise ApiError(HTTPStatus.BAD_REQUEST, "'message' must not be empty")
    return live.run_agent_demo(message, _customer_field(body),
                               _int_field(body, "max_iterations", config.AGENT_MAX_ITERATIONS, 1, 12),
                               _int_field(body, "token_limit", config.AGENT_TOKEN_LIMIT, 50, 20000))


GET_ROUTES = {"/api/overview": lambda q: data.overview(refresh="refresh" in q),
              "/api/part-a": lambda q: data.part_a(), "/api/part-b": lambda q: data.part_b(),
              "/api/part-c": lambda q: data.part_c(), "/api/part-d": lambda q: data.part_d()}
POST_ROUTES = {"/api/triage/try": post_triage, "/api/policy/ask": post_policy, "/api/agent/run": post_agent,
               "/api/agent/reset": lambda body: live.reset_demo()}


def resolve_static(url_path: str, root: Path = config.STATIC_DIR) -> Path | None:
    """Map a URL path to a file inside root, or None for anything outside it or of an unserved type."""
    rel = unquote(url_path).lstrip("/") or "index.html"
    if "\x00" in rel or "\\" in rel or any(part in ("..", "") for part in rel.split("/")):
        return None
    base = root.resolve()
    target = (base / rel).resolve()
    if not target.is_relative_to(base) or not target.is_file() or target.suffix not in STATIC_TYPES:
        return None
    return target


class DashboardHandler(BaseHTTPRequestHandler):
    """Serves app/static and the /api/* JSON endpoints."""

    server_version = "InstamartCopilot/1.0"
    sys_version = ""

    def log_message(self, fmt: str, *args) -> None:
        """Send access logs to the logging module instead of stderr."""
        log.info("%s %s", self.address_string(), fmt % args)

    def _send(self, status: HTTPStatus, body: bytes, content_type: str, extra: dict | None = None) -> None:
        """Write one complete response with the security headers."""
        self.send_response(status)
        headers = {"Content-Type": content_type, "Content-Length": str(len(body)), **SECURITY_HEADERS,
                   **(extra or {})}
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: HTTPStatus, payload: dict, extra: dict | None = None) -> None:
        """Send a JSON response that is never cached."""
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", {"Cache-Control": "no-store", **(extra or {})})

    def _error(self, status: HTTPStatus, message: str, extra: dict | None = None) -> None:
        """Send {"error": message} with the given status."""
        self._json(status, {"error": message, "status": int(status)}, extra)

    def _host_allowed(self) -> bool:
        """Only accept requests addressed to this loopback server (blocks DNS-rebinding)."""
        port = self.server.server_address[1]
        return self.headers.get("Host", "") in {f"127.0.0.1:{port}", f"localhost:{port}"}

    def _dispatch(self, handler) -> None:
        """Run a route handler and translate every failure into a JSON error."""
        try:
            self._json(HTTPStatus.OK, handler())
        except ApiError as exc:
            self._error(exc.status, exc.message)
        except FileNotFoundError as exc:
            log.warning("missing file for %s: %s", self.path, exc)
            self._error(HTTPStatus.SERVICE_UNAVAILABLE,
                        "Outputs are missing: run python generate_data.py and python run_all.py first.")
        except Exception:                                  # noqa: BLE001 - last-resort JSON 500
            log.exception("unhandled error for %s", self.path)
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "Internal error; see the server log.")

    def do_GET(self) -> None:
        """Static files and read-only API views."""
        if not self._host_allowed():
            return self._error(HTTPStatus.BAD_REQUEST, "unexpected Host header")
        url = urlsplit(self.path)
        if url.path in POST_ROUTES:
            return self._error(HTTPStatus.METHOD_NOT_ALLOWED, "use POST", {"Allow": "POST"})
        if url.path in GET_ROUTES:
            query = parse_qs(url.query)
            return self._dispatch(lambda: GET_ROUTES[url.path](query))
        match = CUSTOMER_PATH.fullmatch(url.path)
        if match:
            return self._dispatch(lambda: self._customer(unquote(match.group(1))))
        if url.path.startswith("/api/"):
            return self._error(HTTPStatus.NOT_FOUND, "unknown API endpoint")
        target = resolve_static(url.path)
        if target is None:
            return self._error(HTTPStatus.NOT_FOUND, "not found")
        self._send(HTTPStatus.OK, target.read_bytes(), STATIC_TYPES[target.suffix], {"Cache-Control": "no-cache"})

    do_HEAD = do_GET

    @staticmethod
    def _customer(raw_id: str) -> dict:
        """GET /api/customers/<id>."""
        customer_id = raw_id.strip().upper()
        if not data.CUSTOMER_ID.fullmatch(customer_id):
            raise ApiError(HTTPStatus.BAD_REQUEST, "customer id must look like C0007")
        found = data.customer(customer_id)
        if found is None:
            raise ApiError(HTTPStatus.NOT_FOUND, f"customer {customer_id} not found")
        return found

    def _read_body(self) -> dict:
        """Read and validate a JSON object body of at most MAX_BODY_CHARS characters."""
        if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
            raise ApiError(HTTPStatus.LENGTH_REQUIRED, "chunked bodies are not accepted; send Content-Length")
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            raise ApiError(HTTPStatus.LENGTH_REQUIRED, "Content-Length header required") from None
        if length < 0 or length > config.MAX_BODY_CHARS * 4:          # UTF-8 uses at most 4 bytes per character
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"body over {config.MAX_BODY_CHARS} characters")
        if not self.headers.get("Content-Type", "").lower().startswith("application/json"):
            raise ApiError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "Content-Type must be application/json")
        try:
            text = self.rfile.read(length).decode("utf-8")
        except UnicodeDecodeError:
            raise ApiError(HTTPStatus.BAD_REQUEST, "body must be UTF-8") from None
        if len(text) > config.MAX_BODY_CHARS:
            raise ApiError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, f"body over {config.MAX_BODY_CHARS} characters")
        try:
            body = json.loads(text)
        except json.JSONDecodeError:
            raise ApiError(HTTPStatus.BAD_REQUEST, "body must be valid JSON") from None
        if not isinstance(body, dict):
            raise ApiError(HTTPStatus.BAD_REQUEST, "body must be a JSON object")
        return body

    def do_POST(self) -> None:
        """Live demo endpoints."""
        if not self._host_allowed():
            return self._error(HTTPStatus.BAD_REQUEST, "unexpected Host header")
        path = urlsplit(self.path).path
        if path not in POST_ROUTES:
            if path in GET_ROUTES or CUSTOMER_PATH.fullmatch(path):
                return self._error(HTTPStatus.METHOD_NOT_ALLOWED, "use GET", {"Allow": "GET"})
            return self._error(HTTPStatus.NOT_FOUND, "unknown API endpoint")
        try:
            body = self._read_body()
        except ApiError as exc:
            self.close_connection = True                   # the unread body must not be parsed as a request
            return self._error(exc.status, exc.message)
        self._dispatch(lambda: POST_ROUTES[path](body))

    def _not_allowed(self) -> None:
        """Every other method."""
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed", {"Allow": "GET, HEAD, POST"})

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = _not_allowed


def make_server(port: int = config.APP_PORT) -> ThreadingHTTPServer:
    """Create (but do not start) the dashboard server on 127.0.0.1:port; port 0 picks a free port."""
    server = ThreadingHTTPServer((config.APP_HOST, port), DashboardHandler)
    server.daemon_threads = True
    return server
