"""Retrieval and grounding evaluation on policy_eval.csv (task 4)."""
import pandas as pd

from instamart import config
from instamart.part_d.chunking import chunk_documents
from instamart.part_d.rag import FALLBACK_PREFIX, answer
from instamart.part_d.retrieval import PolicyIndex

NO_DOC = "NONE"


def load_eval() -> pd.DataFrame:
    """Read the 14 evaluation questions (empty expected_fact stays an empty string)."""
    return pd.read_csv(config.POLICY_EVAL, keep_default_na=False)


def evaluate(overlap: int) -> dict:
    """Run every question against a fresh index with the given overlap and score it."""
    chunks = chunk_documents(overlap)
    index = PolicyIndex(chunks)
    rows = []
    for q in load_eval().itertuples(index=False):
        result = answer(q.question, index)
        answerable = q.expected_doc != NO_DOC
        rows.append({"question": q.question, "expected_doc": q.expected_doc, "expected_fact": q.expected_fact,
                     "answerable": answerable, "sources": result["sources"], "answer": result["answer"],
                     "doc_in_top3": answerable and q.expected_doc in result["sources"],
                     "fact_in_answer": answerable and q.expected_fact in result["answer"],
                     "fallback": result["answer"].startswith(FALLBACK_PREFIX)})
    answerable = [r for r in rows if r["answerable"]]
    unanswerable = [r for r in rows if not r["answerable"]]
    return {"overlap": overlap, "chunks": len(chunks),
            "answerable": len(answerable), "unanswerable": len(unanswerable),
            "doc_in_top3": sum(r["doc_in_top3"] for r in answerable),
            "fact_in_answer": sum(r["fact_in_answer"] for r in answerable),
            "fallback_on_unanswerable": sum(r["fallback"] for r in unanswerable),
            "failures": [r for r in answerable if not (r["doc_in_top3"] and r["fact_in_answer"])]
                        + [r for r in unanswerable if not r["fallback"]],
            "rows": rows}
