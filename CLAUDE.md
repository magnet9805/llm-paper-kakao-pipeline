# 프로젝트 컨텍스트 (Claude Code용)

이 파일은 Claude Code가 세션 시작 시 자동으로 읽는 컨텍스트 파일이다.
설계 논의 내용을 요약해뒀으니, 작업 전에 반드시 참고할 것.

## 프로젝트 목적

관심 키워드에 맞는 최신 논문(멀티에이전트, RAG, LLM 기반 시계열예측, 추론기법 등)을
매일 요약해서 카카오톡으로 받아보는 "관심 논문 카톡 알리미" 서비스.

개인용 스크립트(MVP)로 시작해, 회원가입/로그인 + 마이페이지 + 관심 키워드 관리 +
카카오 발송을 갖춘 웹 서비스로 확장하는 것을 목표로 한다.

기술적으로는 아래 스택을 단계적으로 도입하며, 각 단계는 이전 단계의 자연스러운
다음 문제(배포 자동화, 재사용 가능한 도구화, 멀티에이전트 오케스트레이션, 품질
평가, 인프라 확장)를 해결하는 방향으로 이어진다:
FastAPI, Docker, MCP, LangGraph/LangChain, RAGAS, AWS, vLLM, A2A

인증·세션·DB 같은 주변부 인프라는 표준 라이브러리에 위임해 최소한으로 구현하고,
리소스는 핵심 로직(수집·필터링·LLM 기반 요약 및 키워드 추출 파이프라인)에
집중하는 것을 설계 원칙으로 한다.

## 현재 단계: MVP (완료), 웹 서비스로 전환 준비 중

- 수집(collector.py) -> 요약(summarizer.py) -> 발송(kakao_sender.py)을
  main.py가 순서대로 실행하는 개인용 스크립트 버전은 완료됨
- 지금부터는 이 로직을 멀티유저 웹 서비스 구조로 리팩터링하는 단계
- 패키지 관리는 pip/venv가 아니라 **uv**를 사용 (`uv add`, `uv sync`, `uv run`)

## 웹 서비스 컨셉

로그인한 사용자가 자신의 관심 키워드를 설정하면, 그 키워드에 맞는 논문을
카카오톡으로 매일 받아보는 서비스. 홈페이지 구성:

- 로그인(카카오 소셜 로그인) / 내 정보(마이페이지)
- 버튼 1: **관심 논문 알리미**
  - 1-1. 관심 키워드 직접 입력
  - 1-2. LLM과 대화하며 관심 키워드 찾기 (아래 상세 스펙 참고)
- 버튼 2: **핫한 논문 알리미**
  - AI 한정이 아니라 범사회적으로 최근 화제인 키워드 관련 논문을 다룸
  - 트렌드 소스(뉴스 API, 실시간 검색어 등) → 관련 논문 검색이라는 2단계 파이프라인 필요
  - 논문 검색 범위도 cs.* 카테고리에 한정하지 않고 전체 분야로 확장 필요
  - 별도의 데이터 소스·매칭 로직이 필요해 난이도가 높으므로 로드맵 후순위로 배치

마이페이지에서는 사용자가 설정해둔 관심 키워드(그룹 단위)를 조회/관리할 수 있어야 함.

## 개발 로드맵

1. [x] MVP: HF Daily Papers 수집 + 키워드 필터 + Gemini API(무료 티어) 요약 + 카카오 발송 (개인용 스크립트)
2. [ ] FastAPI + 카카오 소셜 로그인 + DB(SQLite)로 멀티유저 구조 전환
   - [x] 2-1. 카카오 소셜 로그인 (Authlib) - 회원가입/로그인 통합 (server.py, db.py)
   - [x] 2-2. 관심 키워드 "직접 입력" 플로우 (그룹 생성/수정/삭제 + 키워드 추가/삭제 API +
     마이페이지 조회/편집 UI) (`/api/keyword-groups` 전체 CRUD, `templates/` 프론트엔드 포함)
   - [x] 2-3. 기존 collector.py를 사용자별 키워드로 파라미터화해서 카카오 발송까지 연결
     (`POST /api/send-now` 수동 트리거, `sent_papers` 테이블로 사용자별 중복 방지,
     DB의 사용자별 kakao 토큰으로 발송 - 자동 스케줄링은 로드맵 7번에서 붙일 예정)
   - [x] 2-4. LLM 대화형 키워드 추출 (아래 스펙대로 구현, `keyword_chat.py` +
     `POST /api/keyword-chat` + `templates/_chat_modal.html`)
   - [x] 2-5. 홈 화면 진입점 분리 + 그룹별 발송 on/off (스펙에 없던 추가 개선,
     아래 "홈 화면 진입점"·"그룹별 발송 on/off" 섹션 참고)
3. [x] Docker 컨테이너화 (아래 "Docker 컨테이너화" 섹션 참고)
4. [x] 논문 검색/조회 로직을 MCP 서버로 분리 (아래 "MCP 서버" 섹션 참고)
5. [x] LangGraph로 Collector/Filter/Summarizer 노드 그래프화 (아래 "LangGraph 파이프라인" 섹션 참고)
6. [x] RAGAS로 요약 품질 평가 하네스 구축 (실제로는 ragas 패키지를 포기하고 직접
   구현 - 아래 "요약 품질 평가" 섹션 참고)
7. [ ] AWS 배포 + 도메인 연결 + 스케줄링 (EventBridge/ECS)
8. [ ] (선택) vLLM 셀프호스팅으로 요약 모델 교체
9. [ ] (선택) A2A로 Collector/Evaluator 에이전트 간 통신 분리
10. [ ] (후순위) 핫한 논문 알리미 - 트렌드 소스 연동 + 전체 분야 논문 검색
11. [ ] Agent System 고도화: 직무 갭 분석 에이전트 (아래 "Agent System 고도화" 섹션 참고)

한 번에 다 만들지 않고, 단계별로 점진적으로 리팩터링하는 방식으로 진행 중.

## 논문 수집 소스: Hugging Face Daily Papers

- API: `https://huggingface.co/api/daily_papers?date=YYYY-MM-DD&limit=100`
- 구글 스칼라는 공식 API가 없고 크롤링이 이용약관 위반 소지가 있어 사용하지 않기로 함
- `upvotes` 필드 기준으로 그날의 상위 30개(top_n)를 추린 뒤 키워드로 필터링

## 관심 키워드 클러스터 (직접 입력 시 기본 프리셋으로 활용, collector.py의 KEYWORD_CLUSTERS)

아래 5개 클러스터로 구성 (동등 가중치, 우선순위 없음):

1. **time_series**: LLM 기반 시계열예측만 (통계/전통 ML 시계열은 배제)
   - 특수 로직: `require_all_of`로 "시계열 단어" AND "LLM 단어"가 둘 다 있어야 통과
2. **multi_agent**: 멀티에이전트, A2A(agent2agent), tool use 등
3. **rag**: retrieval-augmented generation, hybrid retrieval 등
4. **inference_efficiency**: vLLM 관련 - speculative decoding, KV cache, quantization 등
5. **reasoning**: chain-of-thought, test-time scaling 등

한 클러스터라도 매칭되면 통과(OR), 여러 클러스터에 걸릴수록 랭킹에서 우선순위를 줌.
웹 서비스에서는 이 클러스터들을 "직접 입력" 화면의 추천 프리셋으로 노출하는 것도 고려.

## 인증 방식: 카카오 소셜 로그인 하나로 통합

이메일/비밀번호 회원가입은 만들지 않기로 함. 이유:
- 이 서비스는 어차피 카카오톡으로 메시지를 보내야 하므로, 카카오 로그인(OAuth)을
  인증 수단으로 쓰면 "로그인"과 "메시지 발송 권한 획득"이 한 번의 OAuth 플로우로 동시에 끝남
- 비밀번호 저장/해싱/재설정 같은 인증 자체의 번거로운 부분이 통째로 사라짐
- 인증은 표준 라이브러리에 위임하고, 핵심 로직(LLM 기반 파이프라인)에 집중하기 위함

**사용 라이브러리:**
- OAuth 플로우: **Authlib**
- 세션 관리: FastAPI/Starlette 내장 `SessionMiddleware` (쿠키 기반)

**엔드포인트:**
```
GET  /auth/kakao/login     → 카카오 로그인 페이지로 리다이렉트
GET  /auth/kakao/callback  → 인증 코드 받아서 토큰 교환, users 테이블에 upsert, 세션 쿠키 발급
POST /auth/logout          → 세션 쿠키 삭제
GET  /auth/me              → 현재 로그인한 사용자 정보 (JSON API)
```

