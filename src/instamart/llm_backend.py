"""Single import point for the supplied offline mock_llm.py (lives at the repo root, never edited)."""
import sys

from instamart import config

if str(config.ROOT) not in sys.path:
    sys.path.insert(0, str(config.ROOT))

import mock_llm  # noqa: E402

chat = mock_llm.chat
est_tokens = mock_llm.est_tokens
reset = mock_llm.reset
TransientLLMError = mock_llm.TransientLLMError
