"""
Google Gemini API(무료 티어)로 논문 초록을 한국어로 요약한다.

collect_papers()가 반환한 논문 dict 리스트를 받아 각 논문에 'summary' 필드를
추가해서 반환한다.
"""

import os

from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")

SYSTEM_PROMPT = (
    "너는 AI/ML 논문을 바쁜 실무자에게 소개하는 어시스턴트다. "
    "주어진 논문의 제목과 초록을 읽고, 한국어로 핵심 아이디어와 왜 흥미로운지를 "
    "2~3문장, 전체 150자 이내로 간결하게 요약해라. 150자를 넘기지 마라. "
    "카카오톡 메시지에 그대로 들어가는 텍스트이므로 마크다운, 이모지, 줄바꿈, "
    "서론(예: '이 논문은') 없이 핵심 문장만 바로 써라."
)


SUMMARY_SAFETY_CAP = 180  # Gemini가 길이 지시를 안 지켰을 때의 최후 안전장치


def _summarize_one(client: genai.Client, paper: dict) -> str:
    response = client.models.generate_content(
        model=MODEL,
        contents=f"제목: {paper['title']}\n\n초록: {paper['abstract']}",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=300,
            # 이 모델은 기본적으로 내부 reasoning(thinking) 토큰을 쓰는데, 단순 요약에는
            # 불필요하고 max_output_tokens 예산을 thinking이 다 잡아먹어 답변이 잘리므로 끈다.
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    summary = response.text.strip()
    if len(summary) > SUMMARY_SAFETY_CAP:
        summary = summary[: SUMMARY_SAFETY_CAP - 1].rstrip() + "…"
    return summary


def summarize_papers(papers: list[dict]) -> list[dict]:
    """각 논문에 한국어 요약을 'summary' 필드로 추가해서 반환한다."""
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return [{**p, "summary": _summarize_one(client, p)} for p in papers]
