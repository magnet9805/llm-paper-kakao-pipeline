"""
ReadingStore의 테스트용 인메모리 구현 - DB 파트 통합 전까지 에이전트 개발/테스트에 쓴다.

fixtures/sample_data.json을 읽어 메모리에 올리고, 외부 의존성 없이 검색을 흉내낸다:
- "벡터 검색": 글자 3-gram 빈도 벡터의 코사인 유사도 (임베딩 모델 흉내 - 의미 검색은 못 하지만
  단어 형태가 조금 달라도 걸리는 정도의 차이는 BM25와 구분된다)
- BM25: 표준 Okapi BM25 (k1=1.5, b=0.75)를 후보 문서 집합 위에서 바로 계산

실제 벡터 DB·임베딩 모델·BM25 구현 방식은 CLAUDE.md의 "미결 사항"이라 일부러 여기서 정하지
않는다 - 이 파일은 계약(store.ReadingStore)을 만족하는 가짜일 뿐이고, 실제 구현은 DB 파트가
같은 메서드 시그니처로 만들면 된다.
"""

import json
import math
import re
from collections import Counter
from pathlib import Path

from reading.schemas import AbstractHit, Briefing, ChunkHit, PaperMeta, PoolCoverage, Reference

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_data.json"

_STOPWORDS = {
    "a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "is", "are", "was", "with",
    "by", "we", "our", "this", "that", "it", "as", "at", "be", "from", "which", "how", "what",
}


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS]


def _trigram_vector(text: str) -> Counter:
    vec: Counter = Counter()
    for tok in _tokens(text):
        padded = f"#{tok}#"
        vec.update(padded[i : i + 3] for i in range(len(padded) - 2))
    return vec


def _cosine(a: Counter, b: Counter) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b[k] for k, v in a.items() if k in b)
    return dot / (math.sqrt(sum(v * v for v in a.values())) * math.sqrt(sum(v * v for v in b.values())))


def _bm25(query: str, docs: dict[str, str], k1: float = 1.5, b: float = 0.75) -> dict[str, float]:
    tokenized = {doc_id: _tokens(text) for doc_id, text in docs.items()}
    n = len(tokenized)
    if n == 0:
        return {}
    avgdl = sum(len(t) for t in tokenized.values()) / n or 1.0
    df: Counter = Counter()
    for toks in tokenized.values():
        df.update(set(toks))
    scores = {}
    for doc_id, toks in tokenized.items():
        tf = Counter(toks)
        score = 0.0
        for q in set(_tokens(query)):
            if q not in tf:
                continue
            idf = math.log(1 + (n - df[q] + 0.5) / (df[q] + 0.5))
            score += idf * tf[q] * (k1 + 1) / (tf[q] + k1 * (1 - b + b * len(toks) / avgdl))
        scores[doc_id] = score
    return scores


def _top(scores: dict[str, float], k: int) -> list[tuple[str, float]]:
    ranked = sorted(((i, s) for i, s in scores.items() if s > 0), key=lambda x: x[1], reverse=True)
    return ranked[:k]


class FakeReadingStore:
    def __init__(self, data: dict):
        self._papers: dict[str, dict] = {p["paper_id"]: p for p in data["papers"]}
        self._briefings: dict[str, Briefing] = {b["paper_id"]: b for b in data["briefings"]}
        self._references: dict[str, list[Reference]] = data["references"]
        self._chunks: dict[str, dict] = {c["chunk_id"]: c for c in data["chunks"]}
        self._coverage: PoolCoverage = data["coverage"]
        self._alias_to_id = {
            alias.lower(): kid for kid, aliases in data["keyword_aliases"].items() for alias in aliases
        }

    @classmethod
    def from_fixture(cls, path: Path = FIXTURE_PATH) -> "FakeReadingStore":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    # ---- 관계형 DB ----
    def get_papers(self, paper_ids: list[str]) -> dict[str, PaperMeta]:
        out = {}
        for pid in paper_ids:
            p = self._papers.get(pid)
            if p:
                out[pid] = PaperMeta(
                    paper_id=pid, title=p["title"], abstract=p["abstract"],
                    published=p.get("published", ""), has_fulltext=p.get("has_fulltext", False),
                )
        return out

    def get_briefing(self, paper_id: str) -> Briefing | None:
        return self._briefings.get(paper_id)

    def get_references(self, paper_id: str) -> list[Reference]:
        return list(self._references.get(paper_id, []))

    def normalize_keywords(self, keywords: list[str]) -> list[str]:
        ids = []
        for kw in keywords:
            kid = self._alias_to_id.get(kw.strip().lower())
            if kid and kid not in ids:
                ids.append(kid)
        return ids

    def filter_pool_by_keywords(self, keyword_ids: list[str]) -> list[str]:
        wanted = set(keyword_ids)
        return [pid for pid, p in self._papers.items() if wanted & set(p.get("keyword_ids", []))]

    def pool_coverage(self) -> PoolCoverage:
        return self._coverage

    # ---- 벡터 DB / BM25 인덱스 ----
    def _abstract_docs(self, candidate_ids: list[str] | None) -> dict[str, str]:
        ids = self._papers.keys() if candidate_ids is None else [i for i in candidate_ids if i in self._papers]
        return {pid: f"{self._papers[pid]['title']}. {self._papers[pid]['abstract']}" for pid in ids}

    def vector_search_abstracts(self, query, candidate_ids, k) -> list[AbstractHit]:
        qv = _trigram_vector(query)
        scores = {pid: _cosine(qv, _trigram_vector(text)) for pid, text in self._abstract_docs(candidate_ids).items()}
        return [AbstractHit(paper_id=pid, score=s) for pid, s in _top(scores, k)]

    def bm25_search_abstracts(self, query, candidate_ids, k) -> list[AbstractHit]:
        scores = _bm25(query, self._abstract_docs(candidate_ids))
        return [AbstractHit(paper_id=pid, score=s) for pid, s in _top(scores, k)]

    def _chunk_docs(self, paper_ids: list[str]) -> dict[str, str]:
        wanted = set(paper_ids)
        return {cid: f"{c['section']}. {c['text']}" for cid, c in self._chunks.items() if c["paper_id"] in wanted}

    def _chunk_hit(self, chunk_id: str, score: float) -> ChunkHit:
        c = self._chunks[chunk_id]
        hit = ChunkHit(chunk_id=chunk_id, paper_id=c["paper_id"], section=c["section"], text=c["text"], score=score)
        if "section_type" in c:
            hit["section_type"] = c["section_type"]
        return hit

    def vector_search_chunks(self, query, paper_ids, k) -> list[ChunkHit]:
        qv = _trigram_vector(query)
        scores = {cid: _cosine(qv, _trigram_vector(text)) for cid, text in self._chunk_docs(paper_ids).items()}
        return [self._chunk_hit(cid, s) for cid, s in _top(scores, k)]

    def bm25_search_chunks(self, query, paper_ids, k) -> list[ChunkHit]:
        scores = _bm25(query, self._chunk_docs(paper_ids))
        return [self._chunk_hit(cid, s) for cid, s in _top(scores, k)]
