"""
검색 로직 (LLM 호출 없음). 저장소는 ReadingStore 프로토콜로만 다룬다.

CLAUDE.md "에이전트 구성"의 확정 사항을 그대로 옮긴 것:
- 하이브리드 검색: 벡터 + BM25를 병렬 실행하고 Reciprocal Rank Fusion으로 합친다.
- 섹션 가중: 질문 유형에 맞는 섹션의 점수를 높인다 (제외하지는 않음).
- 수치 질문: 표/수치는 임베딩이 놓치기 쉬워서 BM25 쪽 비중을 높인다.
- 레퍼런스 검색: 중요도 점수로 가중.
- 메타데이터 필터 -> (후보가 적으면) 필터 완화 -> 병렬 검색 순서.
- 공용 풀 2단계 검색: 초록끼리 비교해 논문을 고르고, 뽑힌 논문 중 전문이 있는 것만 청크로 보강.

아래 상수들은 "미결 사항"(RRF 상위 개수 5~8 잠정 등)이거나 임베딩 모델에 따라 달라지는 값이라,
환경변수로 덮어쓸 수 있게 해 뒀다. 실제 데이터로 테스트하며 조정할 것.
"""

import os
from concurrent.futures import ThreadPoolExecutor

from reading.schemas import ChunkHit, QuestionType, SectionType
from reading.store import ReadingStore

RRF_K = 60  # RRF 표준 상수 (Cormack et al., 2009)
TOP_PAPERS = int(os.environ.get("READING_TOP_PAPERS", "6"))  # RRF 후 넘길 논문 수 (5~8 잠정)
TOP_PAPER_CHUNKS = int(os.environ.get("READING_TOP_PAPER_CHUNKS", "5"))  # 본 논문 청크 수
DETAIL_CHUNKS_PER_PAPER = 2  # 2단계 보강에서 논문당 붙일 전문 청크 수 (1~2)
SEARCH_DEPTH = 30  # RRF에 넣기 전 각 검색기에서 가져올 후보 수

# 벡터 검색 최고 점수가 이보다 낮으면 "관련도가 낮다"고 보고 필터를 완화해 1회 재검색한다.
# 임베딩 모델마다 코사인 분포가 달라서 실제 모델이 정해지면 반드시 다시 맞춰야 하는 값이다.
MIN_RELEVANCE = float(os.environ.get("READING_MIN_RELEVANCE", "0.2"))

SECTION_BOOST = 1.5
BOOSTED_SECTIONS: dict[QuestionType, set[SectionType]] = {
    "result": {"results", "experiments"},
    "numeric": {"results", "experiments"},
    "method": {"method"},
    "general": set(),
}
NUMERIC_BM25_WEIGHT = 1.5  # 수치 질문일 때 BM25 순위 리스트의 RRF 가중치 (벡터는 1.0)

IMPORTANCE_WEIGHT = 0.5  # 중요도 95점이면 점수 x1.5, -35점이면 약 x0.82
IMPORTANCE_MAX = 95.0

# section_type이 비어 있는 청크를 위한 최소한의 보정. 섹션 정규화는 원칙적으로 적재 단계의
# Instruction이 맡으므로(CLAUDE.md), 여기서는 흔한 영문 섹션 제목만 대충 맞춘다.
_HEADING_HINTS: list[tuple[SectionType, tuple[str, ...]]] = [
    ("results", ("result", "evaluation", "main finding")),
    ("experiments", ("experiment", "setup", "benchmark")),
    ("method", ("method", "approach", "model", "framework", "algorithm")),
]


def rrf(ranked_lists: list[list[str]], weights: list[float] | None = None) -> dict[str, float]:
    """Reciprocal Rank Fusion: score(d) = sum_i w_i / (RRF_K + rank_i(d))."""
    weights = weights or [1.0] * len(ranked_lists)
    fused: dict[str, float] = {}
    for ranked, w in zip(ranked_lists, weights):
        for rank, doc_id in enumerate(ranked, start=1):
            fused[doc_id] = fused.get(doc_id, 0.0) + w / (RRF_K + rank)
    return fused


