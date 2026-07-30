"""
Collector/Filter/Summarizer를 LangGraph의 StateGraph 노드로 그래프화한다 (로드맵 5번).

기존에는 main.py/server.py가 collect_papers()(collector+filter가 이미 합쳐진 함수)
-> summarize_papers()를 순서대로 그냥 파이썬 함수 호출로 이어붙였다. 여기서는 그
세 단계(수집/필터/요약)를 명시적인 그래프 노드로 나눠서 표현한다. 지금 당장은
선형(START -> collector -> filter -> summarizer -> END) 그래프라 실질 동작은 바뀌지
않지만, 다음 로드맵 단계들(RAGAS 품질 평가 노드 추가, 요약 실패 시 재시도/분기 등)을
그래프에 자연스럽게 끼워 넣을 수 있는 구조를 미리 만들어두는 것이 목적이다.

mcp_server.py를 호출하지 않고 collector.py/summarizer.py를 그대로 import해서 쓴다 -
같은 프로세스 안에서 도는 파이프라인이라 프로토콜 왕복을 거칠 이유가 없다
(CLAUDE.md "MCP 서버" 섹션의 설계 판단과 동일한 이유 - MCP는 이 앱 바깥에서
재사용하기 위한 별도 진입점이지, 내부 호출을 대체하는 게 아니다).
"""

from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from collector import fetch_top_daily_papers, filter_by_keywords
from summarizer import summarize_papers


class PipelineState(TypedDict):
    target_date: str | None
    top_n: int
    clusters: dict | None
    seen_ids: set | None
    papers_per_send: int
    raw_papers: list[dict]
    filtered_papers: list[dict]
    summarized_papers: list[dict]


def collector_node(state: PipelineState) -> dict:
    papers = fetch_top_daily_papers(target_date=state["target_date"], top_n=state["top_n"])
    return {"raw_papers": papers}


def filter_node(state: PipelineState) -> dict:
    matched = filter_by_keywords(
        state["raw_papers"], clusters=state["clusters"], seen_ids=state["seen_ids"]
    )
    return {"filtered_papers": matched}


def summarizer_node(state: PipelineState) -> dict:
    selected = state["filtered_papers"][: state["papers_per_send"]]
    if not selected:
        # 매칭된 후보가 없으면 Gemini 클라이언트를 만들 필요도 없이 바로 끝낸다.
        return {"summarized_papers": []}
    return {"summarized_papers": summarize_papers(selected)}


_graph = StateGraph(PipelineState)
_graph.add_node("collector", collector_node)
_graph.add_node("filter", filter_node)
_graph.add_node("summarizer", summarizer_node)
_graph.add_edge(START, "collector")
_graph.add_edge("collector", "filter")
_graph.add_edge("filter", "summarizer")
_graph.add_edge("summarizer", END)
pipeline = _graph.compile()


def run_pipeline(
    target_date: str | None = None,
    top_n: int = 30,
    clusters: dict | None = None,
    seen_ids: set | None = None,
    papers_per_send: int = 3,
) -> PipelineState:
    """
    수집 -> 필터 -> 요약을 한 번에 실행한다. main.py/server.py가 기존에
    collect_papers() + summarize_papers()를 직접 이어붙이던 자리를 대체한다.

    반환값은 그래프의 최종 state 전체다 - 최종 결과물은 result["summarized_papers"]
    지만, 중간 결과(result["filtered_papers"] 등)도 그대로 남아있어 호출하는 쪽에서
    로깅이나 디버깅에 쓸 수 있다.
    """
    return pipeline.invoke(
        {
            "target_date": target_date,
            "top_n": top_n,
            "clusters": clusters,
            "seen_ids": seen_ids,
            "papers_per_send": papers_per_send,
        }
    )
