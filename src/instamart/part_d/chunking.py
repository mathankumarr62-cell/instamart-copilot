"""Fixed-size word chunks with overlap over the five policy documents (task 1)."""
from pathlib import Path

from instamart import config


def chunk_words(words: list[str], size: int = config.CHUNK_WORDS, overlap: int = config.CHUNK_OVERLAP) -> list[list[str]]:
    """Split words into windows of `size` advancing by size - overlap; stop after the window reaching the end."""
    step = size - overlap
    if step <= 0:
        raise ValueError("overlap must be smaller than the chunk size")
    chunks, start = [], 0
    while True:
        chunks.append(words[start:start + size])
        if start + size >= len(words):
            return chunks
        start += step


def load_documents(folder: Path = config.POLICY_DIR) -> dict[str, str]:
    """Read every policy .txt file, keyed by file name, in sorted order."""
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(folder.glob("*.txt"))}


def chunk_documents(overlap: int = config.CHUNK_OVERLAP, size: int = config.CHUNK_WORDS,
                    folder: Path = config.POLICY_DIR) -> list[dict]:
    """Return [{source, chunk_index, text}] for every chunk of every policy document."""
    return [{"source": name, "chunk_index": i, "text": " ".join(words)}
            for name, text in load_documents(folder).items()
            for i, words in enumerate(chunk_words(text.split(), size, overlap))]
