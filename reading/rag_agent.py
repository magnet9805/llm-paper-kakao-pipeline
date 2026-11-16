"""
RAG 에이전트 - 본 논문이 아닌 다른 논문(레퍼런스 / 공용 풀)에서 근거를 찾는다 (LLM 호출 없음).

두 가지 검색 범위:
- search_references(): 라우터 scope=refs_first. 레퍼런스 id로 범위를 좁히고 중요도로 가중.
- search_pool(): 라우터 scope=pool, 또는 통합 에이전트가 need_more_evidence를 낸 뒤.

둘 다 같은 순서를 따른다 (CLAUDE.md "RAG 에이전트"):
  메타데이터 필터링(별칭 사전) -> 후보가 적으면 필터 완화 -> 벡터/BM25 병렬 검색 -> RRF
  -> 2단계 보강(뽑힌 논문 중 전문이 있는 것만 청크 1~2개)

공용 풀 검색은 결과가 없거나 관련도가 낮으면 키워드 필터를 빼고 딱 1회 재검색한다
(LLM으로 쿼리를 다시 쓰지 않고 필터 완화로 처리 - 호출 수를 늘리지 않기 위함).
"""

from typing import TypedDict

from reading.retrieval import MIN_RELEVANCE, detail_chunks, keyword_candidates, select_papers
from reading.schemas import Evidence
from reading.store import ReadingStore


class SearchInfo(TypedDict):
    via: str  # "references" | "pool"
    filter_relaxed: bool  # 키워드 필터를 뺐는가
    retried: bool  # 관련도가 낮아 1회 재검색했는가
    found: bool  # 관련도 기준을 넘는 결과가 있었는가


def _to_evidence(
    store: ReadingStore, query: str, ranked: list[tuple[str, float]], via: str, start_index: int
) -> list[Evidence]:
    ids = [pid for pid, _ in ranked]
    metas = store.get_papers(ids)
    details = detail_chunks(store, query, ids)
    evidence = []
    for pid in ids:
        meta = metas.get(pid)
        if not meta:
            continue
        ev = Evidence(
            evidence_id=f"R{start_index + len(evidence)}", kind="other_paper", paper_id=pid,
            title=meta["title"], text=meta["abstract"], published=meta.get("published", ""), via=via,
        )
        if pid in details:
            ev["detail_chunks"] = details[pid]
        evidence.append(ev)
    return evidence


def search_references(
    store: ReadingStore, paper_id: str, query: str, keywords: list[str], start_index: int = 1
) -> tuple[list[Evidence], SearchInfo]:
    refs = store.get_references(paper_id)
    if not refs:
        # 레퍼런스가 아직 수집되지 않은 논문이면 공용 풀로 바로 넘어간다.
        return search_pool(store, paper_id, query, keywords, start_index=start_index)

    ref_ids = [r["paper_id"] for r in refs]
    importance = {r["paper_id"]: r["importance"] for r in refs}
    candidates, relaxed = keyword_candidates(store, keywords, within=ref_ids)
    ranked, best = select_papers(store, query, candidates, importance=importance, exclude={paper_id})
    info = SearchInfo(via="references", filter_relaxed=relaxed, retried=False, found=bool(ranked) and best >= MIN_RELEVANCE)
    return _to_evidence(store, query, ranked, "references", start_index), info


def search_pool(
    store: ReadingStore,
    paper_id: str,
    query: str,
    keywords: list[str],
    start_index: int = 1,
    exclude: set[str] = frozenset(),
    force_relax: bool = False,
) -> tuple[list[Evidence], SearchInfo]:
    """
    exclude: 이미 근거로 넘긴 논문 (레퍼런스 검색 결과 등) - 같은 논문을 두 번 넣지 않는다.
    force_relax: 처음부터 키워드 필터 없이 검색 (이미 필터 검색을 해본 뒤의 재검색).
    """
    exclude = set(exclude) | {paper_id}
    if force_relax:
        candidates, relaxed = None, True
    else:
        candidates, relaxed = keyword_candidates(store, keywords)
    ranked, best = select_papers(store, query, candidates, exclude=exclude)

    retried = False
    if (not ranked or best < MIN_RELEVANCE) and not relaxed:
        ranked, best = select_papers(store, query, None, exclude=exclude)
        relaxed, retried = True, True

    info = SearchInfo(via="pool", filter_relaxed=relaxed, retried=retried, found=bool(ranked) and best >= MIN_RELEVANCE)
    return _to_evidence(store, query, ranked, "pool", start_index), info