def _parallel(f1, f2):
    """벡터 검색과 BM25를 동시에 실행한다 (원격 DB라면 왕복 시간이 겹쳐서 줄어든다)."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = pool.submit(f1), pool.submit(f2)
        return a.result(), b.result()


def section_type_of(chunk: ChunkHit) -> SectionType:
    if chunk.get("section_type"):
        return chunk["section_type"]
    heading = chunk["section"].lower()
    for stype, hints in _HEADING_HINTS:
        if any(h in heading for h in hints):
            return stype
    return "other"


def search_paper_chunks(
    store: ReadingStore, query: str, paper_id: str, question_type: QuestionType, k: int = TOP_PAPER_CHUNKS
) -> list[ChunkHit]:
    """본 논문 전문 안에서 하이브리드 검색 + 섹션 가중 (논문 분석 에이전트용)."""
    vec, bm = _parallel(
        lambda: store.vector_search_chunks(query, [paper_id], SEARCH_DEPTH),
        lambda: store.bm25_search_chunks(query, [paper_id], SEARCH_DEPTH),
    )
    by_id = {c["chunk_id"]: c for c in vec + bm}
    bm25_weight = NUMERIC_BM25_WEIGHT if question_type == "numeric" else 1.0
    fused = rrf([[c["chunk_id"] for c in vec], [c["chunk_id"] for c in bm]], [1.0, bm25_weight])

    boosted = BOOSTED_SECTIONS.get(question_type, set())
    for cid in fused:
        if section_type_of(by_id[cid]) in boosted:
            fused[cid] *= SECTION_BOOST

    ranked = sorted(fused, key=fused.get, reverse=True)[:k]
    return [{**by_id[cid], "score": fused[cid]} for cid in ranked]


def keyword_candidates(
    store: ReadingStore, keywords: list[str], within: list[str] | None = None, min_count: int = TOP_PAPERS
) -> tuple[list[str] | None, bool]:
    """
    메타데이터 필터링 + 필터 완화 (병렬 검색 이전 단계).

    within=None이면 공용 풀 전체, 리스트면 그 안(예: 레퍼런스 id)에서만 거른다.
    반환: (후보 id 목록 - None이면 "공용 풀 전체", 필터를 완화했는지 여부)
    """
    keyword_ids = store.normalize_keywords(keywords) if keywords else []
    if keyword_ids:
        filtered = store.filter_pool_by_keywords(keyword_ids)
        if within is not None:
            allowed = set(within)
            filtered = [pid for pid in filtered if pid in allowed]
        if len(filtered) >= min_count:
            return filtered, False
    # 정규화 결과가 없거나 후보가 너무 적으면 키워드 필터를 빼고 원래 범위로 되돌린다.
    return within, True


def select_papers(
    store: ReadingStore,
    query: str,
    candidate_ids: list[str] | None,
    k: int = TOP_PAPERS,
    importance: dict[str, float] | None = None,
    exclude: set[str] = frozenset(),
) -> tuple[list[tuple[str, float]], float]:
    """
    초록 단위 하이브리드 검색 (2단계 검색의 1단계 - "어떤 논문을 고를지").
    importance가 주어지면(레퍼런스 검색) RRF 점수에 중요도 가중을 곱한다.

    반환: ([(paper_id, 최종 점수)], 벡터 검색 최고 점수 - 관련도 판단용)
    """
    if candidate_ids is not None and not candidate_ids:
        return [], 0.0
    vec, bm = _parallel(
        lambda: store.vector_search_abstracts(query, candidate_ids, SEARCH_DEPTH),
        lambda: store.bm25_search_abstracts(query, candidate_ids, SEARCH_DEPTH),
    )
    vec = [h for h in vec if h["paper_id"] not in exclude]
    bm = [h for h in bm if h["paper_id"] not in exclude]
    fused = rrf([[h["paper_id"] for h in vec], [h["paper_id"] for h in bm]])

    if importance:
        for pid in fused:
            imp = max(-35.0, min(IMPORTANCE_MAX, importance.get(pid, 0.0)))
            fused[pid] *= 1 + IMPORTANCE_WEIGHT * imp / IMPORTANCE_MAX

    ranked = sorted(fused, key=fused.get, reverse=True)[:k]
    best_vector = max((h["score"] for h in vec), default=0.0)
    return [(pid, fused[pid]) for pid in ranked], best_vector


def detail_chunks(store: ReadingStore, query: str, paper_ids: list[str]) -> dict[str, list[str]]:
    """
    2단계 보강: 뽑힌 논문 중 전문이 있는 것만, 그 논문 안에서 질문과 가장 관련된 청크 1~2개.
    paper_id 필터가 걸린 벡터 검색 몇 번뿐이라 LLM 호출은 늘지 않는다.
    """
    metas = store.get_papers(paper_ids)
    out: dict[str, list[str]] = {}
    for pid in paper_ids:
        if not metas.get(pid, {}).get("has_fulltext"):
            continue
        hits = store.vector_search_chunks(query, [pid], DETAIL_CHUNKS_PER_PAPER)
        if hits:
            out[pid] = [f"[{h['section']}] {h['text']}" for h in hits]
    return out
