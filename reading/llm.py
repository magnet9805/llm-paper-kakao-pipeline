"""
라우터/통합 에이전트가 같이 쓰는 Gemini function calling 헬퍼.

keyword_chat.py/evaluator.py와 같은 모델 설정(GEMINI_MODEL, 기본 Flash-Lite)을 쓴다.
Gemma 대체 모델은 쓰지 않는다 - function calling 지원이 미검증이라 (CLAUDE.md "LLM 모델 선택").
"""

import os

from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
HISTORY_TURNS = 6  # 프롬프트에 넣을 최근 대화 메시지 수 (무상태 - 프론트가 매 턴 보내줌)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


def format_history(history: list[dict]) -> str:
    recent = [m for m in history if m.get("content")][-HISTORY_TURNS:]
    if not recent:
        return "(없음)"
    return "\n".join(f"{'사용자' if m['role'] == 'user' else 'AI'}: {m['content']}" for m in recent)


def call_function(
    system_prompt: str,
    prompt: str,
    declarations: list[types.FunctionDeclaration],
    allowed: list[str] | None = None,
    max_output_tokens: int = 3000,
) -> tuple[str | None, dict, str]:
    """
    함수 호출을 강제(mode=ANY)해서 구조화된 결과를 받는다.
    반환: (호출된 함수 이름 | None, 인자 dict, 함께 나온 텍스트)
    """
    response = _get_client().models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            tools=[types.Tool(function_declarations=declarations)],
            tool_config=types.ToolConfig(
                function_calling_config=types.FunctionCallingConfig(
                    mode="ANY", allowed_function_names=allowed or [d.name for d in declarations]
                )
            ),
            max_output_tokens=max_output_tokens,
        ),
    )
    text = ""
    candidate = response.candidates[0] if response.candidates else None
    for part in (candidate.content.parts if candidate and candidate.content else None) or []:
        if part.function_call:
            return part.function_call.name, dict(part.function_call.args or {}), text
        if part.text:
            text += part.text
    return None, {}, text
