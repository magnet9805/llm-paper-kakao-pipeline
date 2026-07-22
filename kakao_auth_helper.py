"""
카카오톡 "나에게 보내기" 최초 1회 수동 인증 스크립트.

실행:
    uv run python kakao_auth_helper.py

브라우저가 열리면 카카오 로그인 후 동의하면 되고, 발급받은 토큰을
kakao_token.json에 저장한다. 이후 kakao_sender.py가 이 파일을 읽어
access_token을 자동 갱신한다.

카카오 개발자 콘솔에 Redirect URI로 http://localhost:5000/oauth 를
등록해둬야 한다 (README 참고).
"""

import os
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import requests
from dotenv import load_dotenv

from kakao_sender import KAKAO_TOKEN_FILE, save_tokens

load_dotenv()

KAKAO_REST_API_KEY = os.environ["KAKAO_REST_API_KEY"]
KAKAO_CLIENT_SECRET = os.environ.get("KAKAO_CLIENT_SECRET")
REDIRECT_URI = "http://localhost:5000/oauth"
AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"

_auth_code: dict = {}


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        _auth_code["code"] = query.get("code", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("인증이 완료되었습니다. 이 창은 닫아도 됩니다.".encode("utf-8"))

    def log_message(self, format, *args):
        pass  # 콘솔에 HTTP 접근 로그를 남기지 않는다.


def _get_authorization_code() -> str:
    server = HTTPServer(("localhost", 5000), _OAuthCallbackHandler)
    # talk_message는 선택 동의 항목이라 scope에 명시해야 동의 화면에 노출된다.
    auth_url = (
        f"{AUTHORIZE_URL}?client_id={KAKAO_REST_API_KEY}"
        f"&redirect_uri={REDIRECT_URI}&response_type=code&scope=talk_message"
    )
    print(f"브라우저에서 아래 주소를 열어 카카오 로그인/동의를 진행하세요:\n{auth_url}")
    webbrowser.open(auth_url)

    while "code" not in _auth_code:
        server.handle_request()

    return _auth_code["code"]


def main():
    code = _get_authorization_code()

    data = {
        "grant_type": "authorization_code",
        "client_id": KAKAO_REST_API_KEY,
        "redirect_uri": REDIRECT_URI,
        "code": code,
    }
    if KAKAO_CLIENT_SECRET:
        data["client_secret"] = KAKAO_CLIENT_SECRET

    res = requests.post(TOKEN_URL, data=data, timeout=10)
    res.raise_for_status()
    save_tokens(res.json())
    print(f"인증 완료. {KAKAO_TOKEN_FILE}에 토큰을 저장했습니다.")


if __name__ == "__main__":
    main()