`signup`이 따로 없음 - 콜백에서 처음 오는 `kakao_id`면 새로 생성, 이미 있으면 로그인 처리.

기존 `kakao_auth_helper.py`(개인용 1회성 수동 인증 스크립트)는 이 플로우로 대체됨.
`kakao_sender.py`의 토큰 자동 갱신 로직(refresh_token 사용)은 그대로 재사용 가능
(단, `.env`가 아니라 DB의 사용자별 토큰을 읽어오도록 수정 필요).

**Authlib + 카카오 연동 시 겪은 함정 (공식 문서에 없고 실전에서 확인된 내용):**
- `oauth.register(...)`에 `token_endpoint_auth_method="client_secret_post"`를 명시해야 함.
  기본값(`client_secret_basic`, client_id/secret을 HTTP Basic 헤더로 전송)을 쓰면 카카오
  토큰 엔드포인트가 `invalid_client: Not exist client_id [null]` 에러를 반환한다 - 카카오는
  client_id/secret을 폼 body 파라미터로만 받는다.
- 닉네임/프로필 사진은 "선택 동의" 항목이라, `client_kwargs={"scope": "..."}`에
  `profile_nickname profile_image`를 명시적으로 넣어야 응답에 채워진다. (마찬가지로
  카카오톡 메시지 전송 권한은 `talk_message`를 넣어야 함 - 위 참고.) 안 넣으면 로그인은
  되지만 `nickname`/`profile_image_url`이 조용히 `null`로 온다.

## DB 스키마 (SQLite, 로컬 프로토타입 기준)

```sql
-- 카카오 로그인이 곧 회원가입이므로 password 필드 없음.
-- 카카오 access/refresh token도 여기 같이 저장 (별도 kakao_accounts 테이블 불필요).
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    kakao_id TEXT UNIQUE NOT NULL,
    nickname TEXT,
    profile_image_url TEXT,
    kakao_access_token TEXT NOT NULL,
    kakao_refresh_token TEXT NOT NULL,
    kakao_token_expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE keyword_groups (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    title TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('manual', 'llm_chat')),
    is_active INTEGER NOT NULL DEFAULT 1,  -- 그룹별 발송 on/off (아래 섹션 참고)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE keywords (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES keyword_groups(id) ON DELETE CASCADE,
    keyword_text TEXT NOT NULL
);

-- 개인용 스크립트의 전역 seen_papers.json과 달리, 사용자마다 "이미 보낸 논문"이
-- 달라야 해서 사용자별로 발송 이력을 남긴다.
CREATE TABLE sent_papers (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    hf_id TEXT NOT NULL,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, hf_id)
);
```

> SQLite는 `ON DELETE CASCADE`를 기본적으로 무시한다 - 연결마다 `PRAGMA foreign_keys = ON`을
> 실행해야 실제로 동작한다 (`db.py`의 `get_connection()`에 이미 반영되어 있음).

> `is_active` 컬럼은 2-5에서 추가됨. `CREATE TABLE IF NOT EXISTS`는 이미 만들어진 테이블에
> 새 컬럼을 넣어주지 않으므로, `db.py`의 `init_db()`가 `_migrate()`를 통해 기존 `app.db`에
> `ALTER TABLE ... ADD COLUMN`을 1회성으로 실행해 보정한다 (컬럼이 이미 있으면 아무 것도
> 안 함). 앞으로 스키마에 컬럼을 더 추가할 때도 이 패턴(SCHEMA에 새 컬럼 추가 + `_migrate()`에
> 조건부 ALTER 추가)을 재사용하면 된다.

**관심 키워드 그룹 API 엔드포인트 (구현 완료, `server.py`):**
```
POST   /api/keyword-groups                       # 그룹 생성 (title, keywords[], source) - "직접 입력"은 source="manual"(기본값), 대화형은 source="llm_chat"
GET    /api/keyword-groups                        # 내 그룹 목록 조회 (마이페이지용)
PATCH  /api/keyword-groups/{group_id}              # 그룹 제목 수정
PATCH  /api/keyword-groups/{group_id}/active       # 그룹별 발송 on/off 토글 (body: {is_active: bool})
DELETE /api/keyword-groups/{group_id}              # 그룹 전체 삭제 (키워드도 CASCADE로 같이 삭제)
POST   /api/keyword-groups/{group_id}/keywords     # 그룹에 키워드 하나 추가
DELETE /api/keywords/{keyword_id}                  # 키워드 하나 삭제
POST   /api/keyword-chat                           # LLM 대화형 키워드 찾기 한 턴 (아래 섹션 참고)
```
모든 엔드포인트는 `require_login` 의존성으로 로그인을 요구하고, 그룹/키워드가 요청한
사용자 소유인지 SQL의 `WHERE user_id = ?` 절로 확인한다 (남의 그룹 id를 넣어도 404).

## 사용자별 논문 발송 (구현 완료, `POST /api/send-now`)

개인용 스크립트(`main.py`)의 collector/summarizer/kakao_sender를 그대로 재사용하되,
"사용자별로 다른 부분"만 바꿔치기하는 방식으로 연결했다:

| 개인용 스크립트 (main.py)              | 웹 서비스 (server.py의 send-now)                     |
|----------------------------------------|-------------------------------------------------------|
| `.env`의 고정 `KEYWORD_CLUSTERS`       | 이 사용자의 `list_keyword_groups()` 결과로 만든 클러스터 (그룹 1개 = 클러스터 1개, 그룹 제목이 곧 클러스터 이름) |
| `seen_papers.json` (전역 파일)         | `sent_papers` 테이블 (사용자별 발송 이력)             |
| `kakao_token.json` (전역 파일)         | `users` 테이블의 이 사용자 kakao 토큰 컬럼            |

이 매핑 덕분에 `collector.py`/`kakao_sender.py`는 각각 `clusters`/`seen_ids`,
`access_token`을 인자로 받는 형태로만 살짝 파라미터화됐고, 실제 수집/필터링/요약/
발송 로직 자체는 손대지 않았다. `kakao_sender.py`에는 파일 기반 경로
(`_refresh_access_token`, `send_daily_papers` - main.py용)와 DB 기반 경로
(`refresh_user_access_token`, `send_papers` - server.py용)가 공존한다.

지금은 마이페이지의 "지금 논문 받아보기" 버튼으로 수동 트리거해야 한다. 매일 자동
실행되는 스케줄링은 로드맵 7번(AWS EventBridge/ECS)에서 붙일 예정.

`_clusters_from_keyword_groups()`는 `is_active=False`로 꺼둔 그룹을 클러스터 구성에서
제외한다 - 관심 키워드로 등록은 해뒀지만 오늘은 다른 그룹의 논문만 받고 싶은 경우를 위한
기능(2-5). 그룹/키워드 자체는 지워지지 않고, 발송 대상에서만 빠진다.

## 프론트엔드 (서버 렌더링, `templates/`)

React/Vue 같은 SPA 프레임워크는 쓰지 않고, FastAPI의 `Jinja2Templates`로 서버에서
HTML을 직접 렌더링한다 - 이 프로젝트의 리소스는 백엔드/LLM 파이프라인에 집중하는 게
설계 원칙이라, 프론트는 최소 구성으로 감. 상태가 필요한 부분(모달 열기/닫기, 키워드
칩 편집)만 바닐라 JS로 처리하고, 화면 전환은 그냥 서버 라우트 이동.

**파일 구성:**
- `templates/base.html`: 공통 레이아웃. 상단 네비(홈/마이페이지/로그아웃), 전역 CSS
  변수(`--kakao`, `--ink`, `--radius` 등), `logout()` 함수를 여기 한 곳에 둠.
- `templates/index.html`: 홈 화면 (`GET /`). 전체 화면 히어로 섹션 - 실제 사진 대신
  그라디언트 배경 + 인라인 SVG(문서+카카오톡 말풍선 모양 일러스트)로 "관심 논문을
  카카오톡으로 받는다"는 컨셉을 표현함 (외부 이미지 URL에 의존하지 않아 깨질 일이 없음).
  로그인 시 "관심 키워드 등록"/"AI 기반 관심 키워드 찾기" 두 버튼을 보여줌 (아래
  "홈 화면 진입점" 섹션 참고).
- `templates/mypage.html`: 마이페이지 (`GET /mypage`). 키워드 그룹 목록 + 그룹별
  수정/삭제 아이콘 버튼(연필/휴지통, 그룹 박스 우측) + "+ 새 그룹 등록" 토글 버튼 +
  그룹별 발송 on/off 스위치.
- `templates/_chat_modal.html`, `templates/_manual_modal.html`: 키워드 등록 팝업
  (대화형/직접입력). `index.html`과 `mypage.html` 양쪽에서 `{% include %}`로 재사용하는
  공유 partial (아래 "홈 화면 진입점" 섹션 참고).

