"""
통합 에이전트 - 받은 근거만으로 답하고, "본 논문 내용 / 다른 논문 근거 / 일반 설명"을 나눠서 답한다.

function calling 도구 2개:
- answer(...)                 : 근거가 충분하면 바로 답변
- need_more_evidence(missing) : 무엇이 부족한지 적고 공용 풀 추가 검색을 요청

final=True(추가 검색 후 마지막 호출)이면 answer만 허용한다 - 질문당 LLM 호출 최대 3회 보장.
"""

from typing import Literal, NotRequired, TypedDict

from google.genai import types

from reading.llm import call_function, format_history
from reading.schemas import Evidence


class Decision(TypedDict):
    action: Literal["answer", "need_more_evidence"]
    missing: NotRequired[str]
    from_paper: NotRequired[str]
    from_other_papers: NotRequired[str]
    general: NotRequired[str]
    cited_ids: NotRequired[list[str]]
    found: NotRequired[bool]


SYSTEM_PROMPT = (
    "너는 사용자가 논문을 읽는 것을 돕는 AI다. 아래에 주어진 '근거 자료'만 사용해서 한국어로 답해라.\n\n"
    "규칙:\n"
    "- 근거 자료에 없는 논문 제목, 저자, 수치, 실험 결과를 절대 지어내지 마라.\n"
    "- 답변은 세 칸으로 나눠 채운다. from_paper: 본 논문 근거(B, P*)로 말할 수 있는 내용. "
    "from_other_papers: 다른 논문 근거(R*)로 말할 수 있는 내용 - 어느 논문인지 제목을 밝혀라. "
    "general: 근거 자료에 없지만 질문 이해에 필요한 일반 설명 (출처 없는 설명으로 표시된다). "
    "해당 내용이 없는 칸은 빈 문자열로 둬라.\n"
    "- 문장 끝에 사용한 근거 id를 [P2], [R1]처럼 붙이고, 사용한 id를 cited_ids에 모두 넣어라.\n"
    "- R* 근거 중 '본 논문이 인용한 레퍼런스'로 표시된 것은 본 논문의 선행연구다.\n"
    "- 근거 자료가 질문에 답하기에 부족하고, 다른 논문을 더 찾아보면 답할 수 있을 것 같으면 "
    "need_more_evidence를 호출해서 무엇이 부족한지 영어 검색 질의 형태로 적어라.\n"
    "- 더 찾을 수 없는 상황이거나 근거가 충분하면 answer를 호출해라. 근거에서 답을 찾지 못했다면 "
    "found=false로 두고, 찾지 못했다는 사실을 솔직하게 말해라.\n"
    "- 일반 텍스트로 답하지 말고 반드시 함수 하나를 호출해라."
)

ANSWER_DECLARATION = types.FunctionDeclaration(
    name="answer",
    description="근거 자료를 바탕으로 최종 답변을 한다.",
    parameters={
        "type": "object",
        "properties": {
            "from_paper": {"type": "string", "description": "본 논문 근거로 한 설명 (없으면 빈 문자열)"},
            "from_other_papers": {"type": "string", "description": "다른 논문 근거로 한 설명 (없으면 빈 문자열)"},
            "general": {"type": "string", "description": "출처 없는 일반 설명 (없으면 빈 문자열)"},
            "cited_ids": {"type": "array", "items": {"type": "string"}, "description": "사용한 근거 id"},
            "found": {"type": "boolean", "description": "근거 자료에서 질문의 답을 찾았는가"},
        },
        "required": ["from_paper", "from_other_papers", "general", "cited_ids", "found"],
    },
)

NEED_MORE_DECLARATION = types.FunctionDeclaration(
    name="need_more_evidence",
    description="근거가 부족할 때, 무엇이 부족한지 적고 다른 논문 추가 검색을 요청한다.",
    parameters={
        "type": "object",
        "properties": {"missing": {"type": "string", "description": "부족한 정보 - 영어 검색 질의 형태"}},
        "required": ["missing"],
    },
)


def format_evidence(evidence: list[Evidence]) -> str:
    if not evidence:
        return "(근거 자료 없음)"
    blocks = []
    for ev in evidence:
        if ev["kind"] == "other_paper":
            origin = "본 논문이 인용한 레퍼런스" if ev.get("via") == "references" else "공용 논문 풀"
            year = (ev.get("published") or "")[:4]
            head = f"[{ev['evidence_id']}] 다른 논문 ({origin}) - {ev['title']}" + (f" ({year})" if year else "")
            body = f"초록: {ev['text']}"
            if ev.get("detail_chunks"):
                body += "\n전문 발췌:\n" + "\n".join(ev["detail_chunks"])
        else:
            head = f"[{ev['evidence_id']}] 본 논문 - {ev.get('section', '')}"
            body = ev["text"]
        blocks.append(f"{head}\n{body}")
    return "\n\n".join(blocks)


def parse_decision(name: str | None, args: dict, text: str) -> Decision:
    if name == "need_more_evidence":
        return Decision(action="need_more_evidence", missing=str(args.get("missing", "")).strip())
    if name == "answer":
        return Decision(
            action="answer",
            from_paper=str(args.get("from_paper", "")).strip(),
            from_other_papers=str(args.get("from_other_papers", "")).strip(),
            general=str(args.get("general", "")).strip(),
            cited_ids=[str(i) for i in (args.get("cited_ids") or [])],
            found=bool(args.get("found", False)),
        )
    # 함수 호출 없이 텍스트만 온 경우 - 출처를 확인할 수 없으니 일반 설명으로만 취급한다.
    return Decision(action="answer", from_paper="", from_other_papers="", general=text.strip(),
                    cited_ids=[], found=False)


def integrate(
    question: str, history: list[dict], paper_title: str, evidence: list[Evidence], final: bool
) -> Decision:
    prompt = (
        f"본 논문 제목: {paper_title}\n\n"
        f"이전 대화:\n{format_history(history)}\n\n"
        f"근거 자료:\n{format_evidence(evidence)}\n\n"
        f"이번 질문: {question}"
    )
    if final:
        prompt += "\n\n(추가 검색까지 마친 상태다. 더 찾을 수 없으니 answer를 호출해라.)"
    allowed = ["answer"] if final else ["answer", "need_more_evidence"]
    name, args, text = call_function(
        SYSTEM_PROMPT, prompt, [ANSWER_DECLARATION, NEED_MORE_DECLARATION], allowed=allowed
    )
    return parse_decision(name, args, text)
