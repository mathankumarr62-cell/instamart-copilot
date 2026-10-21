"""TF-IDF retrieval over policy chunks with cosine similarity (task 2)."""
from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from instamart import config
from instamart.part_d.chunking import chunk_documents


class PolicyIndex:
    """A TfidfVectorizer fitted on chunk texts plus the chunk matrix it produced."""

    def __init__(self, chunks: list[dict]):
        self.chunks = chunks
        self.vectorizer = TfidfVectorizer()
        self.matrix = self.vectorizer.fit_transform([c["text"] for c in chunks])

    def retrieve(self, query: str, k: int = config.TOP_K) -> list[dict]:
        """Return the k most cosine-similar chunks as [{source, score, text}], best first."""
        scores = cosine_similarity(self.vectorizer.transform([query]), self.matrix)[0]
        order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))[:k]
        return [{"source": self.chunks[i]["source"], "score": round(float(scores[i]), 4),
                 "text": self.chunks[i]["text"]} for i in order]


@lru_cache(maxsize=None)
def get_index(overlap: int = config.CHUNK_OVERLAP) -> PolicyIndex:
    """Build (once) the index for 40-word chunks with the given overlap."""
    return PolicyIndex(chunk_documents(overlap))


def retrieve(query: str, k: int = config.TOP_K) -> list[dict]:
    """Retrieve from the default index (40 words, overlap 10)."""
    return get_index().retrieve(query, k)
