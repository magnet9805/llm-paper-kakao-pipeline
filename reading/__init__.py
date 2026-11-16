"""
AI와 함께 읽기 (로드맵 7번) - 질의응답 에이전트 패키지.

구성:
- schemas.py     : 에이전트와 저장소 사이에 오가는 데이터 형태 (TypedDict)
- store.py       : ReadingStore 프로토콜 - DB 파트와의 "계약". 에이전트는 이것만 안다.
- fake_store.py  : 테스트용 인메모리 구현 (fixtures/sample_data.json을 읽음)
- retrieval.py   : RRF, 섹션 가중, 중요도 가중, 2단계 공용 풀 검색 같은 순수 검색 로직
- router.py      : 라우터 LLM (1회)
- paper_agent.py : 논문 분석 에이전트 (본 논문 안에서만 검색, LLM 호출 없음)
- rag_agent.py   : RAG 에이전트 (레퍼런스/공용 풀 검색, LLM 호출 없음)
- integrator.py  : 통합 에이전트 LLM (answer | need_more_evidence)
- graph.py       : 위 노드들을 LangGraph로 연결 + ask() 진입점
"""

from reading.graph import ask, build_reading_graph

__all__ = ["ask", "build_reading_graph"]