**마이페이지 편집 UX (중요 - 2-4에서도 재사용할 패턴):**
- [수정] 아이콘 클릭 → 페이지 안에서 인라인으로 바뀌지 않고 **팝업(모달)**이 뜸.
  모달 안에서 제목 입력창 + 키워드 칩 목록을 편집.
- 키워드 삭제: 칩 옆 `✕` 클릭 → "삭제하시겠습니까?" confirm() → 확인 시 즉시 DELETE
  API 호출 + "삭제되었습니다" alert(). 이 삭제/추가는 모달의 [저장]과 별개로 즉시
  서버에 반영됨 (제목 변경만 [저장]을 눌러야 반영).
- 키워드 추가: 목록 끝의 `+` 클릭 → 기존 키워드 칩과 똑같은 모양(회색 알약)의 칸이
  텍스트 입력 가능한 상태로 바뀌고, 오른쪽에 `✓`(확정) - `✕`(취소) 순서로 버튼이 붙음.
  엔터 또는 `✓` 클릭으로 확정. 공백/특수문자만 입력한 경우는 무시(`isValidKeywordText`).
  [저장] 버튼을 누르면, `✓`를 안 눌렀어도 입력 중이던 유효한 텍스트가 있으면 그것도
  같이 커밋한다 (깜빡하고 저장만 누르는 경우를 위한 배려).
- 모달에서 바뀐 내용(제목/키워드)은 모달을 닫기 전에 뒤에 깔린 마이페이지 카드에도
  바로 반영됨 (새로고침 불필요) - `groups_json`으로 서버가 내려준 데이터를 JS
  `groupsData` 배열에 캐싱해두고 그걸 기준으로 모달/메인 목록을 둘 다 다시 그림.
- **이 x-삭제(confirm 팝업) / +-추가(체크·엑스 버튼) 패턴은 2-4(LLM 대화형 키워드
  추출)의 등록 확인 팝업 키워드 편집(`_chat_modal.html`의 `renderConfirmKeywords()`)에
  그대로 재사용됨.**
- "+ 새 그룹 등록"은 상시 노출된 폼이 아니라, 클릭 전엔 점선 테두리 버튼(호버 시
  테두리 강조)만 보이고 클릭하면 폼이 펼쳐지는 방식.

## LLM 대화형 키워드 추출 - 확정된 스펙 (구현 완료)

아래 스펙대로 `keyword_chat.py`(Gemini function calling) + `POST /api/keyword-chat`
+ `templates/_chat_modal.html`로 구현 완료됨. 모델은 `gemini-flash-latest`(무료 티어),
시스템 프롬프트에서 "대화 초반 1~2턴은 섣불리 제안하지 말 것"과 "keywords는 반드시
영어로 작성할 것"(논문 원문이 영어라 매칭되려면 영어 표현이어야 함)을 명시한다.
백엔드는 무상태 - 대화 기록을 서버에 저장하지 않고 프론트가 매 턴 전체 history를
다시 보낸다.

### 전체 흐름

1. "나의 관심 키워드 찾기" 버튼 클릭 → 대화형 모달 팝업
2. AI 첫 메시지: "AI에 관하여 어떤 내용들에 관심이 있으신가요? 관심 키워드를 함께 찾아보아요."
3. 사용자와 대화 진행 (멀티턴)
4. 모델이 충분한 정보가 모였다고 판단하면 **function calling**으로 키워드 그룹을 제안
   (섣불리 첫 턴부터 제안하지 않도록 시스템 프롬프트에 명시할 것)
5. 제안된 키워드들이 칩(chip) 버튼으로, 그 아래 "선택" 버튼과 함께 표시됨
6. 사용자가 칩을 클릭 = 로컬 상태에서 선택/해제 토글만 (아직 API 호출 없음)
7. 하나 이상 선택되면 "선택" 버튼 활성화. "전체 선택"은 모든 칩을 한 번에 선택 상태로
   토글하는 역할 (결국 개별/전체 모두 "선택" 버튼을 눌러야 다음 단계로 진행되는
   동일한 흐름으로 통일됨)
8. "선택" 버튼 클릭 → 등록 확인 팝업 표시:
   - 최상단: title 입력창 (LLM이 생성한 제목이 기본값으로 들어있으나 사용자가 직접 수정 가능)
   - 중간: 방금 선택한 키워드들 표시
   - 우측 하단: [취소] [등록] 버튼
9. **취소**: 팝업만 닫힘, 칩 선택 상태 유지, 채팅으로 복귀 (재시도 가능)
10. **등록**: 이 시점에만 실제로 `POST /api/keyword-groups` 호출하여 DB에 저장
11. 사용자가 아무것도 선택하지 않고 다음 메시지를 보내면, 직전 키워드 카드는
    자동으로 비활성화(회색 처리 + 모든 버튼 disabled) 처리됨
12. 한 대화 세션에서 여러 그룹을 등록할 수 있도록 열어둠 (모달은 등록 후에도
    자동으로 닫히지 않고, 사용자가 명시적으로 "닫기"를 눌러야 닫힘)

### 카드 상태 3가지

| 상태 | 시각적 표시 | 버튼 |
|---|---|---|
| active | 일반 | 칩 클릭 가능 |
| registered | ✓ 등록됨 뱃지 | 전부 비활성화 |
| dismissed | 회색/흐림 | 전부 비활성화 |

등록되지 않은 카드를 계속 활성 상태로 남겨두지 않는 이유: 세션/DB 부하 방지.
등록 API는 사용자가 명시적으로 "등록" 버튼을 눌렀을 때만 호출된다.

### Function Calling 스키마 (초안)

```python
tools = [{
    "name": "propose_keyword_group",
    "description": "사용자와의 대화에서 관심 주제가 충분히 파악됐을 때, 구조화된 키워드 그룹을 제안한다. 아직 충분히 파악되지 않았다면 이 도구를 호출하지 말고 계속 대화로 질문할 것.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "이 키워드 그룹의 대표 제목"},
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "description": "논문 필터링에 쓸 구체적 키워드 5~8개"
            }
        },
        "required": ["title", "keywords"]
    }
}]
```

안내 문구("마음에 드신다면 관심 키워드로 등록할 수 있습니다!")는 모델이 매번
다르게 생성하게 두지 않고, tool_use가 감지되면 프론트엔드에서 고정 문구로
붙이는 방식으로 결정함 (UI 일관성 때문).

### API 엔드포인트 (키워드 챗 관련, 딱 2개)

```
POST /api/keyword-chat        # 대화 한 턴 (LLM 응답 + 필요시 tool_use로 제안). 백엔드는 무상태로, 프론트가 history를 매번 전달
POST /api/keyword-groups      # 등록 확정 시점에만 호출 (title, keywords[])
```

## 홈 화면 진입점 (2-5)

원래 스펙(위 "웹 서비스 컨셉")대로 "관심 키워드 직접 입력"과 "LLM과 대화하며 찾기"를
홈 화면에서 바로 시작할 수 있어야 한다는 요구를 반영해, 로그인 후 홈 화면에 마이페이지로
이동하는 링크 하나 대신 두 버튼을 둔다:
- **관심 키워드 등록** (`openManualModal()`) - `_manual_modal.html`의 팝업 (제목 +
  쉼표 구분 키워드 입력, `source` 없이 `POST /api/keyword-groups` 호출 → 기본값 manual)
- **AI 기반 관심 키워드 찾기** (`openChatModal()`) - `_manual_modal.html`이 아니라
  `_chat_modal.html`의 대화형 팝업. 히어로 배경의 보라색 톤과 어울리는 그라디언트
  버튼(`.btn-ai`)으로 카카오 노란 버튼과 구분함.

둘 다 마이페이지로 페이지 이동하지 않고 홈 화면 위에 팝업으로 뜬다 - 대화형 키워드
찾기 UI(칩 선택, 카드 3상태, 등록 확인 팝업)는 마이페이지에서도 똑같이 쓰이므로,
`templates/_chat_modal.html`(대화 모달 + 등록 확인 팝업 + 칩/키워드 칩 편집 관련 CSS·JS
전체)을 별도 partial로 분리해서 `index.html`과 `mypage.html` 양쪽에서 `{% include %}`
한다. 두 페이지가 서로 다르게 처리해야 하는 부분(등록 완료 후 무엇을 할지)만 각
페이지가 정의하는 `onGroupRegistered(group)` 훅으로 분리했다:
- `mypage.html`: `appendNewGroupToMainList(group)`으로 새로고침 없이 목록에 바로 추가
- `index.html`: 그룹 목록이 없으므로 완료 안내 alert만 띄움

