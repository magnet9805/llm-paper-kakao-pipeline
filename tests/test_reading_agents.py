"""
검색 로직 + 그래프 흐름 테스트 (LLM 호출 없음 - 라우터/통합 에이전트를 가짜 함수로 주입).
실제 Gemini를 붙인 확인은 `uv run python -m reading.demo`로 한다.
"""

import pytest

from reading.fake_store import FakeReadingStore
from reading.graph import PaperNotFoundError, build_reading_graph
from reading.integrator import Decision
from reading.paper_agent import gather_paper_evidence
from reading.rag_agent import search_pool, search_references
from reading.retrieval import keyword_candidates, rrf, search_paper_chunks, select_papers
from reading.router import normalize_route
from reading.schemas import Route

PAPER = "test.00001"


@pytest.fixture
def store():
    return FakeReadingStore.from_fixture()


def make_route(**kw) -> Route:
    base = dict(targets=["paper", "rag"], question_type="general", scope="refs_first",
                rewritten_query="where does speculative decoding come from", keywords=["speculative decoding"])
    base.update(kw)
    return Route(**base)


# ---- retrieval ----

def test_rrf_rewards_agreement():
    fused = rrf([["a", "b", "c"], ["b", "a", "d"]])
    assert set(fused) == {"a", "b", "c", "d"}
    assert fused["a"] == fused["b"] > fused["c"] == fused["d"]


def test_section_boost_prefers_results_for_numeric(store):
    chunks = search_paper_chunks(store, "AdaDraft speedup HumanEval", PAPER, "numeric")
    assert chunks[0]["section_type"] == "results"
    method = search_paper_chunks(store, "how does AdaDraft decide when to stop drafting", PAPER, "method")
    assert method[0]["section_type"] == "method"


def test_keyword_filter_relaxes_when_too_few(store):
    cands, relaxed = keyword_candidates(store, ["speculative decoding"], min_count=3)
    assert not relaxed and "2309.08168" in cands
    cands, relaxed = keyword_candidates(store, ["speculative decoding"], min_count=100)
    assert relaxed and cands is None  # 필터를 빼고 공용 풀 전체로
    cands, relaxed = keyword_candidates(store, ["unknown-term"], within=["x", "y"])
    assert relaxed and cands == ["x", "y"]  # 정규화 실패 -> 원래 범위(레퍼런스) 유지


def test_importance_weighting_demotes_dataset_paper(store):
    refs = {r["paper_id"]: r["importance"] for r in store.get_references(PAPER)}
    query = "math reasoning benchmark speculative decoding"
    plain, _ = select_papers(store, query, list(refs))
    weighted, _ = select_papers(store, query, list(refs), importance=refs)
    rank = lambda ranked: [p for p, _ in ranked].index("2110.14168")
    assert rank(weighted) > rank(plain)


# ---- agents ----

def test_paper_agent_always_includes_briefing(store):
    ev = gather_paper_evidence(store, PAPER, make_route(question_type="numeric", rewritten_query="speedup"))
    assert ev[0]["evidence_id"] == "B" and ev[0]["kind"] == "briefing"
    assert all(e["paper_id"] == PAPER for e in ev)


def test_reference_search_finds_origin_and_excludes_self(store):
    ev, info = search_references(store, PAPER, "original speculative decoding algorithm rejection sampling", ["speculative decoding"])
    assert info["via"] == "references"
    ids = [e["paper_id"] for e in ev]
    assert PAPER not in ids
    assert ids[0] == "2211.17192"
    assert ev[0]["via"] == "references" and ev[0].get("detail_chunks")  # 전문 있는 논문만 2단계 보강
    assert "2309.08168" not in ids  # 레퍼런스가 아닌 논문은 안 나온다


def test_pool_search_finds_non_reference_paper(store):
    ev, info = search_pool(store, PAPER, "self-speculative decoding without a separate draft model skipping layers",
                           ["speculative decoding"])
    assert info["via"] == "pool"
    assert ev[0]["paper_id"] == "2309.08168"
    assert PAPER not in [e["paper_id"] for e in ev]


