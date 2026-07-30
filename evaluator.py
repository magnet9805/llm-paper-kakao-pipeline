"""
Summarizer(summarizer.py)가 생성한 요약의 품질을, Gemini 자신을 심사자로 써서
평가하는 하네스 (로드맵 6번).

원래는 공식 ragas 패키지를 쓰려고 했으나 포기했다 - ragas==0.4.3/0.3.9 둘 다
내부에서 langchain_community.chat_models.vertexai를 무조건 import하는데, 이
모듈이 최신 langchain-community(sunset되면서 개별 통합 패키지로 이전됨)에는
더 이상 없다(ragas 쪽의 버전 미고정 버그). 이걸 우회하려고 langchain-community를
구버전으로 고정해봤지만, langgraph(로드맵 5번)가 요구하는 langchain-core>=1.4.7과
langchain-community 구버전이 요구하는 langchain-core<1.0.0이 정면으로 충돌해서
같은 환경에 공존이 애초에 불가능했다(uv 리졸버가 명확히 실패 응답).

게다가 이 파이프라인은 "검색 -> 답변"이 아니라 "수집(정렬) -> 필터(규칙 기반
키워드 매칭) -> 요약"이라, RAGAS의 핵심 지표(Context Precision/Recall 등)가
애초에 잘 들어맞지도 않았다 - 평가가 실제로 의미 있는 단계는 Summarizer
하나뿐이다 (Collector/Filter는 결정론적 로직이라 "품질"을 평가할 대상이 아님).
그래서 ragas 패키지 없이, Summarizer 출력만 직접 LLM-as-judge로 평가한다.

실행:
    uv run python evaluator.py    # 파이프라인을 조금만 돌려서(기본 3편) 채점
"""

import os

from google import genai
from google.genai import types

MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
SUMMARY_LENGTH_LIMIT = 150  # summarizer.py의 SYSTEM_PROMPT가 지시하는 길이 제약과 동일

JUDGE_SYSTEM_PROMPT = (
    "너는 논문 요약의 품질을 채점하는 엄격한 평가자다. 주어진 논문의 제목/초록과, "
    "그걸 바탕으로 생성된 한국어 요약을 보고 score_summary 함수를 반드시 호출해서 "
    "채점 결과를 반환해라. 절대로 일반 텍스트로 답하지 말고 함수 호출만 해라."
)

SCORE_SUMMARY_TOOL = types.Tool(
    function_declarations=[
        types.FunctionDeclaration(
            name="score_summary",
            description="논문 요약 하나를 채점한다.",
            parameters={
                "type": "object",
                "properties": {
                    "faithful": {
                        "type": "boolean",
                        "description": "요약이 초록에 없는 내용을 지어내지 않고 사실에 기반했는가 (초록에 없는 수치/방법론/결과를 언급하면 False)",
                    },
                    "relevant": {
                        "type": "boolean",
                        "description": "요약이 논문의 핵심 아이디어/기여를 담고 있는가",
                    },
                    "reasoning": {
                        "type": "string",
                        "description": "판단 근거를 한국어 한 문장으로",
                    },
                },
                "required": ["faithful", "relevant", "reasoning"],
            },
        )
    ]
)


def judge_summary(client: genai.Client, paper: dict) -> dict:
    """
    논문 하나의 요약을 채점한다. faithful/relevant는 Gemini의 판단이고, concise는
    LLM한테 물어볼 필요 없이 길이만 재면 되는 결정론적 체크라 여기서 바로 계산한다.
    """
    prompt = f"제목: {paper['title']}\n\n초록: {paper['abstract']}\n\n생성된 요약: {paper['summary']}"
    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=JUDGE_SYSTEM_PROMPT,
            tools=[SCORE_SUMMARY_TOOL],
            max_output_tokens=1500,
        ),
    )

    judgment = {"faithful": None, "relevant": None, "reasoning": "함수 호출 없음 - 모델이 채점을 거부함"}
    for part in response.candidates[0].content.parts or []:
        if part.function_call and part.function_call.name == "score_summary":
            args = dict(part.function_call.args)
            judgment = {
                "faithful": args.get("faithful"),
                "relevant": args.get("relevant"),
                "reasoning": args.get("reasoning", ""),
            }
            break

    judgment["concise"] = len(paper["summary"]) <= SUMMARY_LENGTH_LIMIT
    return judgment


def evaluate_summaries(papers: list[dict]) -> list[dict]:
    """각 논문 dict에 'judgment' 필드를 덧붙여 반환한다."""
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return [{**paper, "judgment": judge_summary(client, paper)} for paper in papers]


def summarize_evaluation(results: list[dict]) -> dict:
    """개별 채점 결과를 종합 비율로 요약한다."""
    total = len(results)
    if total == 0:
        return {"total": 0, "faithful_rate": 0.0, "relevant_rate": 0.0, "concise_rate": 0.0}

    faithful = sum(1 for r in results if r["judgment"]["faithful"])
    relevant = sum(1 for r in results if r["judgment"]["relevant"])
    concise = sum(1 for r in results if r["judgment"]["concise"])

    return {
        "total": total,
        "faithful_rate": faithful / total,
        "relevant_rate": relevant / total,
        "concise_rate": concise / total,
    }


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()

    from pipeline_graph import run_pipeline

    SAMPLE_SIZE = 3  # Gemini 무료 티어 할당량(20건/일)을 아끼기 위해 소수만 스팟체크

    print(f"파이프라인을 실행해서 {SAMPLE_SIZE}편을 요약한 뒤 채점합니다...")
    result = run_pipeline(top_n=30, papers_per_send=SAMPLE_SIZE)
    summarized = result["summarized_papers"]

    if not summarized:
        print("요약된 논문이 없습니다 (필터 통과 논문이 없어요).")
    else:
        evaluated = evaluate_summaries(summarized)
        for r in evaluated:
            j = r["judgment"]
            mark = lambda b: "O" if b else "X"
            print(f"\n- {r['title'][:70]}")
            print(
                f"  faithful={mark(j['faithful'])} relevant={mark(j['relevant'])} "
                f"concise={mark(j['concise'])} ({len(r['summary'])}자)"
            )
            print(f"  근거: {j['reasoning']}")

        stats = summarize_evaluation(evaluated)
        print("\n=== 종합 ===")
        print(
            f"총 {stats['total']}편 중 faithful {stats['faithful_rate']:.0%}, "
            f"relevant {stats['relevant_rate']:.0%}, concise {stats['concise_rate']:.0%}"
        )