이 분리 패턴(공통 UI는 partial, 페이지별 후처리는 훅)은 앞으로 키워드 등록 진입점이
늘어나도(예: 로드맵 후순위의 "핫한 논문 알리미") 그대로 재사용할 수 있다.

## 그룹별 발송 on/off (2-5)

관심 키워드로 그룹을 등록은 해뒀지만, 어떤 날은 그중 일부 그룹의 논문만 받고 싶을 수
있다는 요구를 반영. `keyword_groups.is_active`(기본값 1) 컬럼을 추가하고, 마이페이지의
각 그룹 카드 옆에 on/off 스위치를 둔다.

- 스위치는 카드(`.group`) **안이 아니라 밖**, `.group-row` 컨테이너의 우측에 위치함 -
  "그룹 자체를 편집하는 조작"(수정/삭제, 카드 안의 아이콘)과 "발송 대상 여부"(카드 밖)를
  시각적으로 분리하기 위함.
- 꺼도(`is_active=False`) 그룹/키워드 자체는 삭제되지 않고 그대로 남는다. 다만
  `server.py`의 `_clusters_from_keyword_groups()`가 `POST /api/send-now`의 클러스터를
  구성할 때 꺼진 그룹을 제외한다 - 즉 "발송 대상에서만 빠진다".
- API: `PATCH /api/keyword-groups/{group_id}/active` (body: `{"is_active": bool}`).

## Docker 컨테이너화

웹 서비스(`server.py`)를 컨테이너로 띄울 수 있게 `Dockerfile`, `.dockerignore`,
`docker-compose.yml`을 추가했다 (`main.py` 개인용 스크립트는 컨테이너화 대상이
아니고, 필요하면 같은 이미지 안에서 커맨드만 바꿔 1회성으로 실행한다).

- **베이스 이미지**: `ghcr.io/astral-sh/uv:python3.12-bookworm-slim` - uv가 이미
  설치돼 있어 별도로 `pip install uv`할 필요가 없다. 이 프로젝트는 pip/venv 대신
  uv만 쓰기로 했으므로(코딩 컨벤션 참고) 컨테이너 안에서도 동일하게 `uv sync`/
  `uv run`으로 의존성을 관리한다.
- **레이어 캐싱**: `pyproject.toml`/`uv.lock`만 먼저 COPY해서 `uv sync --locked
  --no-install-project`를 한 번 돌리고, 그 다음에야 나머지 소스를 COPY한다 -
  소스 코드만 바뀐 재빌드에서는 의존성 설치 레이어가 캐시돼 재사용된다.
  `--locked`는 `uv.lock`이 `pyproject.toml`과 어긋나 있으면 빌드를 실패시켜서,
  로컬과 다른 버전이 컨테이너에 들어가는 걸 막아준다.
- **SQLite 영속성**: 컨테이너를 재생성(재빌드, `docker compose down/up`)해도
  `app.db`가 사라지면 안 되므로, `db.py`의 `DB_PATH`를 `os.environ.get("DB_PATH",
  "app.db")`로 바꿔 환경변수로 오버라이드 가능하게 했다. `docker-compose.yml`은
  `app-data`라는 이름의 볼륨을 `/app/data`에 마운트하고 `DB_PATH=/app/data/app.db`를
  주입한다 - 로컬 실행(`uv run uvicorn ...`)에서는 이 환경변수가 없으니 그대로
  `app.db`(프로젝트 루트)를 쓴다.
- **비밀값**: `.env`는 이미지에 절대 COPY하지 않는다(`.dockerignore`에 명시) -
  `docker-compose.yml`의 `env_file: .env`로 실행 시점에만 컨테이너 환경변수로
  주입한다. `server.py`의 `load_dotenv()`는 `.env` 파일이 없어도 에러 없이
  그냥 넘어가므로, 이미 주입된 환경변수를 덮어쓰지 않고 그대로 쓴다.
- **포트/카카오 Redirect URI**: 호스트:컨테이너 포트 매핑을 8000:8000으로 맞춰서,
  로컬에서 `uv run uvicorn`으로 띄웠을 때와 접속 주소(`http://localhost:8000`)가
  동일하다 - 카카오 개발자 콘솔의 Redirect URI를 Docker용으로 새로 등록할 필요 없음.

## MCP 서버

`collector.py`의 논문 검색/조회 로직(`fetch_top_daily_papers`, `filter_by_keywords`)을
`mcp_server.py`로 노출했다. 목적은 프로젝트 목적 섹션에 적어둔 스택 도입 이유 그대로 -
Docker(배포 자동화) 다음 문제인 **"재사용 가능한 도구화"**: 지금은 이 논문 검색
기능이 `server.py`가 import해서 쓰는 파이썬 함수로만 존재하는데, MCP로 감싸두면
Claude Desktop 같은 임의의 MCP 클라이언트나 로드맵 5번(LangGraph)의 Collector
노드가 파이썬 모듈을 직접 import하지 않고도 표준 프로토콜로 호출할 수 있다.

**중요한 설계 판단 - `server.py`는 그대로 collector.py를 직접 호출한다.** MCP 서버는
`server.py`를 대체하는 게 아니라, "이 앱 바깥"에서 논문 검색 기능을 재사용하기 위한
**별도의 진입점**이다. 같은 프로세스 안에서 이뤄지는 호출(웹 서비스의 `/api/send-now`)까지
프로토콜 왕복으로 바꿀 이유가 없어서, `_clusters_from_keyword_groups()` 기반의
멀티클러스터 우선순위 랭킹 로직은 그대로 `server.py`/`collector.py`에 남겨뒀다.

**패키지**: `mcp[cli]` (공식 MCP Python SDK, `uv add "mcp[cli]"`로 설치). 이 SDK는
버전에 따라 공개 API가 크게 바뀌므로 주의할 것 - `mcp==2.0.0` 기준으로는 이전에
흔히 알려진 `from mcp.server.fastmcp import FastMCP`가 **더 이상 존재하지 않고**,
`from mcp.server.mcpserver import MCPServer`로 이름과 경로가 바뀌었다 (클래스 이름
자체가 `FastMCP` → `MCPServer`). 새 세션에서 이 코드를 보고 옛날 이름으로 되돌리려
하지 말 것 - 설치된 버전을 `python -c "import mcp.server; help(...)"`로 직접 확인하고
맞춰야 한다.

**노출한 도구 2개** (둘 다 `collector.py` 함수를 얇게 감싼 것 - 새 로직을 만들지 않음):
```python
list_daily_papers(date: str | None = None, top_n: int = 30) -> list[dict]
# fetch_top_daily_papers()를 그대로 노출. 키워드 필터 없이 "오늘 뭐가 화제인지" 훑어볼 때.

search_papers(keyword_groups: list[list[str]], date: str | None = None, top_n: int = 30) -> list[dict]
# filter_by_keywords()를 감쌈. keyword_groups는 "그룹의 리스트"로, 그룹 사이는 AND,
# 그룹 안 키워드끼리는 OR - collector.py의 클러스터 매칭 규칙(_matches_cluster)을
# 그대로 일반화한 것이다. 그룹 하나만 넘기면 기존 클러스터의 평범한 OR 리스트와
# 동일하고, 그룹 두 개를 넘기면 KEYWORD_CLUSTERS의 time_series처럼 AND 조건이 된다.
# seen_ids는 명시적으로 빈 집합을 넘긴다 - 안 그러면 filter_by_keywords의 기본값이
# 개인용 스크립트의 seen_papers.json 파일을 읽어버려서, 이 범용 검색 도구의 결과가
# 이 서버를 실행하는 로컬 머신의 개인 발송 이력에 은근슬쩍 좌우되게 된다.
```

**실행 방법:**
```bash
uv run mcp dev mcp_server.py      # MCP Inspector(웹 UI)로 도구 직접 테스트
uv run python mcp_server.py       # stdio 서버로 실행 (Claude Desktop 등 클라이언트가 이 커맨드로 subprocess 실행)
```

**검증 방법**: Claude Desktop 없이도, `mcp.client.stdio.stdio_client` +
`mcp.client.session.ClientSession`으로 실제 stdio 프로토콜을 통해 도구를 호출하는
테스트 스크립트를 스크래치패드에 작성해서 확인했다 (`session.call_tool(...)`의
결과는 `.content`가 아니라 `.structured_content["result"]`에 파싱된 리스트가 들어
있음 - `.content`의 텍스트 블록은 별도로 문자열화된 표현이라 이중 디코딩하면
문자열을 문자 단위로 순회하게 되는 함정이 있었음). `search_papers`에 그룹을
하나(OR)/둘(AND)로 각각 호출해 교집합 개수가 실제로 줄어드는 것까지 확인함.

