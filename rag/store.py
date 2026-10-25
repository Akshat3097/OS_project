"""
RAG knowledge base: topic-based chunks with metadata, retrieved by
  * BM25 keyword search (always available, no model needed), and
  * dense embeddings from an Ollama embedding model (e.g. nomic-embed-text) when built,
combined with Reciprocal Rank Fusion (RRF) so each method covers the other's blind spots
(exact terms like "SRTF" vs. paraphrased questions).

Pipeline (matches proposal section 5.1):
  raw documents -> text extraction -> cleaning -> de-duplication -> topic-based chunking
  -> metadata -> embeddings -> vector store (numpy file + JSON)
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np

import config

SUBTOPIC_KEYWORDS = {
    "FCFS": ["first come", "first-come", "fcfs", "convoy", "fifo scheduling", "first in, first out"],
    "SJF": ["shortest job", "sjf", "exponential averag"],
    "SRTF": ["shortest remaining", "srtf", "preemptive sjf", "stcf", "shortest time-to-completion", "psjf"],
    "Round Robin": ["round robin", "time quantum", "time slice", "quantum"],
    "Priority scheduling": ["priority", "aging", "starvation"],
    "Scheduling basics": ["turnaround", "waiting time", "response time", "gantt", "throughput", "dispatcher"],
    "Semaphores": ["semaphore", "wait(", "signal(", "producer", "consumer", "bounded buffer"],
    "Critical section": ["critical section", "race condition", "peterson", "mutual exclusion", "test_and_set"],
    "Deadlocks": ["deadlock", "circular wait", "hold and wait", "resource allocation graph"],
    "Banker's algorithm": ["banker", "safe state", "safe sequence", "need matrix", "available"],
    "Multilevel queues": ["multilevel", "mlfq", "mlq", "feedback queue", "priority boost"],
    "Multiprocessor scheduling": ["multiprocessor", "affinity", "load balancing", "smp", "amp ", "multicore", "work stealing"],
    "Locks and hardware": ["test-and-set", "test_and_set", "compare-and-swap", "compare_and_swap", "spinlock", "spin",
                           "bakery", "atomic"],
    "Monitors and classic problems": ["monitor", "condition variable", "readers", "writers", "dining", "philosopher",
                                      "chopstick", "readcount"],
    "IPC": ["inter-process", "interprocess", "message passing", "shared memory", "mailbox", "pipe", "send(", "receive(",
            "socket", "signal handler", "sigint"],
}
SYNC_SUBTOPICS = {"Semaphores", "Critical section", "Deadlocks", "Banker's algorithm", "Locks and hardware",
                  "Monitors and classic problems", "IPC"}
ALGO_TO_SUBTOPIC = {"FCFS": "FCFS", "SJF": "SJF", "SRTF": "SRTF", "RR": "Round Robin",
                    "PRIORITY_NP": "Priority scheduling", "PRIORITY_P": "Priority scheduling",
                    "BANKERS": "Banker's algorithm", "SEMAPHORE": "Semaphores"}
TOKEN = re.compile(r"[a-z0-9_]+")
STOPWORDS = set("""a an the is are was were be been to of in on at for and or but if then than so as by with from
it its this that these those what which who whom how why when where do does did can could should would will i
me my you your we our they their he she his her there here not no yes into about over under up down out also
just only very more most some any each every all both such same other own too s t""".split())


def tokenize(text: str) -> list[str]:
    text = text.lower().replace("i/o", "io").replace("i / o", "io")
    return [w for w in TOKEN.findall(text) if w not in STOPWORDS]


# Different books name the same idea differently (OSTEP: STCF = SRTF, FIFO = FCFS, P()/V() = wait/signal).
SYNONYMS = {"srtf": ["stcf", "psjf"], "stcf": ["srtf"], "psjf": ["srtf"], "fcfs": ["fifo"], "fifo": ["fcfs"],
            "rr": ["round", "robin"], "quantum": ["slice"], "slice": ["quantum"], "semaphore": ["semaphores"],
            "wait": ["sem_wait"], "signal": ["sem_post", "post"], "io": ["input", "output"], "mlq": ["multilevel"],
            "multilevel": ["mlq"], "mutex": ["lock"], "lock": ["mutex"],
            "deadlock": ["deadlocks"], "banker": ["bankers", "banker's"], "tat": ["turnaround"], "wt": ["waiting"],
            "mlfq": ["multilevel", "feedback"], "p": ["wait"], "v": ["signal"], "proberen": ["wait"],
            "verhogen": ["signal"], "ipc": ["communication"], "philosopher": ["philosophers", "dining"],
            "philosophers": ["philosopher", "dining"]}


def expand(tokens: list[str]) -> list[str]:
    out = list(tokens)
    for t in tokens:
        out += SYNONYMS.get(t, [])
    return out


def infer_subtopic(text: str) -> str:
    low = text.lower()
    scores = {k: sum(low.count(w) for w in ws) for k, ws in SUBTOPIC_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "General"


def clean(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)          # ligatures from PDFs (ﬁ → fi) so words match
    text = text.replace("­", "").replace("\x0c", " ")
    text = re.sub(r"-\n(\w)", r"\1", text)          # re-join hyphenated line breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ----------------------------------------------------------------------------- loading + chunking

def _front_matter(raw: str) -> tuple[dict, str]:
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            meta = {}
            for line in raw[3:end].strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            return meta, raw[end + 4:]
    return {}, raw


MAX_SECTION_WORDS = 200

# Friendly names for OSTEP chapter files (the file names the author uses on pages.cs.wisc.edu/~remzi/OSTEP/)
OSTEP_TITLES = {"cpu-intro": "OSTEP ch. 4 – The Abstraction: The Process", "cpu-api": "OSTEP ch. 5 – Process API",
                "cpu-mechanisms": "OSTEP ch. 6 – Limited Direct Execution", "cpu-sched": "OSTEP ch. 7 – Scheduling: Introduction",
                "cpu-sched-mlfq": "OSTEP ch. 8 – Multi-level Feedback Queue",
                "cpu-sched-lottery": "OSTEP ch. 9 – Proportional Share", "cpu-sched-multi": "OSTEP ch. 10 – Multiprocessor Scheduling",
                "threads-intro": "OSTEP ch. 26 – Concurrency: An Introduction", "threads-api": "OSTEP ch. 27 – Thread API",
                "threads-locks": "OSTEP ch. 28 – Locks", "threads-locks-usage": "OSTEP ch. 29 – Lock-based Data Structures",
                "threads-cv": "OSTEP ch. 30 – Condition Variables", "threads-sema": "OSTEP ch. 31 – Semaphores",
                "threads-bugs": "OSTEP ch. 32 – Common Concurrency Problems"}

# Small preference for the course's own material when scores are close (multiplies the fused score).
TYPE_WEIGHT = {"Teacher's notes": 1.06, "Solutions": 1.04, "Previous-year question paper": 1.04, "Textbook (OSTEP)": 0.98}


def chunk_markdown(path: Path) -> list[dict]:
    meta, body = _front_matter(path.read_text(encoding="utf-8"))
    title_m = re.search(r"^# (.+)$", body, re.M)
    title = title_m.group(1).strip() if title_m else path.stem
    chunks = []
    for sec in re.split(r"^## ", body, flags=re.M)[1:]:
        heading, _, text = sec.partition("\n")
        text = clean(text)
        if not text:
            continue
        words = text.split()
        # long sections are split into overlapping pieces so a retrieved chunk fits the model's context
        pieces = [text] if len(words) <= MAX_SECTION_WORDS else \
            [" ".join(words[i:i + MAX_SECTION_WORDS]) for i in range(0, len(words) - 40, MAX_SECTION_WORDS - 40)]
        for piece in pieces:
            sub = meta.get("subtopic") or infer_subtopic(heading + " " + piece)
            chunks.append({"text": f"{title} — {heading.strip()}: {piece}",
                           "meta": {"source": meta.get("source", path.name), "file": path.name,
                                    "topic": meta.get("topic", "Process Synchronization" if sub in SYNC_SUBTOPICS else "CPU Scheduling"),
                                    "subtopic": sub, "section": heading.strip(),
                                    "difficulty": meta.get("difficulty", "Intermediate"),
                                    "type": meta.get("type", "Notes")}})
    if not chunks and body.strip():
        chunks = _window_chunks(clean(body), {"source": meta.get("source", path.name), "file": path.name})
    return chunks


def _source_type(name: str) -> str:
    low = name.lower()
    if any(k in low for k in ("solution", "answer", "key", "soln")):
        return "Solutions"
    if any(k in low for k in ("pyq", "question", "paper", "exam", "cat1", "cat2", "cat-", "fat", "midsem", "endsem")):
        return "Previous-year question paper"
    if any(k in low for k in ("teacher", "class", "notes", "unit", "module")):
        return "Teacher's notes"
    if any(k in low for k in ("slide", "ppt", "lecture")):
        return "Lecture slides"
    if any(k in low for k in ("lab", "manual")):
        return "Lab manual"
    if low.startswith(("cpu-sched", "threads-", "cpu-intro", "cpu-api", "cpu-mechanisms")) or "ostep" in low:
        return "Textbook (OSTEP)"
    if any(k in low for k in ("book", "chapter", "silberschatz", "galvin")):
        return "Textbook"
    return "Notes"


def _window_chunks(text: str, base_meta: dict, size: int = 220, overlap: int = 40) -> list[dict]:
    words = text.split()
    out = []
    step = size - overlap
    for i in range(0, max(1, len(words) - overlap), step):
        piece = " ".join(words[i:i + size])
        if len(piece.split()) < 25:
            continue
        sub = infer_subtopic(piece)
        out.append({"text": piece, "meta": {**base_meta, "subtopic": sub,
                                             "topic": "Process Synchronization" if sub in SYNC_SUBTOPICS else "CPU Scheduling",
                                             "difficulty": "Intermediate"}})
    return out


def load_pdf(path: Path) -> list[dict]:
    try:
        from pypdf import PdfReader
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("Install pypdf to ingest PDFs: pip install pypdf") from e
    reader = PdfReader(str(path))
    chunks = []
    for page_no, page in enumerate(reader.pages, start=1):
        text = clean(page.extract_text() or "")
        if len(text.split()) < 25:
            continue
        chunks += _window_chunks(text, {"source": OSTEP_TITLES.get(path.stem, path.name), "file": path.name, "page": page_no,
                                        "type": _source_type(path.name)})
    return chunks


def load_text(path: Path) -> list[dict]:
    return _window_chunks(clean(path.read_text(encoding="utf-8", errors="ignore")),
                          {"source": path.name, "file": path.name, "type": _source_type(path.name)})


def load_documents(dirs: list[Path]) -> tuple[list[dict], list[str]]:
    chunks, log = [], []
    for d in dirs:
        if not d.exists():
            continue
        for path in sorted(d.rglob("*")):
            if not path.is_file() or path.name.startswith("."):
                continue
            try:
                if path.suffix.lower() == ".md":
                    got = chunk_markdown(path)
                elif path.suffix.lower() == ".pdf":
                    got = load_pdf(path)
                elif path.suffix.lower() == ".txt":
                    got = load_text(path)
                else:
                    continue
                chunks += got
                log.append(f"{path.name}: {len(got)} chunks")
            except Exception as e:  # keep going if one file is broken
                log.append(f"{path.name}: FAILED ({e})")
    # de-duplicate identical chunks (same text from repeated slides/pages)
    seen, unique = set(), []
    for c in chunks:
        h = hashlib.md5(" ".join(c["text"].lower().split()).encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            c["id"] = h[:12]
            unique.append(c)
    if len(unique) < len(chunks):
        log.append(f"removed {len(chunks) - len(unique)} duplicate chunks")
    return unique, log


# ----------------------------------------------------------------------------- retrieval

def _index_text(chunk: dict) -> str:
    """Text used for keyword search: the chunk plus its section heading twice more, so a section titled
    "Peterson's solution" ranks first for "Peterson" even if the body names it only once."""
    sec = chunk["meta"].get("section") or ""
    return chunk["text"] + (" " + sec) * 2


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.toks = [tokenize(d) for d in docs]
        self.avgdl = sum(len(t) for t in self.toks) / max(1, len(self.toks))
        df = Counter()
        for t in self.toks:
            df.update(set(t))
        n = len(self.toks)
        self.idf = {w: math.log(1 + (n - f + 0.5) / (f + 0.5)) for w, f in df.items()}
        self.tf = [Counter(t) for t in self.toks]

    def scores(self, query: str) -> list[float]:
        q = expand(tokenize(query))
        out = []
        for tf, toks in zip(self.tf, self.toks):
            s = 0.0
            for w in q:
                if w in tf:
                    f = tf[w]
                    s += self.idf.get(w, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(toks) / self.avgdl))
            out.append(s)
        return out


class KnowledgeBase:
    def __init__(self, index_dir: Path = config.INDEX_DIR):
        self.index_dir = Path(index_dir)
        self.chunks: list[dict] = []
        self.embeddings: np.ndarray | None = None
        self.embed_model: str | None = None
        self.bm25: BM25 | None = None

    # ------------------------------------------------------------------ build / load
    def build(self, client=None, embed: bool = False, embed_model: str = config.EMBED_MODEL,
              dirs: list[Path] | None = None) -> list[str]:
        dirs = dirs or [config.KNOWLEDGE_DIR, config.SOURCES_DIR]
        self.chunks, log = load_documents(dirs)
        self.bm25 = BM25([_index_text(c) for c in self.chunks])
        self.embeddings, self.embed_model = None, None
        if embed and client is not None and self.chunks:
            vecs = []
            batch = 16
            for i in range(0, len(self.chunks), batch):
                vecs += client.embed([c["text"] for c in self.chunks[i:i + batch]], model=embed_model)
            arr = np.array(vecs, dtype=np.float32)
            arr /= np.linalg.norm(arr, axis=1, keepdims=True) + 1e-9
            self.embeddings, self.embed_model = arr, embed_model
            log.append(f"embedded {len(vecs)} chunks with {embed_model} (dim {arr.shape[1]})")
        self.save()
        log.append(f"index saved: {len(self.chunks)} chunks")
        return log

    def save(self) -> None:
        self.index_dir.mkdir(parents=True, exist_ok=True)
        (self.index_dir / "chunks.json").write_text(json.dumps(self.chunks, ensure_ascii=False, indent=1), encoding="utf-8")
        emb_path = self.index_dir / "embeddings.npy"
        if self.embeddings is not None:
            np.save(emb_path, self.embeddings)
        elif emb_path.exists():
            emb_path.unlink()
        (self.index_dir / "meta.json").write_text(json.dumps({"embed_model": self.embed_model,
                                                              "n_chunks": len(self.chunks)}), encoding="utf-8")

    def load(self) -> bool:
        p = self.index_dir / "chunks.json"
        if not p.exists():
            return False
        self.chunks = json.loads(p.read_text(encoding="utf-8"))
        self.bm25 = BM25([_index_text(c) for c in self.chunks])
        emb = self.index_dir / "embeddings.npy"
        meta = json.loads((self.index_dir / "meta.json").read_text(encoding="utf-8")) if (self.index_dir / "meta.json").exists() else {}
        if emb.exists():
            self.embeddings = np.load(emb)
            self.embed_model = meta.get("embed_model")
        return True

    def load_or_build(self) -> None:
        if not self.load():
            self.build()

    @property
    def mode(self) -> str:
        return f"hybrid (BM25 + {self.embed_model})" if self.embeddings is not None else "BM25 keyword search"

    # ------------------------------------------------------------------ search
    def search(self, query: str, k: int = config.TOP_K, client=None, subtopic: str | None = None,
               types: set[str] | None = None) -> list[dict]:
        """types: keep only chunks of these source types (e.g. {"Teacher's notes"}); empty result if none match."""
        if not self.chunks:
            return []
        idx = list(range(len(self.chunks)))
        if types:
            idx = [i for i in idx if self.chunks[i]["meta"].get("type") in types]
            if not idx:
                return []
        if subtopic:
            filt = [i for i in idx if self.chunks[i]["meta"].get("subtopic") == subtopic]
            idx = filt or idx
        bm = self.bm25.scores(query)
        rank_lists = [sorted(idx, key=lambda i: -bm[i])]
        if self.embeddings is not None and client is not None:
            try:
                q = np.array(client.embed([query], model=self.embed_model)[0], dtype=np.float32)
                q /= np.linalg.norm(q) + 1e-9
                sims = self.embeddings @ q
                rank_lists.append(sorted(idx, key=lambda i: -sims[i]))
            except Exception:
                pass  # embedding model unavailable -> keyword search only
        fused: dict[int, float] = {}
        for ranks in rank_lists:
            for r, i in enumerate(ranks):
                fused[i] = fused.get(i, 0) + 1 / (60 + r + 1)
        for i in fused:
            fused[i] *= TYPE_WEIGHT.get(self.chunks[i]["meta"].get("type"), 1.0)
        best = sorted(fused, key=lambda i: -fused[i])[:k]
        if len(rank_lists) == 1:
            best = [i for i in best if bm[i] > 0] or best[:1]
        return [{**self.chunks[i], "score": round(fused[i], 4)} for i in best]
