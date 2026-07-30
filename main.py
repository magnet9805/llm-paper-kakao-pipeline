"""
MVP 파이프라인 진입점: 수집(HF Daily Papers) -> 요약 -> 발송을 순서대로 실행한다.
실제 수집/필터/요약 3단계는 pipeline_graph.py의 LangGraph 그래프가 담당한다
(로드맵 5번).

실행:
    uv run python main.py

설정값(하루에 몇 편 보낼지, 상위 몇 개 중에서 고를지)은 아래 상수를 직접 수정하면 된다.
나중에 FastAPI 단계에서는 이 값들이 API 파라미터로 바뀔 예정.
"""

from dotenv import load_dotenv

load_dotenv()

from collector import mark_as_seen  # noqa: E402
from kakao_sender import send_daily_papers  # noqa: E402
from pipeline_graph import run_pipeline  # noqa: E402
from summarizer import SummaryQuotaExceededError  # noqa: E402

TOP_N_CANDIDATES = 30  # HF Daily Papers에서 볼 상위 후보 개수
PAPERS_PER_DAY = 3  # 사용자가 정하는 하루 발송 개수


def run():
    print(f"1) HF Daily Papers 상위 {TOP_N_CANDIDATES}개 수집 및 필터링 중...")
    try:
        result = run_pipeline(top_n=TOP_N_CANDIDATES, papers_per_send=PAPERS_PER_DAY)
    except SummaryQuotaExceededError:
        print("Gemini 무료 티어의 하루 요청 한도(20건)를 다 썼습니다. 내일 다시 실행해주세요.")
        return
    candidates = result["filtered_papers"]
    print(f"   -> 키워드 클러스터 매칭 통과: {len(candidates)}편")
    for p in candidates:
        print(f"      - [{','.join(p['matched_clusters'])}] {p['title']}")

    summarized = result["summarized_papers"]
    print(f"2) 상위 {len(summarized)}편 요약 완료")

    print("3) 카카오톡 발송 중...")
    send_daily_papers(summarized)

    mark_as_seen(summarized)
    print("완료.")


if __name__ == "__main__":
    run()