## LangGraph 파이프라인

`pipeline_graph.py`에 Collector/Filter/Summarizer를 LangGraph의 `StateGraph` 노드로
그래프화했다. 기존에는 `main.py`/`server.py`가 `collect_papers()`(collector+filter가
이미 합쳐진 함수) -> `summarize_papers()`를 순서대로 그냥 파이썬 함수 호출로
이어붙였는데, 이제는 세 단계를 명시적인 그래프 노드(`collector` -> `filter` ->
`summarizer`, 지금은 선형)로 표현한다. 실질 동작은 바뀌지 않지만, 다음 단계들
(로드맵 6번 RAGAS 품질 평가 노드 추가, 요약 실패 시 재시도/분기 등)을 그래프에
자연스럽게 끼워 넣을 수 있는 구조를 미리 만들어두는 것이 목적 - 로드맵 인트로에서
말한 "멀티에이전트 오케스트레이션" 문제를 해결하는 단계.

**MCP 서버(4번)와의 관계 - 여기서도 같은 판단을 반복했다.** `pipeline_graph.py`의
`collector_node`/`filter_node`는 `mcp_server.py`의 도구를 호출하지 않고
`collector.py`를 그대로 import해서 쓴다. 같은 프로세스 안에서 도는 파이프라인을
굳이 MCP 프로토콜 왕복으로 바꿀 이유가 없기 때문 - MCP 서버는 "이 앱 바깥"에서
재사용하기 위한 별도 진입점이라는 4번 섹션의 설계 판단을 그대로 따른 것이다.

**State 스키마** (`TypedDict`, `pipeline_graph.PipelineState`):
```python
target_date: str | None       # 입력 - 없으면 어제 날짜
top_n: int                    # 입력 - HF Daily Papers 상위 몇 개를 볼지
clusters: dict | None         # 입력 - collector.py의 클러스터 형식 (None이면 KEYWORD_CLUSTERS 기본값)
seen_ids: set | None           # 입력 - 이미 보낸 논문 hf_id 집합
papers_per_send: int           # 입력 - 필터 통과 논문 중 몇 편을 요약/발송할지
raw_papers: list[dict]         # collector 노드 출력
filtered_papers: list[dict]    # filter 노드 출력 (matched_clusters 포함, 랭킹 정렬됨)
summarized_papers: list[dict]  # summarizer 노드 출력 (summary 필드 추가) - 최종 결과물
```

`run_pipeline(target_date, top_n, clusters, seen_ids, papers_per_send)`이 그래프를
`invoke()`하고 최종 state 전체를 그대로 반환한다 - 최종 결과물은
`result["summarized_papers"]`지만, `result["filtered_papers"]`(개수/매칭 클러스터)도
그대로 남아있어 `main.py`가 콘솔 로그에 그대로 활용한다. `summarizer_node`는
필터 통과 논문이 0편이면 Gemini 클라이언트를 만들 필요도 없이 바로 빈 리스트를
반환한다 (불필요한 API 호출/키 검증 방지).

`main.py`와 `server.py`의 `/api/send-now`는 각각 `collect_papers()`+
`summarize_papers()`를 직접 이어붙이던 자리를 `run_pipeline()` 호출 하나로
대체했다 - 개인용 스크립트/웹 서비스 양쪽 다 동일한 그래프를 재사용한다.

**검증**: `papers_per_send=0`으로 그래프 연결(collector -> filter까지만 실행되고
summarizer가 조기 종료되는지)을 먼저 확인하고, `papers_per_send=1`로 실제 Gemini
API까지 호출되는 종단간 테스트를 1건만 돌려 무료 티어 할당량을 아끼면서 확인했다.
Docker 이미지도 `langgraph` 의존성 포함해서 재빌드 후 컨테이너 기동까지 확인함.

## 요약 품질 평가 (evaluator.py)

**ragas 패키지를 포기한 이유 (중요 - 다시 시도하지 말 것):** 로드맵 6번은 원래
"RAGAS로 요약 품질 평가 하네스 구축"이었지만, 실제로 시도해보니 두 가지 이유로
포기하고 직접 구현했다.

1. **ragas 패키지 자체가 langgraph와 같은 환경에 설치 불가능한 버그가 있음.**
   `ragas`(0.4.3, 0.3.9 둘 다 확인)는 `ragas/llms/base.py`에서 무조건
   `from langchain_community.chat_models.vertexai import ChatVertexAI`를
   import하는데, 이 서브모듈이 최신 `langchain-community`(sunset되면서 개별
   통합 패키지로 이전 중)에는 더 이상 없다 - ragas가 `langchain-community`
   버전을 제대로 고정해두지 않은 ragas 쪽의 실제 패키징 버그다. 우회하려고
   `langchain-community`를 예전 버전(0.3.19)으로 고정해봤지만, 그 버전은
   `langchain-core<1.0.0`을 요구하는 반면 우리가 로드맵 5번에서 이미 설치한
   `langgraph==1.2.10`은 `langchain-core>=1.4.7`을 요구해서 **uv 리졸버가 명확히
   "동시에 만족 불가능"이라고 실패**했다. 즉 지금 이 프로젝트에서는 ragas와
   langgraph를 같은 가상환경에 공존시킬 방법이 없다 (별도 가상환경으로 완전히
   격리하면 가능하지만, 운영 부담 대비 이득이 크지 않다고 판단해 보류).
2. **애초에 RAGAS의 핵심 지표가 이 파이프라인에 잘 안 맞음.** RAGAS는
   "질문 -> 검색된 문서 -> 답변" 구조의 RAG 시스템을 겨냥한 지표(Context
   Precision/Recall 등)가 중심인데, 이 파이프라인은 Collector(upvotes 정렬) ->
   Filter(규칙 기반 키워드 매칭) -> Summarizer(요약)라 "검색" 단계가 없다.
   평가가 실제로 의미 있는 단계는 Summarizer 하나뿐이다 (Collector/Filter는
   결정론적 로직이라 애초에 "품질"을 평가할 대상이 아님).

**그래서 한 것**: `evaluator.py`에 Gemini 자신을 심사자(LLM-as-judge)로 쓰는
자체 채점 로직을 직접 구현했다 (keyword_chat.py와 같은 function calling 패턴
재사용). 채점 기준 3가지:
- `faithful`: 요약이 초록에 없는 내용(수치/방법론/결과)을 지어내지 않았는가 - Gemini 판단
- `relevant`: 요약이 논문의 핵심 아이디어/기여를 담고 있는가 - Gemini 판단
- `concise`: `summarizer.py`가 지시하는 150자 제약을 지켰는가 - LLM 호출 없이
  `len(summary)`로 바로 계산 (결정론적이라 굳이 LLM에 물어볼 필요 없음)

`evaluate_summaries(papers)`가 각 논문에 `judgment` 필드를 붙여 반환하고,
`summarize_evaluation(results)`가 `faithful_rate`/`relevant_rate`/`concise_rate`로
종합한다. `uv run python evaluator.py`로 실행하면 `pipeline_graph.run_pipeline()`을
조금만(기본 3편) 돌려서 채점 리포트를 콘솔에 출력한다 - Gemini 무료 티어
할당량(20건/일)이 빠듯해서, 요약 1건당 채점도 1건씩 추가로 드니 샘플 크기를
일부러 작게 유지한다.

**검증**: 파이프라인을 통해서가 아니라, 충실한 요약 하나 + 초록에 없는 내용(양자
컴퓨팅, 100배 속도, 99.9% 정확도)을 지어낸 요약 하나를 직접 만들어서
`evaluate_summaries()`에 넣어봤다 - 충실한 쪽은 `faithful=True`, 지어낸 쪽은
`faithful=False`로 정확히 구분해내는 것을 확인했다 (이 판별력 테스트가 실제
파이프라인을 돌려보는 것보다 하네스가 제대로 작동하는지 더 직접적으로 검증해준다).

## Agent System 고도화: 직무 갭 분석 에이전트 (로드맵 11)

> 상태: 설계 확정 (구현 전). 아래 "확정" 표시는 사용자 결정, "초안" 표시는 구현 시
> 검증하며 조정할 설계 판단이다.

### 목적과 위치

서비스 타겟에 **AI 직무를 준비하는 사용자**를 추가한다. 희망 직무의 채용공고가 요구하는
스킬과 사용자의 보유 스킬(+ 사용 증거의 신뢰도)을 비교해 **보완할 스킬**을 찾고, 그 스킬을
**기존 논문 알리미의 관심 키워드 그룹으로 연결**한다.

