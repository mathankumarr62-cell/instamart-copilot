"""Retrieval-augmented policy answers through the mock POLICY ASSISTANT (task 3)."""
from instamart import config
from instamart.llm_backend import chat
from instamart.part_d.retrieval import PolicyIndex, get_index

SYSTEM_PROMPT = ("You are the Instamart POLICY ASSISTANT. Answer only from the CONTEXT provided. "
                 "If the context does not contain the answer, say: I could not find that information "
                 "in the policy documents.")
FALLBACK_PREFIX = "I could not find"


def build_user_message(question: str, chunks: list[dict]) -> str:
    """CONTEXT:, each chunk as [<source>] on its own line followed by its text, then QUESTION: and the question."""
    context = "\n".join(f"[{c['source']}]\n{c['text']}" for c in chunks)
    return "CONTEXT:\n" + context + "\nQUESTION:\n" + question


def answer(question: str, index: PolicyIndex | None = None) -> dict:
    """Retrieve three chunks and ask the model; return {answer, sources}."""
    chunks = (index or get_index()).retrieve(question, config.TOP_K)
    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_message(question, chunks)}]
    text = chat(messages).choices[0].message.content
    return {"answer": text, "sources": [c["source"] for c in chunks]}
