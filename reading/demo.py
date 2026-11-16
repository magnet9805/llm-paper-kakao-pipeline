"""
실제 Gemini + 테스트용 저장소(FakeReadingStore)로 "AI와 함께 읽기"를 한 번 돌려보는 스크립트.
질문 1개당 Gemini 호출 2~3회 (라우터 + 통합 [+ 추가 검색 후 통합]).

    uv run python -m reading.demo                               # 기본 질문들
    uv run python -m reading.demo "HumanEval에서 몇 배 빨라졌어?"  # 질문 직접 지정
"""

import json
import sys

from dotenv import load_dotenv

load_dotenv()

from reading.graph import ask  # noqa: E402 - .env를 먼저 읽어야 GEMINI_MODEL이 반영된다

PAPER_ID = "test.00001"
DEFAULT_QUESTIONS = [
    "HumanEval에서 고정 길이 대비 얼마나 빨라졌어?",  # 본 논문 수치 질문 -> paper, numeric
    "이 논문의 speculative decoding은 원래 어느 논문에서 나온 방법이야?",  # 선행연구 -> refs_first
    "draft 모델 없이 speculative decoding을 하는 다른 연구도 있어?",  # 레퍼런스 밖 -> pool
]


def main():
    questions = sys.argv[1:] or DEFAULT_QUESTIONS
    for q in questions:
        print("=" * 80)
        print(f"Q: {q}")
        result = ask(PAPER_ID, q)
        print(f"route: {json.dumps(result['route'], ensure_ascii=False)}")
        print(f"searches: {result['searches']}")
        print(f"LLM 호출: {result['llm_calls']}회, found={result['found']}")
        print(f"citations: {[(c['evidence_id'], c['title'][:50]) for c in result['citations']]}")
        print("-" * 80)
        print(result["answer"])


if __name__ == "__main__":
    main()
