# paper-kakao-pipeline

매일 Hugging Face Daily Papers의 인기 상위 논문 중, 관심 키워드(시계열×LLM,
멀티에이전트/A2A, RAG, LLM 추론 효율, 추론기법)에 해당하는 논문을 골라 요약해서
카카오톡 "나에게 보내기"로 발송하는 서비스.

두 가지 실행 방식이 있다:

- **개인용 스크립트** (`main.py`): 수집 -> 요약 -> 발송을 한 번 실행하는 MVP 버전.
  `.env`에 등록한 내 카카오 계정 하나에만 보낸다.
- **웹 서비스** (`server.py`): FastAPI + 카카오 소셜 로그인으로 여러 사용자가 각자
  로그인해서 관심 키워드를 등록/관리하는 멀티유저 버전. 현재 개발 중 (아래
  [웹 서비스 실행](#웹-서비스-실행-fastapi) 참고, 진행 상황은 `CLAUDE.md`의
  개발 로드맵 참고).

Docker, LangGraph, MCP, RAGAS, AWS 배포는 아직 없다. 단계별로 점진적으로
리팩터링해 나갈 예정.

## uv란?

이 프로젝트는 `pip` + `venv` 대신 [uv](https://docs.astral.sh/uv/)로 가상환경과
의존성을 관리한다. uv는 Rust로 작성된 Python 패키지/프로젝트 매니저로, 기존에
따로 쓰던 `pip`(설치), `venv`(가상환경), `pip-tools`(락파일) 역할을 하나의
도구로 통합했고 속도도 훨씬 빠르다.

핵심 개념 두 가지만 알면 된다:

- **`pyproject.toml`**: 이 프로젝트가 어떤 라이브러리를 쓰는지 선언하는 파일
  (`requirements.txt`의 대체재라고 생각하면 됨)
- **`uv.lock`**: `pyproject.toml`에 선언된 라이브러리들의 정확한 버전과 하위
  의존성까지 전부 고정한 파일. 이게 있으면 "내 컴퓨터에선 되는데 다른 곳에선
  안 돼요" 문제가 크게 줄어든다. 직접 수정하지 않고 uv가 자동으로 관리한다.

자주 쓰는 명령어:

```bash
uv add <패키지명>       # 라이브러리 설치 + pyproject.toml/uv.lock 자동 갱신
uv remove <패키지명>    # 라이브러리 제거
uv sync                 # uv.lock 기준으로 가상환경을 정확히 동기화 (팀원 합류 시 등)
uv run python main.py   # 가상환경 activate 없이 바로 실행
uv run <아무 명령어>     # 그 가상환경 안에서 명령어 실행
```

가상환경을 직접 `activate` 할 필요 없이 `uv run`을 앞에 붙이면 알아서
`.venv`를 찾아 실행해준다는 점이 pip/venv 조합과 가장 다른 부분이다.

## 설치

uv가 없다면 먼저 설치:

```bash
pip install uv  # 또는 curl -LsSf https://astral.sh/uv/install.sh | sh
```

프로젝트 의존성 설치 (uv.lock 기준으로 정확히 동일한 버전 설치):

```bash
uv sync
```

새 라이브러리가 필요할 때마다는 이렇게 추가하면 된다 (예: LangGraph 도입 시):

```bash
uv add langgraph langchain-mcp-adapters
```


## 설정

1. `.env.example`을 복사해 `.env` 생성

```bash
cp .env.example .env
```

2. `.env`에 아래 값들 채우기
   - `GEMINI_API_KEY`: 무료 티어. https://aistudio.google.com/apikey
   - `KAKAO_REST_API_KEY`, `KAKAO_CLIENT_SECRET`: https://developers.kakao.com 에서
     앱 생성 후 [앱 설정 > 앱 키]에서 확인 (Client Secret은 하단에서 "사용함"으로
     활성화해야 값이 보임)
   - `SESSION_SECRET_KEY`: 웹 서비스 로그인 세션 쿠키 서명에 쓰는 임의의 랜덤 문자열.
     아래 명령으로 생성:
     ```bash
     uv run python -c "import secrets; print(secrets.token_hex(32))"
     ```

   카카오 개발자 콘솔에서 추가로 설정할 것:
   - **카카오 로그인** 활성화
   - **Redirect URI** 등록: 개인용 스크립트(`kakao_auth_helper.py`)용
     `http://localhost:5000/oauth` + 웹 서비스(`server.py`)용
     `http://localhost:8000/auth/kakao/callback` (둘 다 등록)
   - **동의항목**에서 "카카오톡 메시지 전송", "닉네임", "프로필 사진" 활성화
   - **[앱 설정 > 플랫폼 > Web]**에 발송할 링크의 도메인(예: `https://huggingface.co`)
     등록 - 안 하면 카카오톡 메시지의 버튼이 API 에러 없이 조용히 안 보임 (실전에서
     확인된 함정, 자세한 내용은 `CLAUDE.md` 참고)

관심 키워드 클러스터는 `collector.py`의 `KEYWORD_CLUSTERS`에서 수정할 수 있다.
`time_series` 클러스터만 예외적으로 "시계열 관련 단어"와 "LLM 관련 단어"가
**둘 다** 있어야 통과하도록 `require_all_of`로 묶여 있다 (순수 통계 시계열 논문 배제).

3. 카카오 토큰 최초 발급 (한 번만 실행)

```bash
uv run python kakao_auth_helper.py
```

## 실행 (개인용 스크립트)

```bash
uv run python main.py
```

성공하면 카카오톡 "나에게 보내기"로 오늘의 논문 요약이 도착한다.

## 웹 서비스 실행 (FastAPI)

여러 사용자가 각자 로그인해서 자신의 관심 키워드를 등록/관리하는 버전.

```bash
uv run uvicorn server:app --reload
```

- `http://localhost:8000/` 접속 → "카카오로 시작하기"로 로그인
- 로그인하면 `http://localhost:8000/mypage`에서 관심 키워드 그룹을 등록/수정/삭제
- 최초 실행 시 `app.db`(SQLite)가 자동 생성됨 (커밋 대상 아님, `.gitignore` 참고)
- 아직 이 웹 서비스가 실제로 카카오톡을 발송하지는 않는다 (로그인 + 키워드 관리까지만
  구현됨 - 발송 연결은 로드맵 2-3에서 진행 예정, 자세한 내용은 `CLAUDE.md` 참고)

## 개발 로드맵

전체 로드맵과 각 단계의 상세 설계(DB 스키마, API 엔드포인트, UX 스펙 등)는
`CLAUDE.md`에 있다. 요약하면:

- [x] 1. MVP: 수집 + 요약 + 카카오 발송 (개인용 스크립트)
- [ ] 2. FastAPI + 카카오 소셜 로그인 + DB로 멀티유저 구조 전환
  - [x] 2-1. 카카오 소셜 로그인
  - [x] 2-2. 관심 키워드 직접 입력 (그룹 생성/수정/삭제 + 마이페이지 UI)
  - [ ] 2-3. 사용자별 키워드로 카카오 발송 연결
  - [ ] 2-4. LLM 대화형 키워드 추출
- [ ] 3. Docker 컨테이너화
- [ ] 4. 논문 검색/조회 로직을 MCP 서버로 분리
- [ ] 5. LangGraph로 파이프라인 그래프화
- [ ] 6. RAGAS로 요약 품질 평가 하네스 구축
- [ ] 7. AWS 배포 + 스케줄링
- [ ] 8. (선택) vLLM 셀프호스팅, A2A 멀티에이전트 통신
