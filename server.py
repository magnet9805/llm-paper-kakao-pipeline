"""
FastAPI 웹 서비스 진입점. 카카오 소셜 로그인(Authlib)으로 회원가입/로그인을 통합한다.

실행:
    uv run uvicorn server:app --reload

카카오 개발자 콘솔에 Redirect URI로 http://localhost:8000/auth/kakao/callback 를
등록해둬야 한다. talk_message(카카오톡 메시지 전송) 동의도 로그인 시점에 함께 받는다.
"""

import json
import os
from datetime import datetime, timedelta

from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

from db import (
    add_keyword,
    create_keyword_group,
    delete_keyword,
    delete_keyword_group,
    get_user,
    init_db,
    list_keyword_groups,
    update_keyword_group_title,
    upsert_user,
)

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# SessionMiddleware: 로그인 상태를 서버가 따로 저장하지 않고, 서명된(signed) 쿠키에
# 담아 브라우저에 보관한다. secret_key로 서명하기 때문에 사용자가 쿠키 값을 조작해도
# (예: user_id를 다른 숫자로 바꿔치기) 서명 검증에서 걸러진다.
app.add_middleware(SessionMiddleware, secret_key=os.environ["SESSION_SECRET_KEY"])

# OAuth 클라이언트 하나를 앱 전역에서 재사용한다. "카카오"라는 이름의 OAuth 공급자를
# 등록해두면, 아래에서 oauth.kakao.xxx() 형태로 카카오의 인가/토큰/사용자정보 API를
# Authlib가 대신 호출해준다 (요청 서명, state 검증 등을 직접 구현할 필요 없음).
oauth = OAuth()
oauth.register(
    name="kakao",
    client_id=os.environ["KAKAO_REST_API_KEY"],
    client_secret=os.environ.get("KAKAO_CLIENT_SECRET"),
    access_token_url="https://kauth.kakao.com/oauth/token",
    authorize_url="https://kauth.kakao.com/oauth/authorize",
    api_base_url="https://kapi.kakao.com/",
    # 카카오 토큰 엔드포인트는 client_id/secret을 HTTP Basic 헤더가 아니라
    # 폼 body 파라미터로 받는다. 기본값(client_secret_basic)이면 "Not exist
    # client_id [null]" 에러가 난다.
    token_endpoint_auth_method="client_secret_post",
    client_kwargs={"scope": "talk_message profile_nickname profile_image"},
)


@app.on_event("startup")
def on_startup():
    init_db()


def require_login(request: Request) -> int:
    """
    "로그인 안 했으면 여기서 바로 막고, 했으면 user_id를 꺼내준다"는 검문소 역할.
    FastAPI의 Depends(require_login)로 각 엔드포인트 함수의 매개변수에 꽂아 넣으면,
    그 엔드포인트 본문이 실행되기 *전에* 이 함수가 먼저 실행된다. 즉 로그인 여부를
    엔드포인트마다 매번 손으로 체크하지 않아도 된다.
    """
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")
    return user_id


def get_current_user(request: Request) -> dict | None:
    """require_login과 달리 로그인 안 했다고 막지 않고 None을 돌려준다.
    화면(홈)은 로그인 여부에 따라 다르게 보여줘야 할 뿐, 막을 필요는 없어서 따로 둔다."""
    user_id = request.session.get("user_id")
    return get_user(user_id) if user_id is not None else None


@app.get("/")
async def index(request: Request):
    """홈 화면. 로그인 전엔 로그인 버튼, 로그인 후엔 인사말 + 마이페이지 링크를 보여준다."""
    return templates.TemplateResponse(
        request, "index.html", {"user": get_current_user(request)}
    )


@app.get("/mypage")
async def mypage(request: Request):
    """
    마이페이지 화면. API(require_login)와 다르게, 로그인 안 한 사람이 오면 401을
    던지는 대신 로그인 화면으로 보내버린다 - 사람이 보는 화면이라 JSON 에러보다는
    리다이렉트가 자연스럽다.
    """
    user = get_current_user(request)
    if user is None:
        return RedirectResponse(url="/auth/kakao/login")

    groups = list_keyword_groups(user["id"])
    return templates.TemplateResponse(
        request,
        "mypage.html",
        {
            "user": user,
            "groups": groups,
            # 수정 팝업을 열 때마다 서버에 다시 물어보지 않고 이미 받은 데이터로
            # 바로 채워 넣을 수 있도록, 같은 목록을 JS에서 쓸 JSON 문자열로도 넘긴다.
            "groups_json": json.dumps(groups, ensure_ascii=False, default=str),
        },
    )


@app.get("/auth/kakao/login")
async def kakao_login(request: Request):
    """
    사용자가 "카카오로 로그인" 버튼을 누르면 여기로 온다.
    할 일은 딱 하나: 카카오 로그인 페이지로 리다이렉트시키는 것.

    request.url_for("kakao_callback")은 "kakao_callback이라는 이름표가 붙은 라우트의
    전체 URL을 계산해줘"라는 뜻이다. 바로 아래 kakao_callback 함수가 그 이름표를
    달고 "/auth/kakao/callback" 경로에 등록되어 있으므로, 결과는
    "http://localhost:8000/auth/kakao/callback"이 된다.

    이 URL을 카카오에 redirect_uri로 넘기면, 카카오는 로그인/동의가 끝난 뒤 이
    주소로 사용자를 돌려보낸다 - 단, 이 주소가 카카오 개발자 콘솔에 등록해둔
    Redirect URI 목록과 정확히 일치해야만 통과시켜준다 (안 맞으면 KOE006 에러).
    실제로 일치해야 하는 건 @app.get("/auth/kakao/callback")의 경로 문자열이지,
    함수 이름("kakao_callback")은 코드 안에서 그 경로를 다시 찾기 위한 별명일 뿐이다.
    """
    redirect_uri = request.url_for("kakao_callback")
    return await oauth.kakao.authorize_redirect(request, redirect_uri)


