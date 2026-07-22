"""
카카오톡 "나에게 보내기" 발송. refresh_token으로 access_token을 자동 갱신한다.

최초 1회는 kakao_auth_helper.py로 수동 인증을 먼저 진행해야
kakao_token.json이 생성된다.
"""

import json
import os

import requests

from collector import CLUSTER_LABELS

KAKAO_TOKEN_FILE = "kakao_token.json"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


def load_tokens() -> dict:
    if not os.path.exists(KAKAO_TOKEN_FILE):
        raise FileNotFoundError(
            f"{KAKAO_TOKEN_FILE}가 없습니다. 먼저 `uv run python kakao_auth_helper.py`로 "
            "최초 인증을 진행하세요."
        )
    with open(KAKAO_TOKEN_FILE, "r") as f:
        return json.load(f)


def save_tokens(tokens: dict) -> None:
    with open(KAKAO_TOKEN_FILE, "w") as f:
        json.dump(tokens, f)


def _refresh_access_token() -> str:
    tokens = load_tokens()
    data = {
        "grant_type": "refresh_token",
        "client_id": os.environ["KAKAO_REST_API_KEY"],
        "refresh_token": tokens["refresh_token"],
    }
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET")
    if client_secret:
        data["client_secret"] = client_secret

    res = requests.post(TOKEN_URL, data=data, timeout=10)
    res.raise_for_status()
    refreshed = res.json()

    tokens["access_token"] = refreshed["access_token"]
    # 카카오는 만료가 얼마 안 남았을 때만 refresh_token을 새로 내려준다.
    if "refresh_token" in refreshed:
        tokens["refresh_token"] = refreshed["refresh_token"]
    save_tokens(tokens)

    return tokens["access_token"]


MAX_TEXT_LENGTH = 200  # 카카오 text 템플릿의 text 필드 최대 길이


def _build_text(paper: dict) -> str:
    """
    feed 템플릿의 description은 1줄로 고정 표시돼서 요약을 담기엔 너무 좁다.
    text 템플릿은 200자를 여러 줄로 자연스럽게 감싸 보여주므로 이쪽을 쓴다.
    요약은 최대한 자르지 않고, 공간이 부족하면 제목부터 양보한다.
    """
    labels = [CLUSTER_LABELS.get(c, c) for c in paper.get("matched_clusters", [])]
    header = f"HF Daily Papers - {', '.join(labels)}" if labels else "HF Daily Papers"
    summary = paper["summary"]

    with_title = f"[{header}] {paper['title']}\n\n{summary}"
    if len(with_title) <= MAX_TEXT_LENGTH:
        return with_title

    without_title = f"[{header}]\n\n{summary}"
    if len(without_title) <= MAX_TEXT_LENGTH:
        return without_title

    # summarizer가 원하는 길이를 못 지켰을 때의 최후 안전장치.
    head = f"[{header}]"
    budget = MAX_TEXT_LENGTH - len(head) - 2
    truncated = summary[: budget - 1].rstrip() + "…"
    return f"{head}\n\n{truncated}"


def _build_template(paper: dict) -> dict:
    """
    text 템플릿 + buttons 사용. 버튼이 보이려면 link의 도메인(huggingface.co)이
    카카오 개발자 콘솔의 [앱 설정 > 플랫폼 > Web]에 등록되어 있어야 한다.
    """
    link = {"web_url": paper["url"], "mobile_web_url": paper["url"]}
    return {
        "object_type": "text",
        "text": _build_text(paper),
        "link": link,
        "buttons": [{"title": "해당 논문 보기", "link": link}],
    }


def _send_message(access_token: str, template_object: dict) -> None:
    res = requests.post(
        SEND_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        data={"template_object": json.dumps(template_object)},
        timeout=10,
    )
    res.raise_for_status()


def send_daily_papers(papers: list[dict]) -> None:
    """요약된 논문 리스트를 카카오톡 "나에게 보내기"로 한 편씩 발송한다."""
    access_token = _refresh_access_token()

    for p in papers:
        _send_message(access_token, _build_template(p))