- 기존 논문 알리미(수집 -> 요약 -> 발송, `pipeline_graph.py`)는 **변경하지 않는다**.
  이 에이전트는 "키워드를 정하는 새로운 경로"일 뿐이고, 출력은 기존 `POST /api/keyword-groups`로
  흘러 들어간다.
- 이 기능을 도입하는 이유: 지금까지의 LangGraph 파이프라인은 선형이라 Planning이 필요 없었다.
  이 기능은 (1) 멀티턴 대화로 상태를 쌓고, (2) 사용자의 한마디에 따라 이전 단계로 되돌아가고,
  (3) 외부 데이터(공고 DB)를 도구로 검색하는 문제라서 Planning / Memory / Tool-Use가
  실제로 필요하다.
- `pipeline_graph.py`(논문 파이프라인)와 **파일을 분리**한다. 그래프도, State도 따로 둔다.

### 기능의 위치 (확정: 위임받아 결정)

**전용 페이지 `/career` + 홈 세 번째 진입점 + 마이페이지 "내 커리어 프로필" 섹션.**

- 기존 `_chat_modal.html`에 넣지 않는다. 그 모달은 "무상태 + 단일 목적(키워드 그룹 제안)"으로
  설계됐고, 이 에이전트는 서버 측 상태(확정 프로필, 후보 공고, 갭 목록)와 3단계 진행 표시가 필요해서
  모달에 얹으면 양쪽 다 복잡해진다.
- 홈 화면: 기존 "관심 키워드 등록" / "AI 기반 관심 키워드 찾기" 옆에 세 번째 버튼
  "내 직무 갭 분석"을 추가한다. (로드맵 후순위인 "핫한 논문 알리미"와는 별개 기능이다.)
- `/career` 레이아웃: 좌측 채팅, 우측 사이드 패널(진행 단계 ①②③, 확정된 프로필 카드,
  갭 결과 카드).
- 마이페이지: 직무, 보유 스킬(신뢰도 배지 포함)을 조회/수정/삭제하고, 커리어 데이터를
  통째로 삭제하는 버튼을 둔다.
- 최종 출력(갭 스킬 -> 키워드 그룹 등록)은 **기존 등록 확인 팝업을 재사용**한다
  (`_chat_modal.html`의 확인 팝업 + 페이지별 `onGroupRegistered(group)` 훅 패턴 그대로).

### 확정 결정 사항

| # | 결정 | 내용 |
|---|---|---|
| 1 | 이력서 업로드는 **선택** (확정) | 대화만으로도, 업로드로도 시작 가능. 두 경로 모두 같은 `profile` state로 수렴 |
| 2 | 스킬은 **사용 증거로 신뢰도**를 매긴다 (확정) | 보유한다고 말한 스킬마다 "프로젝트에서 어떻게 썼는지"를 질문해 증거 슬롯을 채우고, 신뢰도를 계산 |
| 3 | 기능 위치 (확정, 위 참고) | 전용 페이지 `/career` |

### 전체 흐름

```
Planner(Supervisor) -- state를 보고 다음 노드 결정, 되돌아가기 라우팅
  ① 상황 파악  : 희망직무 확정 -> 보유 스킬 수집 -> 증거(신뢰도) 질문 -> 프로필 확정
  ② 공고 검색  : 직무/경력 메타데이터 필터 + 벡터 검색 -> 후보 공고 상위 N개
  ③ 갭 분석    : 요구 스킬 집계 vs 보유 스킬(신뢰도 반영) -> 갭 목록, 사용자와 보정
  출력        : 갭 스킬 -> (concept 종류만) 영어 논문 키워드 -> 기존 키워드 그룹 등록
```

### State 스키마 (초안, `career_agent.CareerState`)

```python
messages: list                  # 대화 기록 (체크포인터가 보관)
profile: {
    "target_roles": list[str],  # 확정된 희망 직무 (공고 DB의 role_category 값)
    "experience_years": float | None,
    "skills": list[{            # 아래 "스킬 증거와 신뢰도" 참고
        "skill": str, "project": str|None, "role": str|None,
        "how": str|None, "outcome": str|None,
        "confidence": "low"|"medium"|"high",
        "origin": "chat"|"resume", "verified": bool,
    }],
}
profile_confirmed: bool
candidate_jobs: list[int]       # job_postings.id
candidate_jobs_stale: bool      # 직무/프로필이 바뀌면 True -> ② 재실행 필요
gaps: list[{"skill": str, "gap_score": float, "kind": str, "reason": str}]
gaps_stale: bool                # 프로필이 바뀌면 True -> ③ 재계산 필요
gaps_confirmed: bool
retry_count: int                # 같은 단계로 되돌아간 횟수 (무한 루프 방지)
```

### Planner 라우팅 (확정 원칙 + 초안 임계값)

**원칙: 이동 결정은 코드(규칙)가 하고, LLM은 사용자 발화 해석에만 쓴다.** 규칙이
결정하면 테스트가 쉽고(궤적 평가 가능), 무료 티어 호출도 아낀다.

- **별도의 의도 분류 LLM 호출을 하지 않는다.** 활성 에이전트가 function calling으로
  `change_target_roles` / `upsert_skill` / `confirm_profile` 같은 도구를 부르면, 그 도구가
  state(stale 플래그 포함)를 바꾸고, Planner는 바뀐 state만 보고 라우팅한다.

```python
def route(state):
    if state["retry_count"] >= 2:
        return "ask_user"                  # 같은 단계 반복 -> 사용자에게 직접 묻기
    if not state["profile_confirmed"]:
        return "profile_agent"             # ①
    if state["candidate_jobs_stale"]:
        return "job_search"                # ② (직무 변경 / 필터 완화 후 재검색)
    if len(state["candidate_jobs"]) < MIN_JOBS:          # 초안: 3
        return "relax_or_back_to_profile"  # 필터 완화 1회, 그래도 부족하면 ①로
    if state["gaps_stale"]:
        return "gap_analysis"              # ③ (프로필 변경 후 재계산)
    if not state["gaps_confirmed"]:
        return "gap_analysis"              # ③ 사용자와 보정 대화
    return "done"
```

**되돌아가기 시나리오 4개 (그대로 평가용 테스트 케이스가 된다):**

| # | 상황 | 신호 | 이동 |
|---|---|---|---|
| 1 | ②에서 후보 공고가 거의 안 나옴 | `len(candidate_jobs) < MIN_JOBS` | 필터 완화 후 ② 재시도, 그래도 부족하면 **①로 복귀**(인접 직무 제안) |
| 2 | ③에서 사용자가 직무를 바꿈 | `change_target_roles` 호출 -> `candidate_jobs_stale=True` | **②로 복귀** |
| 3 | ③의 갭이 흐릿함 | 상위 3개 `gap_score` 평균 < 0.15 (초안), 후보 공고에 서로 다른 직무가 섞임 | **②로 복귀** (직무 필터를 좁혀 재검색) |
| 4 | ③에서 사용자가 새 정보를 줌 | `upsert_skill` 호출 -> `gaps_stale=True` | ①로 가지 않고 **프로필만 갱신 후 ③ 재계산** |

원칙: (1) 가장 얕은 곳으로 돌아간다, (2) 상위 단계가 바뀌면 하위 산출물을 stale로 표시해
낡은 값이 노출되지 않게 한다, (3) 같은 단계로 2번 넘게 돌아가면 사용자에게 묻는다.

### ① 상황 파악 에이전트

1. **희망 직무를 먼저 확정한다.** 자유 입력을 그대로 필터에 쓰지 않고, **공고 DB에서 뽑은
   직무 카테고리(`role_category`)를 선택지로 제시**한다 (대화형으로 좁히되 필터 정확도 확보).
   기존 키워드 챗의 "제안 -> 사용자 확정" 패턴과 같다.
2. 직무가 정해지면 `get_top_required_skills(role)`로 그 직무 공고의 요구 빈도 상위 스킬을
   조회해, 사용자가 이 스킬들을 얼마나 아는지 묻는다.
