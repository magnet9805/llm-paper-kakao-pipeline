"""
Gemini function calling으로 사용자와 대화하며 관심 키워드 그룹을 제안한다.
(로드맵 2-4, CLAUDE.md의 "LLM 대화형 키워드 추출 - 확정된 스펙" 참고)

server.py의 POST /api/keyword-chat는 무상태로 동작한다 - 대화 기록은 서버에
저장하지 않고, 프론트엔드가 매 턴 전체 history를 다시 보내준다.
"""

import os

from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

SYSTEM_PROMPT = (
    "너는 AI/ML 논문에 관심있는 사용자가 자신의 관심 키워드를 구체화하도록 "
    "도와주는 어시스턴트다. 사용자와 자연스럽게 대화하면서 관심 주제를 물어봐라.\n\n"
    "규칙:\n"
    "- 대화 초반(최소 1~2턴)에는 섣불리 키워드를 제안하지 말고, 관심 분야를 "
    "구체화하는 질문을 먼저 해라 (예: 어떤 세부 분야인지, 왜 관심있는지 등).\n"
    "- 사용자의 관심사가 충분히 구체적으로 파악됐다고 판단될 때만 "
    "propose_keyword_group 함수를 호출해서 제목과 키워드 5~8개를 제안해라.\n"
    "- keywords는 반드시 영어로 작성해라 - 논문 원문(제목/초록)이 영어라서 "
    "키워드가 실제로 매칭되려면 영어 표현이어야 한다.\n"
    "- propose_keyword_group을 호출할 때는 별도의 안내 문구를 텍스트로 덧붙이지"
    "말고 함수 호출만 해라 (안내 문구는 프론트엔드가 고정 문구로 붙인다).\n"
    "- 응답은 간결하게, 한국어로 해라."
)

PROPOSE_KEYWORD_GROUP_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="propose_keyword_group",
            description=(
                "사용자와의 대화에서 관심 주제가 충분히 파악됐을 때, 구조화된 키워드 "
                "그룹을 제안한다. 아직 충분히 파악되지 않았다면 이 함수를 호출하지 "
                "말고 계속 대화로 질문할 것."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "이 키워드 그룹의 대표 제목"},
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "논문 필터링에 쓸 구체적 영어 키워드 5~8개",
                    },
                },
                "required": ["title", "keywords"],
            },
        )
    ]
)


def chat_turn(history: list[dict]) -> dict:
    """
    history: [{"role": "user"|"assistant", "content": str}, ...] (마지막 항목이
    이번 턴의 새 사용자 메시지). Gemini는 "assistant" 대신 "model"이라는 역할
    이름을 쓰므로 여기서 변환한다.

    반환값: {"reply": str, "proposal": {"title": str, "keywords": [str]} | None}
    """
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    contents = [
        types.Content(
            role="model" if m["role"] == "assistant" else "user",
            parts=[types.Part(text=m["content"])],
        )
        for m in history
        if m["content"]  # 텍스트 없이 제안만 했던 과거 턴은 건너뛴다.
    ]

    response = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=[PROPOSE_KEYWORD_GROUP_TOOL],
            max_output_tokens=1500,
        ),
    )

    reply_text = ""
    proposal = None
    for part in response.candidates[0].content.parts or []:
        if part.text:
            reply_text += part.text
        if part.function_call and part.function_call.name == "propose_keyword_group":
            args = dict(part.function_call.args)
            proposal = {
                "title": args.get("title", ""),
                "keywords": list(args.get("keywords", [])),
            }

    return {"reply": reply_text.strip(), "proposal": proposal}
