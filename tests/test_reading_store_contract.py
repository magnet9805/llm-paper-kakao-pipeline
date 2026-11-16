"""
ReadingStore 계약 테스트 - 에이전트가 저장소에 기대하는 동작을 고정한다.

DB 파트 통합 시: 실제 구현(예: SqlReadingStore)을 아래 store fixture의 params에 추가하고
`uv run pytest tests/test_reading_store_contract.py`가 통과하면 에이전트 쪽은 수정 없이 붙는다.
SAMPLE_PAPER_ID는 그 저장소에 브리핑/전문 청크/레퍼런스가 모두 있는 발송 논문 id로 바꿔서 돌릴 것.
"""

import pytest

from reading.fake_store import FakeReadingStore
from reading.store import ReadingStore

SAMPLE_PAPER_ID = "test.00001"


@pytest.fixture(params=["fake"])
def store(request) -> ReadingStore:
    if request.param == "fake":
        return FakeReadingStore.from_fixture()
    raise ValueError(request.param)


def _descending(scores):
    return all(a >= b for a, b in zip(scores, scores[1:]))


def test_implements_protocol(store):
    assert isinstance(store, ReadingStore)


def test_get_papers_skips_unknown_ids(store):
    papers = store.get_papers([SAMPLE_PAPER_ID, "no-such-id"])
    assert set(papers) == {SAMPLE_PAPER_ID}
    p = papers[SAMPLE_PAPER_ID]
    assert p["title"] and p["abstract"]


def test_briefing_has_four_fields(store):
    b = store.get_briefing(SAMPLE_PAPER_ID)
    assert b is not None
    assert all(b[k] for k in ("problem", "method", "contribution", "limitation"))
    assert store.get_briefing("no-such-id") is None


def test_references_point_into_pool(store):
    refs = store.get_references(SAMPLE_PAPER_ID)
    assert refs
    ids = [r["paper_id"] for r in refs]
    # 레퍼런스는 공용 풀에 초록으로 들어가 있어야 RAG 에이전트가 검색할 수 있다.
    assert set(store.get_papers(ids)) == set(ids)
    assert all(isinstance(r["importance"], (int, float)) for r in refs)
    assert store.get_references("no-such-id") == []


def test_normalize_keywords_drops_unknown(store):
    ids = store.normalize_keywords(["Speculative Decoding", "speculative sampling", "zzz-not-a-keyword"])
    assert len(ids) == 1  # 동의어는 같은 id로, 사전에 없는 건 버림
    assert store.filter_pool_by_keywords(ids)


def test_abstract_search_respects_candidates_and_order(store):
    for search in (store.vector_search_abstracts, store.bm25_search_abstracts):
        everything = search("speculative decoding draft model", None, 5)
        assert everything and _descending([h["score"] for h in everything])
        subset = [h["paper_id"] for h in everything[:2]]
        limited = search("speculative decoding draft model", subset, 5)
        assert {h["paper_id"] for h in limited} <= set(subset)
        assert search("speculative decoding", [], 5) == []


def test_chunk_search_stays_inside_paper(store):
    for search in (store.vector_search_chunks, store.bm25_search_chunks):
        hits = search("speedup on HumanEval", [SAMPLE_PAPER_ID], 3)
        assert hits and len(hits) <= 3
        assert all(h["paper_id"] == SAMPLE_PAPER_ID for h in hits)
        assert all(h["chunk_id"] and h["section"] and h["text"] for h in hits)
        assert _descending([h["score"] for h in hits])


def test_pool_coverage(store):
    cov = store.pool_coverage()
    assert cov["source"] and cov["date_from"] <= cov["date_to"]