3. **증거 질문 (확정 #2)**: 사용자가 "있다"고 한 스킬마다 프로젝트에서 어떻게 썼는지 묻는다.
   과도한 심문을 막는 정책(초안): 요구 빈도 상위 스킬 중 보유를 주장한 것만, 최대 5개,
   스킬당 최대 2턴, 사용자는 "건너뛰기" 가능 (건너뛰면 해당 스킬은 `low`로 저장).
4. 프로필이 모이면 `propose_profile`로 확정 카드를 제시하고, 사용자 승인 후 `profile_confirmed=True`.

### 스킬 증거와 신뢰도 (확정 #2)

각 스킬에 **증거 슬롯 4개**를 둔다. LLM은 대화에서 슬롯을 **추출**만 하고, 신뢰도는
**채워진 슬롯 수로 규칙이 계산**한다 (재현 가능하고 테스트 가능).

| 슬롯 | 질문 의도 |
|---|---|
| `project` | 어떤 프로젝트/맥락에서 썼는가 |
| `role` | 본인이 맡은 부분은 무엇인가 |
| `how` | 구체적으로 어떻게 구현/사용했는가 |
| `outcome` | 결과, 수치, 배운 점은 무엇인가 |

- 채워진 슬롯 3~4개 -> `high`, 2개 -> `medium`, 0~1개 -> `low`
- 갭 계산에서 신뢰도를 **보유 크레딧**으로 반영 (초안 값, `config`로 분리해 튜닝):
  `high=1.0`, `medium=0.6`, `low=0.3`, 미보유 `0`
- 갭 결과는 두 종류로 나눠 보여준다: **미보유 스킬**(보완 필요)과 **증거 부족 스킬**
  (`low`/`medium`: 사용 경험을 더 구체화할 필요).

### ② 공고 검색 에이전트

- 입력: `profile.target_roles`, 경력 연차 -> 메타데이터 필터(직무/경력/마감 여부) + 벡터 검색
  -> 후보 공고 상위 N개 (기본 30, 초안).
- 결과가 `MIN_JOBS` 미만이면 규칙에 따라 필터 완화 -> 재시도 (시나리오 1).
- 상위 K개는 `get_job_detail`로 **마감 여부를 재확인**한 뒤 후보로 확정한다.

### ③ 갭 분석 에이전트

- **LLM 없이 집계로 계산한다** (공고 구조화는 수집 시점에 끝나 있으므로).
```
demand(skill) = (필수로 요구한 공고 수 + 0.5 * 우대로 요구한 공고 수) / 후보 공고 수
gap_score(skill) = demand(skill) * (1 - credit(skill))
```
- 사용자에게 갭 목록을 제시하고 대화로 보정받는다 ("이건 이미 있어요" -> `upsert_skill`,
  "관심 없어요" -> 목록에서 제외). 보정 결과는 장기 메모리에 반영된다.
- **논문 연결**: `kind='concept'`인 갭 스킬만 논문 키워드로 변환한다 (예: RAG, 멀티에이전트).
  `kind='tool'`/`'language'`(Docker, AWS, SQL 등)은 갭 목록에는 표시하되 논문 연결 버튼은 없다
  - 도구류는 논문 키워드로 의미가 없다.
- 논문 키워드는 **영어**여야 한다 (`keyword_chat.py`와 같은 규칙 - 논문 원문이 영어).
  `skill_aliases.paper_keywords`에 사전으로 두고, 없는 스킬만 LLM 1회 배치 호출로 보완한다.

### Tool 목록 (초안)

| 도구 | 쓰는 곳 | LLM 사용 | 비고 |
|---|---|---|---|
| `ask_user` | ①③ | - | LangGraph `interrupt`로 사용자 입력 대기 |
| `list_role_categories()` | ① | X | 공고 DB의 직무 카테고리 |
| `get_top_required_skills(role, top_k)` | ① | X | 증거 질문 대상 선정 |
| `upsert_skill(skill, project, role, how, outcome)` | ①③ | X | 슬롯 저장 + 신뢰도 계산 + `gaps_stale=True` |
| `change_target_roles(roles)` | ①③ | X | `candidate_jobs_stale=True`, `gaps_stale=True` |
| `propose_profile` / `confirm_profile` | ① | X | 확정 카드 제안 / 승인 |
| `search_jobs(roles, exp, top_k)` | ② | X | 메타 필터 + 벡터 검색 |
| `get_job_detail(job_id)` | ② | X | 마감 재확인 겸용 |
| `compute_gap(profile, job_ids)` | ③ | X | 위 공식, 순수 함수 |
| `propose_gaps` | ③ | X | 갭 카드 제안 |
| `create_keyword_group` | 출력 | X | 기존 `POST /api/keyword-groups` 재사용 |
| `parse_resume(file)` | ① (선택) | O | 이력서 경로, 아래 참고 |

도구 대부분이 LLM을 쓰지 않는 결정론적 함수다. LLM은 대화(질문/요약)와 슬롯 추출,
이력서 파싱에만 쓴다.

### 이력서 경로 (확정 #1: 선택 사항)

- **경로 A (대화만)**: 위 ① 그대로.
- **경로 B (이력서 업로드)**: 업로드 -> 텍스트 추출 -> LLM으로 스킬/경험 후보 추출 -> 사용자에게
  후보 목록을 보여주고 확인/수정 -> 이후는 경로 A와 같이 **증거 질문으로 신뢰도를 보강**한다.
  이력서에서 뽑은 스킬은 `origin='resume'`, 사용자가 확인하기 전까지 `verified=False`이고
  신뢰도는 증거 슬롯이 채워진 만큼만 오른다 (이력서에 적혀 있다는 사실만으로 `high`가 되지 않음).
- **개인정보 처리 (확정 원칙)**:
  - 이력서 원문은 **저장하지 않는다.** 메모리에서만 처리하고 폐기하며, 추출 결과만 저장한다.
  - 지원 형식 `pdf`/`docx`/`txt`, 용량 상한 5MB (초안). 스캔본 PDF는 OCR 미지원이라 안내만 한다.
  - LLM 호출 전에 이메일/전화번호/주소는 정규식으로 마스킹한다 (best-effort).
  - 업로드 화면에 "이력서 내용이 외부 LLM API로 전송된다"는 고지를 표시한다.
  - 사용자가 마이페이지에서 자신의 커리어 데이터를 언제든 삭제할 수 있어야 한다.

### Memory

- **단기**: LangGraph state + 체크포인터(SQLite, `thread_id` 단위). 세션 TTL을 둬서
  마지막 활동 후 24시간(초안)이 지나면 정리한다 - 체크포인트가 무한히 쌓이지 않게 한다.
- **장기**: `user_career_profiles` / `user_skills`. 사용자가 확정한 직무/스킬, 그리고 갭 보정
  결과(제외한 스킬 등)가 다음 세션에서도 이어진다.
- 공고 DB는 메모리가 아니라 **검색 대상 지식(retrieval)** 이다.

### 데이터 레이어: 공고 DB (초안)

- **소스**: 사람인 채용정보 API, 워크넷 채용정보 API (공식 API만 사용, 크롤링 안 함).
  사람인은 제공 출처 표기가 의무이므로 UI에 출처를 표기한다. 공고 원문 전체를 복제 저장하지
  않고 필요한 필드 + 원본 `url`만 저장한다.
- **수집 배치**: `jobs_ingest.py` (`uv run python jobs_ingest.py`), 하루 1~2회. 공고 ID로 upsert,
  마감된 공고는 `is_active=0`. 스케줄링은 로드맵 7번(EventBridge)에서 붙이고, 그 전에는 수동 실행.
- **구조화 추출 (중요한 제약 반영)**: Gemini 무료 티어 호출 한도(이 문서의 "요약 품질 평가"
  섹션에 기록된 20건/일)로는 공고마다 LLM을 부를 수 없다. 따라서
  1) **`skill_aliases` 사전 기반 규칙 추출을 기본**으로 하고 (본문에서 별칭 매칭 -> canonical),
  2) LLM은 규칙이 못 잡은 모호한 공고에만 보강으로 쓰되 **일일 상한**을 둔다
  (`extraction_method` 컬럼으로 어느 방식이었는지 기록).
- **스킬 정규화**: `skill_aliases`(예: "LangChain"/"랭체인"/"랭체인" -> `langchain`)가 필수다.
  이게 없으면 같은 스킬이 쪼개져서 집계가 틀어진다. 한국어/영어/약어 별칭을 함께 관리한다.
- **임베딩/벡터 저장소 (초안, 구현 시 선택)**: 규모(수천 건)상 별도 서버가 필요 없는 **임베디드**
  방식으로 시작한다 (`sqlite-vec` 또는 `chromadb`). 임베딩은 호출 한도를 피하기 위해
  **로컬 경량 모델**(`fastembed` 등)을 우선 검토한다. 의존성은 추가하기 전에 `uv` 리졸버가
  `langgraph`와 충돌 없이 풀리는지 먼저 확인한다 (ragas 때 겪은 충돌 재발 방지 - 위
  "요약 품질 평가" 섹션 참고). 인덱스 파일은 Docker 볼륨(`app-data`)에 영속시킨다.

### DB 스키마 추가 (SQLite, 초안)

