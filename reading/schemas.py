"""
에이전트 <-> 저장소(ReadingStore) 사이에 오가는 데이터 형태.

기존 코드(collector.py 등)가 논문을 평범한 dict로 다루므로 여기서도 TypedDict를 쓴다 -
DB 구현 쪽에서는 sqlite3.Row/쿼리 결과를 dict로 바꿔 그대로 돌려주면 된다.

paper_id는 arXiv id 문자열이다 (예: "2211.17192"). HF Daily Papers의 id와
sent_papers.hf_id도 arXiv id라서, 발송 이력과 공용 풀을 같은 키로 이을 수 있다.
"""

from typing import Literal, NotRequired, TypedDict

SectionType = Literal[
    "abstract", "introduction", "related_work", "method",
    "experiments", "results", "discussion", "conclusion", "other",
]
QuestionType = Literal["result", "method", "numeric", "general"]
Target = Literal["paper", "rag"]
Scope = Literal["refs_first", "pool"]


class PaperMeta(TypedDict):
    """공용 풀 논문 1편의 메타데이터 (관계형 DB)."""
    paper_id: str
    title: str
    abstract: str
    published: NotRequired[str]  # "YYYY-MM-DD" - 답변에 연도를 밝힐 때 사용
    has_fulltext: NotRequired[bool]  # 전문 청크가 저장돼 있는가 (2단계 보강 여부 판단)


class Briefing(TypedDict):
    """발송 결정 시 생성되는 브리핑 (관계형 DB, paper_id로 바로 조회)."""
    paper_id: str
    problem: str
    method: str
    contribution: str
    limitation: str


class Reference(TypedDict):
    """본 논문 -> 레퍼런스 관계 1건 (관계형 DB)."""
    paper_id: str  # 레퍼런스 논문의 paper_id (공용 풀에 초록으로 들어가 있어야 함)
    importance: float  # 레퍼런스 중요도 점수 (CLAUDE.md 점수표, 대략 -35 ~ 95)


class ChunkHit(TypedDict):
    """전문 청크 검색 결과 1건 (벡터 DB)."""
    chunk_id: str
    paper_id: str
    section: str  # 원문 섹션 제목 (예: "4.2 Ablation on Draft Length")
    text: str  # 표/수식은 주변 설명과 같은 청크에 들어 있어야 함
    score: float  # 높을수록 관련도 높음. 리스트 안의 순위만 쓰므로 스케일은 상관없음
    section_type: NotRequired[SectionType]  # 적재 시 정규화된 섹션 종류 (있으면 섹션 가중에 사용)


class AbstractHit(TypedDict):
    """공용 풀 초록 검색 결과 1건 (벡터 DB 또는 BM25 인덱스)."""
    paper_id: str
    score: float


class PoolCoverage(TypedDict):
    """공용 풀이 어느 기간까지 갱신돼 있는지 - "검색 범위 명시"에 사용."""
    source: str  # 예: "arXiv"
    date_from: str  # "YYYY-MM"
    date_to: str  # "YYYY-MM"


# ---- 에이전트 내부에서 쓰는 형태 (저장소 구현과는 무관) ----

class Route(TypedDict):
    """라우터 LLM의 구조화된 출력."""
    targets: list[Target]
    question_type: QuestionType
    scope: Scope
    rewritten_query: str
    keywords: list[str]


class Evidence(TypedDict):
    """통합 에이전트에 넘기는 근거 1건."""
    evidence_id: str  # 프롬프트 안에서 인용용으로 쓰는 짧은 id (B, P1, R1, ...)
    kind: Literal["briefing", "paper_chunk", "other_paper"]
    paper_id: str
    title: str
    text: str
    section: NotRequired[str]
    published: NotRequired[str]
    via: NotRequired[Literal["references", "pool"]]  # other_paper가 어디서 찾아졌는지
    detail_chunks: NotRequired[list[str]]  # 2단계 보강: 이 논문 전문에서 가져온 청크 1~2개
