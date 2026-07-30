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

AWS 배포는 아직 없다. 단계별로 점진적으로 리팩터링해 나갈 예정.

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
- 로그인 후 홈 화면의 **"관심 키워드 등록"**(직접 입력) / **"AI 기반 관심 키워드
  찾기"**(LLM과 대화하며 찾기) 버튼을 누르면 페이지 이동 없이 팝업으로 바로 등록할 수 있다
- `http://localhost:8000/mypage`에서 등록한 관심 키워드 그룹을 조회/수정/삭제하고,
  그룹별 발송 on/off 스위치로 "오늘은 이 그룹 논문만 받고 싶다" 같은 조정도 가능하다
- 마이페이지의 **"지금 논문 받아보기"** 버튼을 누르면 그 자리에서 수집 -> 요약 ->
  카카오톡 발송까지 한 번에 실행된다 (발송 꺼둔 그룹은 제외, 자동 스케줄링은 아직 없음
  - 로드맵 7번 참고)
- 최초 실행 시 `app.db`(SQLite)가 자동 생성됨 (커밋 대상 아님, `.gitignore` 참고)

## Docker로 실행

웹 서비스(`server.py`)를 컨테이너로 띄울 수 있다. `.env`는 [설정](#설정) 단계까지
먼저 끝내둬야 한다 (이미지에는 포함되지 않고, 실행 시점에 주입된다).

```bash
docker compose up --build
```

- `http://localhost:8000/`으로 접속하는 방식은 로컬에서 `uv run uvicorn`으로 띄웠을
  때와 동일하다 (포트 매핑이 8000:8000이라 카카오 콘솔의 Redirect URI를 새로 등록할
  필요 없음).
- `app.db`는 이미지 레이어가 아니라 `app-data`라는 이름의 Docker 볼륨에 저장된다
  (`DB_PATH` 환경변수로 `db.py`에 전달) - `docker compose down` 후 다시 `up`해도
  데이터가 그대로 남는다. 완전히 초기화하려면 `docker compose down -v`.
- 개인용 스크립트(`main.py`)를 컨테이너 안에서 한 번 실행하고 싶다면:
  ```bash
  docker compose run --rm web uv run python main.py
  ```

## MCP 서버

논문 검색/조회 로직(`collector.py`)을 `mcp_server.py`로 별도 노출해뒀다 - 이 앱의
파이썬 코드를 직접 import하지 않고도, Claude Desktop 같은 MCP 클라이언트가 표준
프로토콜로 논문 검색 도구를 가져다 쓸 수 있다 (설계 배경은 `CLAUDE.md`의 "MCP 서버"
섹션 참고). 웹 서비스(`server.py`)의 동작에는 영향 없음 - 그쪽은 여전히
`collector.py`를 직접 호출한다 (아래 LangGraph 파이프라인을 통해서).

```bash
uv run mcp dev mcp_server.py   # MCP Inspector(웹 UI)로 도구 직접 테스트
uv run python mcp_server.py    # stdio 서버로 실행 (MCP 클라이언트가 이 커맨드로 실행)
```

## LangGraph 파이프라인

수집(Collector) -> 필터(Filter) -> 요약(Summarizer)을 `pipeline_graph.py`의
LangGraph `StateGraph` 노드로 그래프화했다. `main.py`와 `server.py`의
`POST /api/send-now`가 공통으로 `pipeline_graph.run_pipeline(...)` 하나를 호출해서
세 단계를 전부 실행한다 (설계 배경은 `CLAUDE.md`의 "LangGraph 파이프라인" 섹션 참고).

## 요약 품질 평가

`evaluator.py`가 Summarizer가 생성한 요약의 품질을 Gemini 자신을 심사자로 써서
채점한다 (faithful/relevant는 LLM 판단, concise는 길이 체크). 공식 RAGAS 패키지는
langgraph와 의존성 충돌로 설치가 불가능했고 애초에 이 파이프라인 구조와도 잘
안 맞아서 직접 구현했다 - 자세한 사유는 `CLAUDE.md`의 "요약 품질 평가" 섹션 참고.

```bash
uv run python evaluator.py   # 파이프라인을 조금만 돌려서(기본 3편) 채점 리포트 출력
```

## 개발 로드맵

전체 로드맵과 각 단계의 상세 설계(DB 스키마, API 엔드포인트, UX 스펙 등)는
`CLAUDE.md`에 있다. 요약하면:

- [x] 1. MVP: 수집 + 요약 + 카카오 발송 (개인용 스크립트)
- [x] 2. FastAPI + 카카오 소셜 로그인 + DB로 멀티유저 구조 전환
  - [x] 2-1. 카카오 소셜 로그인
  - [x] 2-2. 관심 키워드 직접 입력 (그룹 생성/수정/삭제 + 마이페이지 UI)
  - [x] 2-3. 사용자별 키워드로 카카오 발송 연결 (`POST /api/send-now`)
  - [x] 2-4. LLM 대화형 키워드 추출 (Gemini function calling)
  - [x] 2-5. 홈 화면 진입점 분리 + 그룹별 발송 on/off
- [x] 3. Docker 컨테이너화
- [x] 4. 논문 검색/조회 로직을 MCP 서버로 분리
- [x] 5. LangGraph로 파이프라인 그래프화
- [x] 6. 요약 품질 평가 하네스 구축 (RAGAS 대신 자체 LLM-as-judge로 구현)
- [ ] 7. AWS 배포 + 스케줄링
- [ ] 8. (선택) vLLM 셀프호스팅, A2A 멀티에이전트 통신
