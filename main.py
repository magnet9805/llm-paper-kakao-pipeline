"""
MVP 파이프라인 진입점: 수집(HF Daily Papers) -> 요약 -> 발송을 순서대로 실행한다.

실행:
    uv run python main.py

설정값(하루에 몇 편 보낼지, 상위 몇 개 중에서 고를지)은 아래 상수를 직접 수정하면 된다.
나중에 FastAPI 단계에서는 이 값들이 API 파라미터로 바뀔 예정.
"""

from dotenv import load_dotenv

load_dotenv()

from collector import collect_papers, mark_as_seen  # noqa: E402
from kakao_sender import send_daily_papers  # noqa: E402
from summarizer import summarize_papers  # noqa: E402

TOP_N_CANDIDATES = 30  # HF Daily Papers에서 볼 상위 후보 개수
PAPERS_PER_DAY = 3  # 사용자가 정하는 하루 발송 개수


def run():
    print(f"1) HF Daily Papers 상위 {TOP_N_CANDIDATES}개 수집 중...")
    candidates = collect_papers(top_n=TOP_N_CANDIDATES)
    print(f"   -> 키워드 클러스터 매칭 통과: {len(candidates)}편")
    for p in candidates:
        print(f"      - [{','.join(p['matched_clusters'])}] {p['title']}")

    selected = candidates[:PAPERS_PER_DAY]
    print(f"2) 상위 {len(selected)}편 요약 중...")
    summarized = summarize_papers(selected)

    print("3) 카카오톡 발송 중...")
    send_daily_papers(summarized)

    mark_as_seen(selected)
    print("완료.")


if __name__ == "__main__":
    run()
