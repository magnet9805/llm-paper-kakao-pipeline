"""
FastAPI 웹 서비스 진입점. 카카오 소셜 로그인(Authlib)으로 회원가입/로그인을 통합한다.

실행:
    uv run uvicorn server:app --reload

카카오 개발자 콘솔에 Redirect URI로 http://localhost:8000/auth/kakao/callback 를
등록해둬야 한다. talk_message(카카오톡 메시지 전송) 동의도 로그인 시점에 함께 받는다.
"""

import os
from datetime import datetime, timedelta

from authlib.integrations.starlette_client import OAuth
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.responses import RedirectResponse

from db import get_user, init_db, upsert_user

load_dotenv()

app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=os.environ["SESSION_SECRET_KEY"])

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


@app.get("/auth/kakao/login")
async def kakao_login(request: Request):
    redirect_uri = request.url_for("kakao_callback")
    return await oauth.kakao.authorize_redirect(request, redirect_uri)


@app.get("/auth/kakao/callback")
async def kakao_callback(request: Request):
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
    return RedirectResponse(url="/auth/me")


@app.post("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/auth/me")
async def me(request: Request):
    user_id = request.session.get("user_id")
    if user_id is None:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다.")

    user = get_user(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="사용자를 찾을 수 없습니다.")

    return {
        "id": user["id"],
        "nickname": user["nickname"],
        "profile_image_url": user["profile_image_url"],
    }