```sql
CREATE TABLE job_postings (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL CHECK (source IN ('saramin', 'worknet')),
    source_job_id TEXT NOT NULL,
    title TEXT NOT NULL,
    company TEXT,
    role_category TEXT,
    experience_min INTEGER,
    experience_max INTEGER,
    location TEXT,
    deadline TEXT,
    url TEXT NOT NULL,
    required_skills TEXT NOT NULL DEFAULT '[]',   -- JSON, canonical 스킬명
    preferred_skills TEXT NOT NULL DEFAULT '[]',  -- JSON
    extraction_method TEXT CHECK (extraction_method IN ('rule', 'llm')),
    is_active INTEGER NOT NULL DEFAULT 1,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, source_job_id)
);

CREATE TABLE skill_aliases (
    alias TEXT PRIMARY KEY,
    canonical TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('concept', 'tool', 'language')),
    paper_keywords TEXT                           -- JSON, 영어 논문 키워드 (concept만)
);

CREATE TABLE user_career_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    target_roles TEXT NOT NULL DEFAULT '[]',      -- JSON
    experience_years REAL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE user_skills (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    skill TEXT NOT NULL,                          -- canonical
    project TEXT,
    role TEXT,
    how TEXT,
    outcome TEXT,
    confidence TEXT NOT NULL CHECK (confidence IN ('low', 'medium', 'high')),
    origin TEXT NOT NULL CHECK (origin IN ('chat', 'resume')),
    verified INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, skill)
);
```

**기존 스키마 변경 (주의)**: 갭 결과로 등록하는 키워드 그룹은 `keyword_groups.source`에
`'career_gap'`을 추가해 출처를 구분한다. 그런데 이 컬럼은 `CHECK (source IN ('manual',
'llm_chat'))`이고 **SQLite는 `ALTER`로 CHECK 제약을 바꿀 수 없다** - `db.py`의 `_migrate()`가
쓰던 `ADD COLUMN` 패턴으로는 안 되고, 테이블 재생성(새 테이블 생성 -> 데이터 복사 -> 교체)
마이그레이션이 필요하다. 비용이 부담되면 `'llm_chat'`을 재사용하는 대안도 있다 (마이페이지에서
출처 구분만 포기).

### API 엔드포인트 (초안, 모두 `require_login`)

```
POST   /api/career/chat                 # 대화 한 턴. body: {thread_id?, message}
                                        # 응답: {thread_id, reply, ui_events[], stage}
                                        # ui_events: profile_proposal | gap_result 등 프론트 카드 지시
POST   /api/career/resume               # 이력서 업로드(multipart, thread_id 포함). 원문은 저장하지 않고,
                                        # 추출된 후보 스킬을 해당 thread state에 unverified로 넣는다
GET    /api/career/profile              # 마이페이지용 직무/스킬 조회
PATCH  /api/career/skills/{skill_id}    # 스킬 증거 슬롯 수정 (신뢰도 재계산)
DELETE /api/career/skills/{skill_id}    # 스킬 하나 삭제
DELETE /api/career/profile              # 내 커리어 데이터 전체 삭제 (프로필 + 스킬 + 체크포인트)
```

갭 -> 키워드 그룹 등록은 새 엔드포인트 없이 기존 `POST /api/keyword-groups`
(`source="career_gap"`)를 그대로 쓴다. 모든 사용자 데이터 접근은 기존 패턴대로 SQL의
`WHERE user_id = ?`로 소유권을 확인한다.

### 파일 구성 (초안)

- `career_agent.py`: LangGraph 그래프 (Planner + 3개 노드), `CareerState`, 라우팅 함수
- `career_tools.py`: 위 도구 함수들 (순수 함수 위주, LLM 호출 최소화)
- `jobs_ingest.py`: 공고 수집/구조화/임베딩 배치
- `skill_normalizer.py`: 별칭 사전 로드/정규화
- `career_eval.py`: 평가 하네스
- `mcp_server.py`: `search_jobs`, `get_job_detail`을 도구로 **추가 노출**한다.
  4번 섹션의 설계 판단을 그대로 따른다 - `career_agent.py`는 `career_tools.py`를 직접 호출하고
  (같은 프로세스에서 프로토콜 왕복을 하지 않음), MCP는 앱 바깥 재사용용 별도 진입점이다.
- `templates/career.html` + `_career_*.html` partial, 마이페이지 섹션

### 평가 하네스 (`career_eval.py`)

ragas는 쓰지 않는다 (위 "요약 품질 평가" 섹션의 결정 유지). `evaluator.py`처럼 직접 구현하고,
LLM 심사 호출은 무료 티어 한도 때문에 최소화한다. 결정론적으로 검증할 수 있는 것을 우선한다.

| 대상 | 측정 | 방법 |
|---|---|---|
| 스킬 정규화 | 별칭 매핑 정확도 | 손으로 만든 정답 사전 |
| ① 슬롯 추출/신뢰도 | 슬롯 추출 정확도, 신뢰도 규칙 | 정답 라벨 대화 소규모 세트 + 규칙은 단위 테스트 |
| ② 공고 검색 | precision@k | 라벨된 (프로필, 관련 공고) 쌍 |
| ③ 갭 | 갭 상위 k 일치도 | 라벨된 기대 갭 목록 대비 |
| 전체 | **궤적 평가** | 위 "되돌아가기 시나리오 4개"를 (입력 대화 -> 기대 라우팅 경로)로 테스트. 라우팅이 규칙이라 LLM 없이도 재현 가능 |

LLM은 mock으로 대체해 라우팅/집계 로직을 먼저 검증하고, 실제 Gemini 호출 테스트는 소수만 돌린다.

### 구현 순서 (이 순서로 진행)

1. [ ] A-1 공고 수집/구조화/스킬 정규화 + DB 스키마 (`jobs_ingest.py`, `skill_aliases`)
2. [ ] A-2 공고 검색 도구 + 벡터 인덱스 (`search_jobs`, `get_job_detail`)
3. [ ] A-3 ① 상황 파악 에이전트: 직무 확정 + 스킬 수집 + 증거 슬롯/신뢰도 (대화 경로만)
4. [ ] A-4 ③ 갭 분석: `compute_gap` 순수 함수 + 갭 카드
5. [ ] A-5 Planner 라우팅 + 되돌아가기 시나리오 4개 + 체크포인터
6. [ ] A-6 `/career` 프론트 + 홈 진입점 + 마이페이지 섹션 + 키워드 그룹 연결(`career_gap`)
7. [ ] A-7 평가 하네스 (`career_eval.py`)
8. [ ] A-8 이력서 업로드 경로 (선택 기능이라 마지막)

### 선행 작업과 미결정 사항

- **사람인 API access-key, 워크넷 인증키 신청** (사용자가 직접). 승인에 시간이 걸릴 수 있으니
  승인 전에는 샘플/목 데이터로 A-1~A-5를 진행한다. 워크넷은 공공/중소기업 공고 비중이 커서
  AI 직무 공고 양을 먼저 확인하고, 소스별 비중을 정한다.
- 임베딩 모델과 벡터 저장소(`sqlite-vec` vs `chromadb`)는 A-2에서 의존성 호환을 확인하고 결정한다.
- 이력서를 외부 LLM API로 보내는 것과 관련해, **사용 중인 LLM의 무료 티어 데이터 사용 약관**을
  A-8 착수 전에 확인한다 (무료 티어는 입력이 서비스 개선에 쓰일 수 있는 경우가 있다).
- 갭 계산의 크레딧/임계값(`0.3/0.6/1.0`, `MIN_JOBS=3`, 평균 `0.15`)은 초안이며,
  평가 하네스로 측정하며 조정한다.

## 코딩/설계 컨벤션

- 패키지 관리: uv만 사용. `pip install`이나 `requirements.txt` 다시 만들지 말 것
- 인증/DB/세션은 라이브러리(Authlib, SessionMiddleware, SQLAlchemy 등)에 최대한 의존하고
  직접 구현을 최소화할 것 - 핵심 로직에 리소스를 집중하기 위함
- 카카오 발송: "나에게 보내기" API. 사용자별 refresh_token으로 access_token 자동 갱신 필수
- 각 단계 변경 시 커밋 단위를 기능 단위로 잘게 나눌 것 (예: `feat: 카카오 소셜 로그인 추가`)
- 비밀값(.env)은 절대 커밋하지 않음, `.env.example`만 레포에 유지

## 다음에 할 일

2-1~2-5, 3(Docker 컨테이너화), 4(MCP 서버 분리), 5(LangGraph 그래프화),
6(요약 품질 평가 - ragas 대신 evaluator.py 직접 구현)까지 완료됨. 다음은 로드맵
7번(AWS 배포 + 도메인 연결 + 스케줄링)부터 진행. 진행하기 전에 이 파일의 로드맵
체크리스트를 업데이트해서 어디까지 했는지 계속 반영할 것.