def test_router_output_is_validated():
    r = normalize_route({"targets": ["rag", "bogus", "rag"], "question_type": "x", "scope": "y",
                         "rewritten_query": " ", "keywords": ["a", " ", "b"]}, "원 질문")
    assert r == Route(targets=["rag"], question_type="general", scope="refs_first",
                      rewritten_query="원 질문", keywords=["a", "b"])


# ---- graph ----

class FakeLLM:
    def __init__(self, route: Route, decisions: list[Decision]):
        self.route, self.decisions = route, list(decisions)
        self.integrate_calls: list[tuple[list[str], bool]] = []

    def route_fn(self, question, history, title):
        return self.route

    def integrate_fn(self, question, history, title, evidence, final):
        self.integrate_calls.append(([e["evidence_id"] for e in evidence], final))
        return self.decisions.pop(0)


def answer(**kw) -> Decision:
    base = dict(action="answer", from_paper="", from_other_papers="", general="", cited_ids=[], found=True)
    base.update(kw)
    return Decision(**base)


def run(store, llm, question="질문"):
    graph = build_reading_graph(store, llm.route_fn, llm.integrate_fn)
    return graph.invoke({"paper_id": PAPER, "question": question, "history": []})["result"]


def test_graph_runs_both_agents_in_two_llm_calls(store):
    llm = FakeLLM(make_route(), [answer(from_paper="브리핑 기준 설명 [B]", from_other_papers="원조는 [R1]", cited_ids=["B", "R1"])])
    result = run(store, llm)
    ids, final = llm.integrate_calls[0]
    assert "B" in ids and any(i.startswith("R") for i in ids) and not final
    assert result["llm_calls"] == 2
    assert [c["evidence_id"] for c in result["citations"]] == ["B", "R1"]
    assert result["scope_note"].startswith("검색 범위:")
    assert "[본 논문 내용]" in result["answer"] and "[다른 논문 근거]" in result["answer"]


def test_graph_paper_only_skips_rag(store):
    llm = FakeLLM(make_route(targets=["paper"]), [answer(from_paper="x [P1]", cited_ids=["P1"])])
    result = run(store, llm)
    assert all(not i.startswith("R") for i in llm.integrate_calls[0][0])
    assert result["searches"] == [] and result["scope_note"] is None


def test_need_more_evidence_triggers_one_pool_search(store):
    llm = FakeLLM(
        make_route(targets=["rag"]),
        [Decision(action="need_more_evidence", missing="self-speculative decoding layer skipping"),
         answer(from_other_papers="후속 접근은 [R7]", cited_ids=["R7"])],
    )
    result = run(store, llm)
    assert len(llm.integrate_calls) == 2
    first_ids, first_final = llm.integrate_calls[0]
    second_ids, second_final = llm.integrate_calls[1]
    assert not first_final and second_final  # 두 번째는 answer만 허용되는 final 모드
    assert second_ids[: len(first_ids)] == first_ids  # 기존 근거 id는 그대로 유지
    assert result["llm_calls"] == 3
    assert [s["via"] for s in result["searches"]] == ["references", "pool"]
    # 레퍼런스에서 이미 나온 논문은 풀 검색에서 다시 나오지 않는다
    assert len({c["paper_id"] for c in result["citations"]}) == len(result["citations"])


def test_invented_citations_are_removed_and_not_found_is_honest(store):
    llm = FakeLLM(make_route(targets=["rag"]),
                  [answer(from_other_papers="어떤 논문 [R99]에 따르면", cited_ids=["R99"], found=True)])
    result = run(store, llm)
    assert "[R99]" not in result["answer"]
    assert result["citations"] == [] and result["found"] is False
    assert "찾기 어려웠어요" in result["scope_note"]


def test_unknown_paper_raises(store):
    llm = FakeLLM(make_route(), [])
    graph = build_reading_graph(store, llm.route_fn, llm.integrate_fn)
    with pytest.raises(PaperNotFoundError):
        graph.invoke({"paper_id": "nope", "question": "q", "history": []})
