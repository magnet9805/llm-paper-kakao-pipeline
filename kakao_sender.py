"""
카카오톡 "나에게 보내기" 발송. refresh_token으로 access_token을 자동 갱신한다.

최초 1회는 kakao_auth_helper.py로 수동 인증을 먼저 진행해야
kakao_token.json이 생성된다.
"""

import json
import os
from datetime import datetime, timedelta

import requests

from collector import CLUSTER_LABELS
from db import update_kakao_tokens

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


def refresh_access_token(refresh_token: str) -> dict:
    """카카오에 refresh_token으로 access_token 재발급을 요청하고, 응답을 그대로 반환한다.

    개인용 스크립트(파일 기반)와 웹 서비스(DB 기반) 둘 다 이 함수만 공유하고,
    "갱신된 토큰을 어디에 저장할지"는 각자 알아서 처리한다 (아래 두 함수 참고).
    """
    data = {
        "grant_type": "refresh_token",
        "client_id": os.environ["KAKAO_REST_API_KEY"],
        "refresh_token": refresh_token,
    }
    client_secret = os.environ.get("KAKAO_CLIENT_SECRET")
    if client_secret:
        data["client_secret"] = client_secret

    res = requests.post(TOKEN_URL, data=data, timeout=10)
    res.raise_for_status()
    return res.json()


def _refresh_access_token() -> str:
    """개인용 스크립트(main.py)용. kakao_token.json 파일에서 읽고 다시 저장한다."""
    tokens = load_tokens()
    refreshed = refresh_access_token(tokens["refresh_token"])

    tokens["access_token"] = refreshed["access_token"]
    # 카카오는 만료가 얼마 안 남았을 때만 refresh_token을 새로 내려준다.
    if "refresh_token" in refreshed:
        tokens["refresh_token"] = refreshed["refresh_token"]
    save_tokens(tokens)

    return tokens["access_token"]


def refresh_user_access_token(user: dict) -> str:
    """
    웹 서비스(멀티유저)용. db.get_user()로 조회한 사용자 dict를 받아 DB에 저장된
    이 사용자의 refresh_token으로 access_token을 갱신하고, 갱신 결과를 다시 DB에
    반영한 뒤 access_token을 반환한다.
    """
    refreshed = refresh_access_token(user["kakao_refresh_token"])
    access_token = refreshed["access_token"]
    refresh_token = refreshed.get("refresh_token", user["kakao_refresh_token"])
    expires_at = datetime.utcnow() + timedelta(seconds=refreshed.get("expires_in", 0))

    update_kakao_tokens(user["id"], access_token, refresh_token, expires_at)
    return access_token


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


def send_papers(papers: list[dict], access_token: str) -> None:
    """주어진 access_token으로 요약된 논문 리스트를 카카오톡 "나에게 보내기"로 발송한다.
    개인용/웹 서비스 양쪽에서 공유하는 실제 발송 로직 - 토큰을 어떻게 구했는지는 모른다."""
    for p in papers:
        _send_message(access_token, _build_template(p))


def send_daily_papers(papers: list[dict]) -> None:
    """개인용 스크립트(main.py)용 진입점. kakao_token.json 기반으로 토큰을 갱신해 발송한다."""
    access_token = _refresh_access_token()
    send_papers(papers, access_token)