@app.get("/auth/kakao/callback")
async def kakao_callback(request: Request):
    """
    카카오 로그인/동의가 끝나면 카카오가 사용자를 여기로 돌려보낸다 (쿼리 파라미터에
    임시 인가 코드가 담겨서 옴). 여기서 하는 일 4단계:

    1. 그 인가 코드를 실제 access_token/refresh_token으로 교환 (카카오 서버와 통신)
    2. 그 토큰으로 카카오에 "이 사람이 누구야?" 라고 물어봄 (닉네임, 프로필 사진 등)
    3. DB에 이 사용자를 저장/갱신 (upsert) - 처음 로그인이면 새로 생성, 재로그인이면 갱신
    4. 세션 쿠키에 user_id만 저장하고 홈 화면으로 보냄 (토큰 자체는 쿠키에 안 담고 DB에만 둠)
    """
    token = await oauth.kakao.authorize_access_token(request)

    profile_res = await oauth.kakao.get("v2/user/me", token=token)
    profile = profile_res.json()
    account = profile.get("kakao_account", {})
    kakao_profile = account.get("profile", {})

    expires_at = datetime.utcnow() + timedelta(seconds=token.get("expires_in", 0))

    user_id = upsert_user(
        kakao_id=str(profile["id"]),
        nickname=kakao_profile.get("nickname"),
        profile_image_url=kakao_profile.get("profile_image_url"),
        access_token=token["access_token"],
        refresh_token=token["refresh_token"],
        expires_at=expires_at,
    )

    request.session["user_id"] = user_id
    return RedirectResponse(url="/")


@app.post("/auth/logout")
async def logout(request: Request):
    """세션 쿠키만 비운다. 카카오 쪽 토큰이나 DB는 그대로 둔다 (재로그인 시 그대로 재사용)."""
    request.session.clear()
    return {"ok": True}


@app.get("/auth/me")
async def me(user_id: int = Depends(require_login)):
    """"지금 로그인한 사람이 누구인지" 알려주는 엔드포인트."""
    user = get_user(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")

    return {
        "id": user["id"],
        "nickname": user["nickname"],
        "profile_image_url": user["profile_image_url"],
    }


class KeywordGroupCreate(BaseModel):
    title: str
    keywords: list[str]


@app.post("/api/keyword-groups")
async def create_keyword_group_endpoint(
    body: KeywordGroupCreate, user_id: int = Depends(require_login)
):
    """
    "관심 논문 알리미 > 관심 키워드 직접 입력" 화면에서 [등록] 버튼을 눌렀을 때
    호출되는 API. title과 keywords 목록을 받아 로그인한 사용자 소유로 저장한다.

    source="manual"로 고정 저장한다 - 나중에(로드맵 2-4) LLM 대화로 키워드를
    뽑아내는 플로우가 추가되면, 같은 테이블에 source="llm_chat"으로 저장하게 된다.
    """
    group = create_keyword_group(user_id, body.title, body.keywords, source="manual")
    return group


@app.get("/api/keyword-groups")
async def list_keyword_groups_endpoint(user_id: int = Depends(require_login)):
    """마이페이지에서 "내가 등록한 관심 키워드 그룹들"을 보여줄 때 쓰는 조회 API."""
    return list_keyword_groups(user_id)


class KeywordGroupUpdate(BaseModel):
    title: str


@app.patch("/api/keyword-groups/{group_id}")
async def update_keyword_group_endpoint(
    group_id: int, body: KeywordGroupUpdate, user_id: int = Depends(require_login)
):
    """그룹 제목 수정. 마이페이지의 [수정] 모드에서 제목을 바꾸고 저장할 때 호출된다."""
    updated = update_keyword_group_title(user_id, group_id, body.title)
    if not updated:
        # 그룹이 없거나(잘못된 id) 남의 그룹이면 둘 다 404로 처리한다 - "남의 그룹이라
        # 권한 없음"과 "애초에 없는 그룹"을 구분해서 알려주면 다른 사람의 그룹 id가
        # 존재하는지 추측하는 데 악용될 수 있어서, 둘 다 같은 응답으로 합친다.
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다.")
    return {"ok": True}


@app.delete("/api/keyword-groups/{group_id}")
async def delete_keyword_group_endpoint(group_id: int, user_id: int = Depends(require_login)):
    """그룹 전체 삭제. 마이페이지의 [삭제] 버튼 + 확인 팝업에서 호출된다."""
    deleted = delete_keyword_group(user_id, group_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다.")
    return {"ok": True}


class KeywordCreate(BaseModel):
    text: str


@app.post("/api/keyword-groups/{group_id}/keywords")
async def add_keyword_endpoint(
    group_id: int, body: KeywordCreate, user_id: int = Depends(require_login)
):
    """
    그룹에 키워드 하나 추가. 마이페이지에서 [+] 버튼 → 텍스트 입력 → 엔터/체크(✓)로
    확정했을 때 호출된다.
    """
    keyword = add_keyword(user_id, group_id, body.text)
    if keyword is None:
        raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다.")
    return keyword


@app.delete("/api/keywords/{keyword_id}")
async def delete_keyword_endpoint(keyword_id: int, user_id: int = Depends(require_login)):
    """
    키워드 하나 삭제. 마이페이지에서 키워드 칩 옆의 [x] → 확인 팝업에서 [확인]을
    눌렀을 때 호출된다.
    """
    deleted = delete_keyword(user_id, keyword_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="키워드를 찾을 수 없습니다.")
    return {"ok": True}
