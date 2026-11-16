"""
Google Gemini API(무료 티어)로 논문 초록을 한국어로 요약한다.

collect_papers()가 반환한 논문 dict 리스트를 받아 각 논문에 'summary' 필드를
추가해서 반환한다.

모델 구성 (CLAUDE.md "LLM 모델 선택" 섹션 참고):
- 기본: Gemini Flash-Lite (무료 티어 약 500건/일, 논문 1편당 수 초)
- 대체: 기본 모델이 429(일일 한도 초과)를 내면 Gemma 4 26B로 넘어간다. 같은 Gemini API의
  같은 API 키로 호출되고 무료 한도가 훨씬 크지만(약 14,400건/일), 1편당 수십 초로 느리고
  간헐적으로 500 에러가 나서 기본 모델로는 쓰지 않는다.
"""

import os

from google import genai
from google.genai import errors, types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL", "gemma-4-26b-a4b-it")


class SummaryQuotaExceededError(Exception):
    """기본 모델과 대체 모델 모두 무료 티어 일일 한도를 넘겨서 요약에 실패했을 때 발생시킨다."""

SYSTEM_PROMPT = (
    "너는 AI/ML 논문을 바쁜 실무자에게 소개하는 어시스턴트다. "
    "주어진 논문의 제목과 초록을 읽고, 한국어로 핵심 아이디어와 왜 흥미로운지를 "
    "2~3문장, 전체 150자 이내로 간결하게 요약해라. 150자를 넘기지 마라. "
    "카카오톡 메시지에 그대로 들어가는 텍스트이므로 마크다운, 이모지, 줄바꿈, "
    "서론(예: '이 논문은') 없이 핵심 문장만 바로 써라."
)


SUMMARY_SAFETY_CAP = 180  # 모델이 길이 지시를 안 지켰을 때의 최후 안전장치


def _generate(client: genai.Client, model: str, text: str) -> str:
    # thinking 토큰을 쓰는 모델은 요청마다 편차가 크고(실측 300~1600+) thinking_budget으로
    # 끄거나 제한하는 것도 거부되거나 무시되므로, thinking + 답변이 다 들어가도록 넉넉하게 잡는다.
    try:
        response = client.models.generate_content(
            model=model,
            contents=text,
            config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, max_output_tokens=3000),
        )
    except errors.ServerError:
        if model == MODEL:
            raise
        # Gemma는 system_instruction을 넣은 요청에서 간헐적으로 500을 내는 경우가 있어서
        # (비교 실험에서 확인), 대체 모델일 때만 지시문을 본문 앞에 붙여 한 번 더 시도한다.
        response = client.models.generate_content(
            model=model,
            contents=f"{SYSTEM_PROMPT}\n\n{text}",
            config=types.GenerateContentConfig(max_output_tokens=3000),
        )
    summary = (response.text or "").strip()
    if len(summary) > SUMMARY_SAFETY_CAP:
        summary = summary[: SUMMARY_SAFETY_CAP - 1].rstrip() + "…"
    return summary


def summarize_papers(papers: list[dict]) -> list[dict]:
    """각 논문에 한국어 요약을 'summary' 필드로 추가해서 반환한다."""
    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
        # 503(high demand) 같은 일시적인 서버 에러는 잠깐 뒤 재시도하면 대개 성공하므로
        # SDK 내장 재시도(지수 백오프)를 켠다. 429는 재시도 대상에서 뺀다 - 무료 티어 일일
        # 한도 초과라 재시도해봐야 소용없고, 아래에서 대체 모델로 넘어가야 함.
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(
                attempts=5,
                initial_delay=2.0,
                max_delay=30.0,
                http_status_codes=[500, 502, 503, 504],
            )
        ),
    )

    model = MODEL
    results = []
    for p in papers:
        text = f"제목: {p['title']}\n\n초록: {p['abstract']}"
        try:
            summary = _generate(client, model, text)
        except errors.ClientError as e:
            if e.code != 429 or model == FALLBACK_MODEL:
                if e.code == 429:
                    raise SummaryQuotaExceededError from e
                raise
            # 기본 모델 한도 소진 - 이번 실행의 남은 논문은 전부 대체 모델로 요약한다
            # (논문마다 기본 모델에 다시 429를 받으러 가지 않도록).
            model = FALLBACK_MODEL
            try:
                summary = _generate(client, model, text)
            except errors.ClientError as e2:
                if e2.code == 429:
                    raise SummaryQuotaExceededError from e2
                raise
        results.append({**p, "summary": summary})
    return results
