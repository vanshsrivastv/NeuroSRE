"""Runbook knowledge base: chunking, embedding and semantic retrieval (RAG).

Runbooks are split into one chunk per "## " section, embedded with
all-MiniLM-L6-v2 (ChromaDB's built-in ONNX embedding function) and stored in a
persistent ChromaDB collection with metadata. If ChromaDB or the embedding
model is unavailable (e.g. no internet on first run), a BM25 keyword index is
used instead so the system keeps working.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .. import config

log = logging.getLogger(__name__)
COLLECTION = "runbooks"


@dataclass
class Runbook:
    id: str
    incident_type: str
    services: list[str]
    severity: str
    title: str
    text: str
    commands: list[str]
    path: Path


@dataclass
class Hit:
    runbook_id: str
    incident_type: str
    title: str
    section: str
    text: str
    score: float

    def as_dict(self) -> dict:
        return self.__dict__.copy()


# ---------------------------------------------------------------- parsing
def parse_runbook(path: Path) -> Runbook:
    raw = path.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n(.*)", raw, re.S)
    meta = dict(line.split(":", 1) for line in m.group(1).splitlines())
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    body = m.group(2).strip()
    title = re.search(r"^# (.+)$", body, re.M).group(1).strip()
    block = re.search(r"```neuroctl\n(.*?)```", body, re.S)
    commands = [c.strip() for c in block.group(1).splitlines() if c.strip()] if block else []
    return Runbook(meta["id"], meta["incident_type"], [s.strip() for s in meta["services"].split(",")],
                   meta["severity"], title, body, commands, path)


@lru_cache(maxsize=1)
def load_runbooks() -> dict[str, Runbook]:
    return {rb.id: rb for rb in (parse_runbook(p) for p in sorted(config.RUNBOOK_DIR.glob("*.md")))}


def chunk_runbook(rb: Runbook) -> list[tuple[str, str, dict]]:
    """Split a runbook into (chunk_id, text, metadata), one chunk per section."""
    chunks = []
    for sec in re.split(r"\n(?=## )", rb.text):
        if not sec.startswith("## "):
            continue
        name = sec.splitlines()[0][3:].strip()
        text = f"{rb.title} ({rb.id}) - {name}\n{sec.split(chr(10), 1)[1].strip()}"
        chunks.append((f"{rb.id}:{name.lower().replace(' ', '_')}", text,
                       {"runbook_id": rb.id, "incident_type": rb.incident_type, "title": rb.title,
                        "section": name, "severity": rb.severity, "services": ", ".join(rb.services)}))
    return chunks


def parse_command(line: str, service: str) -> dict:
    """'increase_pool {service} size=200' -> {'action':..., 'target':..., 'params':{...}}"""
    parts = line.replace("{service}", service).split()
    params = {}
    for p in parts[2:]:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k] = int(v) if v.isdigit() else v
    return {"action": parts[0], "target": parts[1] if len(parts) > 1 else service, "params": params}


# ---------------------------------------------------------------- BM25 fallback
class _BM25:
    def __init__(self, docs: list[tuple[str, str, dict]]):
        self.docs = docs
        self.toks = [self._tok(t) for _, t, _ in docs]
        self.avg = sum(map(len, self.toks)) / max(1, len(self.toks))
        df = Counter(w for t in self.toks for w in set(t))
        n = len(docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}

    @staticmethod
    def _tok(s: str) -> list[str]:
        return re.findall(r"[a-z0-9]+", s.lower())

    def query(self, q: str, n: int):
        qt = self._tok(q)
        scores = []
        for i, toks in enumerate(self.toks):
            tf = Counter(toks)
            s = sum(self.idf.get(w, 0) * tf[w] * 2.2 / (tf[w] + 1.2 * (0.25 + 0.75 * len(toks) / self.avg))
                    for w in qt if w in tf)
            scores.append((s, i))
        scores.sort(reverse=True)
        top = scores[:n]
        mx = top[0][0] if top and top[0][0] > 0 else 1
        return [(self.docs[i], s / mx) for s, i in top]


# ---------------------------------------------------------------- store
class KnowledgeBase:
    def __init__(self, persist_dir: Path | None = None):
        self.persist_dir = Path(persist_dir or config.CHROMA_DIR)
        self.runbooks = load_runbooks()
        self.chunks = [c for rb in self.runbooks.values() for c in chunk_runbook(rb)]
        self.backend = "bm25"
        self._collection = None
        self._bm25 = _BM25(self.chunks)
        try:
            import chromadb
            from chromadb.utils import embedding_functions

            client = chromadb.PersistentClient(path=str(self.persist_dir))
            ef = embedding_functions.DefaultEmbeddingFunction()   # ONNX all-MiniLM-L6-v2
            col = client.get_or_create_collection(COLLECTION, embedding_function=ef,
                                                  metadata={"hnsw:space": "cosine"})
            if col.count() != len(self.chunks):
                self._ingest(client, ef)
                col = client.get_collection(COLLECTION, embedding_function=ef)
            self._collection = col
            self.backend = "chromadb"
        except Exception as exc:  # pragma: no cover - depends on environment
            log.warning("ChromaDB unavailable (%s); using BM25 keyword retrieval", exc)

    def _ingest(self, client, ef) -> None:
        try:
            client.delete_collection(COLLECTION)
        except Exception:
            pass
        col = client.create_collection(COLLECTION, embedding_function=ef, metadata={"hnsw:space": "cosine"})
        ids, docs, metas = zip(*self.chunks)
        col.add(ids=list(ids), documents=list(docs), metadatas=list(metas))

    def search(self, query: str, k: int = 3) -> list[Hit]:
        """Return the k best runbooks (deduplicated), each with its best-matching chunk."""
        raw: list[tuple[tuple[str, str, dict], float]] = []
        if self._collection is not None:
            res = self._collection.query(query_texts=[query], n_results=min(len(self.chunks), k * 6))
            for cid, doc, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
                raw.append(((cid, doc, meta), 1 - dist))
        else:
            raw = self._bm25.query(query, k * 6)
        best: dict[str, Hit] = {}
        for (cid, doc, meta), score in raw:
            rid = meta["runbook_id"]
            if rid not in best or score > best[rid].score:
                best[rid] = Hit(rid, meta["incident_type"], meta["title"], meta["section"], doc, round(float(score), 3))
        return sorted(best.values(), key=lambda h: h.score, reverse=True)[:k]

    def get(self, runbook_id: str) -> Runbook | None:
        return self.runbooks.get(runbook_id)

    def by_type(self, incident_type: str) -> Runbook | None:
        return next((rb for rb in self.runbooks.values() if rb.incident_type == incident_type), None)
