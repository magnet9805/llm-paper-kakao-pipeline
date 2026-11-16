"""
"AI와 함께 읽기" 질의응답 그래프 (로드맵 7-4/7-5의 에이전트 파트).

    START -> router ─┬─> paper_agent ─┐
                     └─> rag_agent ───┴─> integrator ─┬─> finalize -> END
                                             ▲        │ (need_more_evidence, 1회만)
                                             └─ pool_search

- router(LLM 1회)가 targets에 따라 paper_agent / rag_agent를 고르고, 둘 다면 병렬 실행된다.
- rag_agent는 scope=refs_first면 레퍼런스부터, pool이면 공용 풀부터 검색한다.
- integrator(LLM)가 need_more_evidence를 내면 pool_search로 공용 풀을 한 번 더 검색한 뒤
  integrator를 final 모드(answer만 허용)로 다시 부른다 -> LLM 호출 최대 3회.
- finalize는 LLM 없이 답변을 조립한다: 근거 id 검증(없는 id 인용 제거), 세 칸 구분 표시,
  검색 범위 안내 문구.

저장소는 build_reading_graph(store)로 주입받는다 - DB 파트 통합 시 store만 바꾸면 된다.
LLM 노드(route_fn/integrate_fn)도 주입 가능해서, 테스트에서는 LLM 없이 그래프를 돌린다.
"""

import operator
import re
from typing import Annotated, Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from reading.integrator import Decision, integrate
from reading.paper_agent import gather_paper_evidence
from reading.rag_agent import search_pool, search_references
from reading.router import route_question
from reading.schemas import Evidence, Route
from reading.store import ReadingStore, get_store


class PaperNotFoundError(Exception):
    """질문 대상 논문이 저장소에 없을 때 (server 쪽에서 404로 바꾸면 된다)."""


class ReadingState(TypedDict, total=False):
    # 입력
    paper_id: str
    question: str
    history: list[dict]
    # 중간 결과
    paper_title: str
    route: Route
    paper_evidence: list[Evidence]
    rag_evidence: list[Evidence]
    rag_searches: list[dict]  # 실행한 다른 논문 검색 기록 (rag_agent.SearchInfo)
    final_round: bool
    decision: Decision
    llm_calls: Annotated[int, operator.add]
    # 출력
    result: dict


RouteFn = Callable[[str, list[dict], str], Route]
IntegrateFn = Callable[[str, list[dict], str, list[Evidence], bool], Decision]

_CITATION = re.compile(r"\[([BPR]\d*)\]")


def _format_month(ym: str) -> str:
    """'2026-10' -> '26년 10월'"""
    try:
        year, month = ym.split("-")[:2]
        return f"{year[2:]}년 {month}월"
    except ValueError:
        return ym


def compose_result(state: ReadingState, store: ReadingStore) -> dict:
    decision = state.get("decision") or Decision(action="need_more_evidence", missing="")
    evidence = state.get("paper_evidence", []) + state.get("rag_evidence", [])
    by_id = {ev["evidence_id"]: ev for ev in evidence}

    if decision["action"] != "answer":
        # final 모드에서는 answer만 허용하므로 정상적으로는 오지 않는 경로 (방어 코드).
        decision = Decision(action="answer", from_paper="", from_other_papers="", general="",
                            cited_ids=[], found=False)

    def clean(text: str) -> str:
        # 근거 목록에 없는 id 인용([R9] 등)은 지어낸 출처일 수 있으니 지운다.
        return _CITATION.sub(lambda m: m.group(0) if m.group(1) in by_id else "", text).strip()

    sections = {
        "paper": clean(decision.get("from_paper", "")),
        "other_papers": clean(decision.get("from_other_papers", "")),
        "general": clean(decision.get("general", "")),
    }
    cited = list(dict.fromkeys(
        [i for i in decision.get("cited_ids", []) if i in by_id]
        + [m for text in sections.values() for m in _CITATION.findall(text) if m in by_id]
    ))
    citations = [
        {
            "evidence_id": i, "paper_id": by_id[i]["paper_id"], "title": by_id[i]["title"],
            "kind": by_id[i]["kind"], "section": by_id[i].get("section"), "via": by_id[i].get("via"),
        }
        for i in cited
    ]

    found = bool(decision.get("found")) and bool(citations)
    rag_searches = state.get("rag_searches", [])
    scope_note = None
    if rag_searches:
        cov = store.pool_coverage()
        span = f"{cov['source']}에서 {_format_month(cov['date_from'])} ~ {_format_month(cov['date_to'])}까지의 논문"
        used_other = any(c["kind"] == "other_paper" for c in citations)
        if used_other:
            scope_note = f"검색 범위: {span}"
        else:
            scope_note = f"{span}을 확인한 결과, 관련된 논문을 찾기 어려웠어요 ㅠㅠ"

    parts = []
    if sections["paper"]:
        parts.append(f"[본 논문 내용]\n{sections['paper']}")
    if sections["other_papers"]:
        parts.append(f"[다른 논문 근거]\n{sections['other_papers']}")
    if sections["general"]:
        parts.append(f"[일반 설명 · 출처 없음]\n{sections['general']}")
    if not parts:
        parts.append("죄송해요, 이 질문에 답할 근거를 찾지 못했어요.")
    if scope_note:
        parts.append(f"({scope_note})")

    return {
        "answer": "\n\n".join(parts),
        "sections": sections,
        "citations": citations,
        "found": found,
        "scope_note": scope_note,
        "route": state.get("route"),
        "searches": rag_searches,
        "llm_calls": state.get("llm_calls", 0),
    }


