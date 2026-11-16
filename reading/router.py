"""
라우터 LLM - 질문당 맨 앞에서 1회만 호출해서, 어떤 에이전트를 어떤 범위로 돌릴지 구조화해서 받는다.

출력(schemas.Route):
  targets         : ["paper"] / ["rag"] / ["paper", "rag"] - 둘 다면 LangGraph에서 병렬 실행
  question_type   : result | method | numeric | general - 논문 분석 에이전트의 섹션 가중에 사용
  scope           : refs_first | pool - RAG 에이전트가 레퍼런스부터 볼지, 공용 풀부터 볼지
  rewritten_query : 이전 대화 맥락을 풀어 쓴 영어 검색 질의 (논문 원문이 영어라서)
  keywords        : 영어 키워드 - 별칭 사전 정규화 -> 메타데이터 필터링에 사용
"""

from google.genai import types

from reading.llm import call_function, format_history
from reading.schemas import Route

SYSTEM_PROMPT = (
    "너는 논문 질의응답 시스템의 라우터다. 사용자가 읽고 있는 '본 논문'에 대한 질문을 보고 "
    "route_question 함수를 반드시 한 번 호출해라. 일반 텍스트로 답하지 마라.\n\n"
    "판단 기준:\n"
    "- targets: 본 논문 내용만으로 답할 수 있으면 [\"paper\"], 다른 논문(선행연구, 비교 대상, "
    "후속 연구, 다른 기법)이 필요하면 [\"rag\"], 둘 다 필요하면 [\"paper\", \"rag\"]. "
    "애매하면 둘 다 넣어라.\n"
    "- question_type: 실험 결과/성능을 묻으면 result, 방법/알고리즘/구조를 묻으면 method, "
    "구체적인 수치/표 값을 묻으면 numeric, 그 외는 general.\n"
    "- scope: 선행연구, 비교, '이 방법은 어디서 왔나', 본 논문이 인용한 논문에 관한 질문이면 "
    "refs_first. 본 논문과 직접 관련 없는 다른 연구나 후속 연구를 찾는 질문이면 pool. "
    "targets에 rag가 없으면 refs_first로 둬라.\n"
    "- rewritten_query: 이전 대화의 지시어(그거, 이 방법 등)를 풀어서, 검색에 바로 쓸 수 있는 "
    "영어 문장으로 다시 써라.\n"
    "- keywords: 검색 대상 주제를 나타내는 영어 기술 용어 1~5개 (예: speculative decoding, "
    "kv cache). 논문 제목이나 일반 단어(paper, method)는 넣지 마라."
)

ROUTE_DECLARATION = types.FunctionDeclaration(
    name="route_question",
    description="질문을 처리할 에이전트와 검색 범위를 정한다.",
    parameters={
        "type": "object",
        "properties": {
            "targets": {"type": "array", "items": {"type": "string", "enum": ["paper", "rag"]}},
            "question_type": {"type": "string", "enum": ["result", "method", "numeric", "general"]},
            "scope": {"type": "string", "enum": ["refs_first", "pool"]},
            "rewritten_query": {"type": "string", "description": "영어 검색 질의"},
            "keywords": {"type": "array", "items": {"type": "string"}, "description": "영어 키워드 1~5개"},
        },
        "required": ["targets", "question_type", "scope", "rewritten_query", "keywords"],
    },
)


def default_route(question: str) -> Route:
    """라우터가 함수 호출에 실패했을 때의 안전한 기본값 - 두 에이전트를 다 돌린다."""
    return Route(targets=["paper", "rag"], question_type="general", scope="refs_first",
                 rewritten_query=question, keywords=[])


def normalize_route(args: dict, question: str) -> Route:
    """LLM 출력값을 검증하고, 허용되지 않은 값은 기본값으로 바꾼다."""
    fallback = default_route(question)
    targets = [t for t in dict.fromkeys(args.get("targets") or []) if t in ("paper", "rag")]
    qtype = args.get("question_type")
    scope = args.get("scope")
    return Route(
        targets=targets or fallback["targets"],
        question_type=qtype if qtype in ("result", "method", "numeric", "general") else "general",
        scope=scope if scope in ("refs_first", "pool") else "refs_first",
        rewritten_query=(args.get("rewritten_query") or "").strip() or question,
        keywords=[str(k).strip() for k in (args.get("keywords") or []) if str(k).strip()][:5],
    )


def route_question(question: str, history: list[dict], paper_title: str) -> Route:
    prompt = (
        f"본 논문 제목: {paper_title}\n\n"
        f"이전 대화:\n{format_history(history)}\n\n"
        f"이번 질문: {question}"
    )
    name, args, _ = call_function(SYSTEM_PROMPT, prompt, [ROUTE_DECLARATION], max_output_tokens=1500)
    if name != "route_question":
        return default_route(question)
    return normalize_route(args, question)
