"""
Collector: Hugging Face Daily Papers에서 특정 날짜의 인기 논문 상위 N개를 가져오고,
관심 키워드 클러스터로 필터링한다.

HF Daily Papers API: https://huggingface.co/api/daily_papers?date=YYYY-MM-DD&limit=100
- 하루에 큐레이션되는 논문 자체가 이미 한 번 걸러진 것이라 arXiv 전체를 훑는 것보다 노이즈가 적다.
- upvotes 필드로 그 날의 "인기 상위" 논문을 뽑을 수 있다.

키워드 클러스터는 기본적으로 클러스터 간 OR, 클러스터 내부 OR로 매칭한다.
단, "time_series" 클러스터만 예외로 topic 키워드와 llm 키워드가 "둘 다" 있어야
통과시킨다 (순수 통계/전통 ML 시계열 논문이 섞이는 것을 방지).
"""

import json
import os
from datetime import date as date_cls
from datetime import timedelta

import requests

SEEN_PAPERS_FILE = "seen_papers.json"
HF_DAILY_PAPERS_URL = "https://huggingface.co/api/daily_papers"

# 관심 키워드 클러스터. 모두 소문자로 매칭한다.
KEYWORD_CLUSTERS = {
    "time_series": {
        "require_all_of": [
            ["time series", "time-series", "forecasting"],  # topic 그룹
            ["llm", "language model", "foundation model"],  # LLM 관련 그룹
        ]
    },
    "multi_agent": [
        "multi-agent",
        "multi agent",
        "agent2agent",
        "a2a",
        "agent orchestration",
        "agentic",
        "tool use",
        "tool calling",
    ],
    "rag": [
        "retrieval-augmented",
        "retrieval augmented",
        " rag ",
        "hybrid retrieval",
        "long-context retrieval",
    ],
    "inference_efficiency": [
        "inference optimization",
        "speculative decoding",
        "kv cache",
        "quantization",
        "test-time compute",
        "efficient inference",
        "vllm",
    ],
    "reasoning": [
        "chain-of-thought",
        "chain of thought",
        "reasoning",
        "test-time scaling",
        "self-consistency",
    ],
}

# 클러스터 키 -> 카카오톡 메시지 등에 표시할 한글 라벨
CLUSTER_LABELS = {
    "time_series": "시계열×LLM",
    "multi_agent": "멀티에이전트",
    "rag": "RAG",
    "inference_efficiency": "추론 효율",
    "reasoning": "추론기법",
}


def _load_seen_ids() -> set:
    if not os.path.exists(SEEN_PAPERS_FILE):
        return set()
    with open(SEEN_PAPERS_FILE, "r") as f:
        return set(json.load(f))


def _save_seen_ids(seen_ids: set) -> None:
    with open(SEEN_PAPERS_FILE, "w") as f:
        json.dump(list(seen_ids), f)


def fetch_top_daily_papers(target_date: str = None, top_n: int = 30) -> list[dict]:
    """
    HF Daily Papers에서 특정 날짜의 논문을 가져와 upvotes 기준 상위 top_n개를 반환한다.

    Args:
        target_date: "YYYY-MM-DD" 형식. None이면 어제 날짜 사용
            (오늘 날짜는 아직 논문이 덜 쌓여있을 수 있어 어제 기준이 안전).
        top_n: 상위 몇 개를 뽑을지.

    Returns:
        {hf_id, title, abstract, upvotes, url} 형태의 논문 리스트 (upvotes 내림차순).
    """
    if target_date is None:
        target_date = (date_cls.today() - timedelta(days=1)).isoformat()

    res = requests.get(
        HF_DAILY_PAPERS_URL,
        params={"date": target_date, "limit": 100},
        timeout=15,
    )
    res.raise_for_status()
    items = res.json()

    papers = []
    for item in items:
        paper = item.get("paper", {})
        papers.append(
            {
                "hf_id": paper.get("id"),
                "title": paper.get("title", item.get("title", "")),
                "abstract": paper.get("summary", item.get("summary", "")),
                "upvotes": paper.get("upvotes", 0),
                "url": f"https://huggingface.co/papers/{paper.get('id')}",
            }
        )

    papers.sort(key=lambda p: p["upvotes"], reverse=True)
    return papers[:top_n]


def _matches_cluster(text: str, cluster_def) -> bool:
    """단일 클러스터 정의(리스트 또는 require_all_of dict)에 대해 매칭 여부 판단."""
    if isinstance(cluster_def, dict) and "require_all_of" in cluster_def:
        # 모든 하위 그룹에서 각각 하나 이상 매칭되어야 통과 (AND 조건)
        return all(
            any(kw in text for kw in group) for group in cluster_def["require_all_of"]
        )
    return any(kw in text for kw in cluster_def)


def filter_by_keywords(papers: list[dict], clusters: dict = None) -> list[dict]:
    """
    논문 리스트를 관심 키워드 클러스터로 필터링한다.
    통과한 논문에는 어떤 클러스터에 매칭됐는지 'matched_clusters' 필드를 추가한다
    (여러 클러스터에 걸릴수록 이후 랭킹에서 우선순위를 줄 수 있음).
    """
    clusters = clusters or KEYWORD_CLUSTERS
    seen_ids = _load_seen_ids()
    matched = []

    for paper in papers:
        if paper["hf_id"] in seen_ids:
            continue

        text = f"{paper['title']} {paper['abstract']}".lower()
        matched_clusters = [
            name for name, cluster_def in clusters.items() if _matches_cluster(text, cluster_def)
        ]
        if matched_clusters:
            matched.append({**paper, "matched_clusters": matched_clusters})

    # 여러 클러스터에 걸린 논문을 우선, 그 다음 upvotes 순
    matched.sort(key=lambda p: (len(p["matched_clusters"]), p["upvotes"]), reverse=True)
    return matched


def collect_papers(target_date: str = None, top_n: int = 30) -> list[dict]:
    """수집 + 필터링을 한 번에 수행하는 진입점."""
    top_papers = fetch_top_daily_papers(target_date=target_date, top_n=top_n)
    return filter_by_keywords(top_papers)


def mark_as_seen(papers: list[dict]) -> None:
    """발송 완료된 논문의 hf_id를 기록해서 다음 실행 시 중복되지 않게 한다."""
    seen_ids = _load_seen_ids()
    seen_ids.update(p["hf_id"] for p in papers)
    _save_seen_ids(seen_ids)