def build_reading_graph(
    store: ReadingStore, route_fn: RouteFn = route_question, integrate_fn: IntegrateFn = integrate
):
    def router_node(state: ReadingState) -> dict:
        meta = store.get_papers([state["paper_id"]]).get(state["paper_id"])
        if not meta:
            raise PaperNotFoundError(state["paper_id"])
        route = route_fn(state["question"], state.get("history", []), meta["title"])
        return {"paper_title": meta["title"], "route": route, "llm_calls": 1,
                "paper_evidence": [], "rag_evidence": [], "rag_searches": [], "final_round": False}

    def pick_agents(state: ReadingState) -> list[str]:
        targets = state["route"]["targets"] or ["paper", "rag"]
        return [{"paper": "paper_agent", "rag": "rag_agent"}[t] for t in targets]

    def paper_agent_node(state: ReadingState) -> dict:
        return {"paper_evidence": gather_paper_evidence(store, state["paper_id"], state["route"])}

    def rag_agent_node(state: ReadingState) -> dict:
        route = state["route"]
        search = search_references if route["scope"] == "refs_first" else search_pool
        evidence, info = search(store, state["paper_id"], route["rewritten_query"], route["keywords"])
        return {"rag_evidence": evidence, "rag_searches": [info]}

    def integrator_node(state: ReadingState) -> dict:
        evidence = state.get("paper_evidence", []) + state.get("rag_evidence", [])
        decision = integrate_fn(
            state["question"], state.get("history", []), state["paper_title"], evidence,
            state.get("final_round", False),
        )
        return {"decision": decision, "llm_calls": 1}

    def after_integrator(state: ReadingState) -> str:
        if state["decision"]["action"] == "need_more_evidence" and not state.get("final_round"):
            return "pool_search"
        return "finalize"

    def pool_search_node(state: ReadingState) -> dict:
        route = state["route"]
        existing = state.get("rag_evidence", [])
        searches = state.get("rag_searches", [])
        missing = state["decision"].get("missing", "")
        query = f"{route['rewritten_query']} {missing}".strip()
        # 공용 풀을 이미 키워드 필터로 검색했다면, 이번에는 필터 없이 넓혀서 찾는다.
        already_pool = any(s["via"] == "pool" for s in searches)
        evidence, info = search_pool(
            store, state["paper_id"], query, route["keywords"],
            start_index=len(existing) + 1, exclude={ev["paper_id"] for ev in existing},
            force_relax=already_pool,
        )
        return {"rag_evidence": existing + evidence, "rag_searches": searches + [info], "final_round": True}

    def finalize_node(state: ReadingState) -> dict:
        return {"result": compose_result(state, store)}

    g = StateGraph(ReadingState)
    g.add_node("router", router_node)
    g.add_node("paper_agent", paper_agent_node)
    g.add_node("rag_agent", rag_agent_node)
    g.add_node("integrator", integrator_node)
    g.add_node("pool_search", pool_search_node)
    g.add_node("finalize", finalize_node)
    g.add_edge(START, "router")
    g.add_conditional_edges("router", pick_agents, ["paper_agent", "rag_agent"])
    g.add_edge("paper_agent", "integrator")
    g.add_edge("rag_agent", "integrator")
    g.add_conditional_edges("integrator", after_integrator, ["pool_search", "finalize"])
    g.add_edge("pool_search", "integrator")
    g.add_edge("finalize", END)
    return g.compile()


_default_graph = None


def ask(paper_id: str, question: str, history: list[dict] | None = None, store: ReadingStore | None = None) -> dict:
    """
    "AI와 함께 읽기" 질문 한 턴. 무상태 - 멀티턴이면 프론트가 history를 매번 보낸다
    ([{"role": "user"|"assistant", "content": str}, ...], 이번 질문은 넣지 않음).

    반환: compose_result()의 dict - answer(표시용 텍스트), sections, citations, found,
    scope_note, route, searches, llm_calls
    """
    global _default_graph
    if store is None:
        if _default_graph is None:
            _default_graph = build_reading_graph(get_store())
        graph = _default_graph
    else:
        graph = build_reading_graph(store)
    final = graph.invoke({"paper_id": paper_id, "question": question, "history": history or []})
    return final["result"]
