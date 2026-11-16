"""
논문 분석 에이전트 - 본 논문 안에서만 근거를 찾는다 (LLM 호출 없음).

- 브리핑(문제/방법/기여/한계)은 질문과 상관없이 항상 근거로 넣는다.
- 전문 청크는 하이브리드 검색 + 질문 유형별 섹션 가중 (retrieval.search_paper_chunks).

LLM 호출 예산(질문당 2~3회: 라우터 + 통합)을 지키기 위해, "에이전트"지만 판단은 라우터가
이미 내려준 question_type/rewritten_query로 대신하고 여기서는 검색만 한다.
"""

from reading.retrieval import search_paper_chunks
from reading.schemas import Evidence, Route
from reading.store import ReadingStore


def gather_paper_evidence(store: ReadingStore, paper_id: str, route: Route) -> list[Evidence]:
    meta = store.get_papers([paper_id]).get(paper_id)
    title = meta["title"] if meta else paper_id
    evidence: list[Evidence] = []

    briefing = store.get_briefing(paper_id)
    if briefing:
        evidence.append(Evidence(
            evidence_id="B", kind="briefing", paper_id=paper_id, title=title, section="브리핑",
            text=(
                f"문제: {briefing['problem']}\n방법: {briefing['method']}\n"
                f"기여: {briefing['contribution']}\n한계: {briefing['limitation']}"
            ),
        ))

    chunks = search_paper_chunks(store, route["rewritten_query"], paper_id, route["question_type"])
    for i, c in enumerate(chunks, start=1):
        evidence.append(Evidence(
            evidence_id=f"P{i}", kind="paper_chunk", paper_id=paper_id, title=title,
            section=c["section"], text=c["text"],
        ))

    # 전문 청크가 아직 없으면(발송 결정 시 전문 수집 실패 등) 초록이라도 근거로 남긴다.
    if not chunks and meta:
        evidence.append(Evidence(
            evidence_id="P1", kind="paper_chunk", paper_id=paper_id, title=title,
            section="Abstract", text=meta["abstract"],
        ))
    return evidence
