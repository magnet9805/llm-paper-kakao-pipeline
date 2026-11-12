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

## 현재 단계: 웹 서비스 전환 완료, "AI와 함께 읽기" 개발 시작

- 수집(collector.py) -> 요약(summarizer.py) -> 발송(kakao_sender.py)을
  main.py가 순서대로 실행하는 개인용 스크립트 버전은 완료됨
- 이 로직을 멀티유저 웹 서비스 구조로 리팩터링하는 작업(로드맵 2~6번)도 완료됨
- 지금은 로드맵 7번 "AI와 함께 읽기"(공용 논문 풀 + RAG/멀티에이전트 질의응답) 개발을 시작하는 단계
- 패키지 관리는 pip/venv가 아니라 **uv**를 사용 (`uv add`, `uv sync`, `uv run`)

## 웹 서비스 컨셉

로그인한 사용자가 자신의 관심 키워드를 설정하면, 그 키워드에 맞는 논문을
카카오톡으로 매일 받아보는 서비스. 홈페이지 구성:

- 로그인(카카오 소셜 로그인) / 내 정보(마이페이지)
- **관심 논문 알리미**
  - 관심 키워드 직접 입력
  - LLM과 대화하며 관심 키워드 찾기 (아래 상세 스펙 참고)

마이페이지에서는 사용자가 설정해둔 관심 키워드(그룹 단위)를 조회/관리할 수 있어야 함.

발송된 논문에는 **"AI와 함께 읽기"** 기능을 붙인다 - 사용자가 받은 논문에 대해 질문하면
본 논문 내용과 레퍼런스/공용 논문 풀을 근거로 답한다 (로드맵 7번, 아래 "AI와 함께 읽기" 섹션 참고).

## 개발 로드맵

1. [x] MVP: HF Daily Papers 수집 + 키워드 필터 + Gemini API(무료 티어) 요약 + 카카오 발송 (개인용 스크립트)
2. [ ] FastAPI + 카카오 소셜 로그인 + DB(SQLite)로 멀티유저 구조 전환
   - [x] 2-1. 카카오 소셜 로그인 (Authlib) - 회원가입/로그인 통합 (server.py, db.py)
   - [x] 2-2. 관심 키워드 "직접 입력" 플로우 (그룹 생성/수정/삭제 + 키워드 추가/삭제 API +
     마이페이지 조회/편집 UI) (`/api/keyword-groups` 전체 CRUD, `templates/` 프론트엔드 포함)
   - [x] 2-3. 기존 collector.py를 사용자별 키워드로 파라미터화해서 카카오 발송까지 연결
     (`POST /api/send-now` 수동 트리거, `sent_papers` 테이블로 사용자별 중복 방지,
     DB의 사용자별 kakao 토큰으로 발송 - 자동 스케줄링은 로드맵 8번에서 붙일 예정)
   - [x] 2-4. LLM 대화형 키워드 추출 (아래 스펙대로 구현, `keyword_chat.py` +
     `POST /api/keyword-chat` + `templates/_chat_modal.html`)
   - [x] 2-5. 홈 화면 진입점 분리 + 그룹별 발송 on/off (스펙에 없던 추가 개선,
     아래 "홈 화면 진입점"·"그룹별 발송 on/off" 섹션 참고)
3. [x] Docker 컨테이너화 (아래 "Docker 컨테이너화" 섹션 참고)
4. [x] 논문 검색/조회 로직을 MCP 서버로 분리 (아래 "MCP 서버" 섹션 참고)
5. [x] LangGraph로 Collector/Filter/Summarizer 노드 그래프화 (아래 "LangGraph 파이프라인" 섹션 참고)
6. [x] RAGAS로 요약 품질 평가 하네스 구축 (실제로는 ragas 패키지를 포기하고 직접
   구현 - 아래 "요약 품질 평가" 섹션 참고)
7. [ ] AI와 함께 읽기 - 공용 논문 풀 + RAG/멀티에이전트 질의응답 (아래 "AI와 함께 읽기" 섹션 참고)
   - [ ] 7-1. 공용 논문 풀 사전 적재 (Kaggle arXiv dump 중 OpenAlex에 있는 논문, 제목+초록+OpenAlex 키워드)
     + OpenAlex 키워드 기반 별칭 사전 구축
   - [ ] 7-2. 키워드 추가 시 풀 검색 + 결과가 적으면 보강 수집 (메타데이터 먼저 저장,
     임베딩은 대기열 -> 야간 일괄 처리)
   - [ ] 7-3. 발송 파이프라인을 "발송 결정(새벽)"과 "발송(아침)"으로 분리 + 발송 결정 시
     전문·레퍼런스 수집, 레퍼런스 중요도 계산, 브리핑 생성 (비동기)
   - [ ] 7-4. 논문 분석 에이전트 / RAG 에이전트 (섹션 청킹, 하이브리드 검색: 벡터 + BM25 + RRF)
   - [ ] 7-5. 라우터 + 통합 에이전트를 LangGraph로 연결 + "AI와 함께 읽기" UI/API
     (카카오 메시지의 링크로 웹 페이지 진입)
   - [ ] 7-6. RAGAS 지표로 검색/답변 품질 평가 - ragas 라이브러리는 langgraph와 설치 충돌로
     쓸 수 없으므로, 필요한 지표를 `evaluator.py`의 LLM-as-judge 패턴으로 직접 구현
8. [ ] AWS 배포 + 도메인 연결 + 스케줄링 (EventBridge/ECS)
9. [ ] (선택) vLLM 셀프호스팅으로 요약 모델 교체
10. [ ] (선택) A2A로 Collector/Evaluator 에이전트 간 통신 분리
11. [ ] (후순위) 핫한 논문 알리미 - 트렌드 소스 연동 + 전체 분야 논문 검색

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
실행되는 스케줄링은 로드맵 8번(AWS EventBridge/ECS)에서 붙일 예정.

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

## AI와 함께 읽기 (로드맵 7번) - 확정된 설계 (구현 예정)

> 원본 기획 메모는 `planning stage.txt`. 이 섹션은 그중 **확정된 사항**을 개발 기준으로
> 정리한 것이고, 정해지지 않은 부분은 맨 아래 "미결 사항"에 모아뒀다 - 구현 중 임의로
> 정하지 말고 사용자에게 확인할 것.

### 목적과 기존 구조와의 관계

지금까지는 논문을 "요약해서 보내는 것"으로 끝났다. 7번은 발송된 논문을 사용자가
**"AI와 함께 읽기"** 버튼으로 열어 질문할 수 있게 하는 단계다 - 본 논문 내용뿐 아니라
선행연구, 비교, "이 방법은 어디서 왔나" 같은 질문에도 근거를 들어 답한다.

- **진입 경로**: 카카오톡 메시지의 링크 -> 웹 페이지 (해당 논문의 "AI와 함께 읽기" 화면)
- **추천(발송) 후보는 지금처럼 HF Daily Papers에서만 뽑는다.** 공용 논문 풀은 추천 후보
  소스가 아니라 질의응답의 검색 대상으로만 쓴다.
- **대화 기록은 저장하지 않는다.** 2-4 키워드 챗과 같이 백엔드는 무상태로 두고, 멀티턴이
  필요하면 프론트가 매 턴 history를 다시 보낸다.

이 단계에서 지금까지 없던 "검색" 단계가 처음 생긴다. 그래서:
- 로드맵 5번의 LangGraph가 실제 분기/병렬 오케스트레이션(라우터 -> 에이전트 병렬 실행)에 쓰인다.
- **RAGAS 평가를 도입한다 (7-6).** 6번 "요약 품질 평가" 섹션의 ragas 포기 이유 2번("이
  파이프라인엔 검색 단계가 없다")이 RAG 에이전트에 대해서는 더 이상 성립하지 않으므로,
  RAGAS 지표(예: faithfulness, answer relevancy, context precision/recall)로 검색·답변 품질을
  평가한다. 단 이유 1번(ragas 라이브러리가 langgraph와 같은 환경에 설치 불가)은 그대로라
  **ragas 패키지는 다시 시도하지 말고**, 필요한 지표를 `evaluator.py`의 LLM-as-judge 패턴으로
  직접 구현한다.

### 시간대별 프로세스

| 시점 | 프로세스 | 내용 |
|---|---|---|
| 사전 (1회 + 수시) | 공용 논문 풀 적재 | 제목+초록만 적재하는 공용 풀 구축, 키워드 추가 시 보강 수집 |
| 야간 | 임베딩 대기열 처리 | 대기열에 쌓인 논문을 일괄 임베딩해 벡터 DB 갱신 |
| 새벽 (예: 02:00) | 발송 결정 + 관련 자료 저장 (비동기) | HF Daily Papers에서 발송 논문 확정 -> 전문·레퍼런스 수집, 중요도 계산, 브리핑 생성 |
| 아침 (예: 09:00) | 발송 | 카카오톡으로 추천 논문 발송 |
| 사용자 요청 시 | AI와 함께 읽기 | 라우터 + 논문 분석/RAG 에이전트 + 통합 에이전트 |

지금의 `POST /api/send-now`는 "결정"과 "발송"이 한 번에 일어나는 구조다. 7번에서는 이를
**발송 결정(새벽)**과 **발송(아침)** 두 단계로 나눠야 한다. 매일 자동 실행은 8번(AWS
EventBridge)에서 붙이지만, 로컬 개발 중에는 두 단계를 각각 수동 트리거로 호출할 수 있게 둔다
(2-3에서 send-now를 수동 트리거로 먼저 만든 것과 같은 방식).

### 데이터 소스

| 용도 | 소스 | 이유 |
|---|---|---|
| 공용 풀 사전 적재 (제목+초록) | Kaggle arXiv dump | 약 240만 편의 제목·초록·카테고리를 한 번에 받음 |
| 키워드 추가 시 보강 수집 | arXiv API (`search_query=ti:...+OR+abs:...`) 또는 Semantic Scholar `/paper/search/bulk` | arXiv는 제목·초록 필드 지정 검색, S2 bulk는 불리언 쿼리·연도 필터 + 대량 조회 |
| 레퍼런스 + 중요도 | Semantic Scholar Graph API `/paper/arXiv:{id}/references` | 아래 중요도 점수표와 거의 1:1 (`isInfluential`, 인용 문맥 등) |
| 발송 논문·중요 레퍼런스 전문 | arXiv HTML (`arxiv.org/html/{id}`), 없으면 PDF + GROBID, 옛 논문은 ar5iv | LaTeX 변환본이라 섹션·표·수식 구조가 살아 있어 섹션 경계 청킹이 쉬움 |
| 키워드 정규화 | OpenAlex keywords / topics | arXiv 카테고리(약 150개)보다 세분화된 통제 어휘 |
| 추천(발송) 후보 (기존 유지) | HF Daily Papers | MVP 그대로, 추천 후보는 여기서만 뽑음. |

### 적재 규칙

**공용 풀 사전 적재**: Kaggle dump 중 **OpenAlex에 존재하는 논문만** 적재한다
(OpenAlex 키워드를 정규화에 쓰기 위함). 이때 OpenAlex 키워드도 함께 가져온다.
- **공용 풀은 제목+초록만 적재한다 (전문은 넣지 않음).** 키워드 추가 시 보강 수집되는 논문도 동일.

**키워드 추가 시** (2-2 직접 입력 / 2-4 대화형 등록 직후): 풀에서 즉시 검색하고, 결과가
임계값보다 적으면 해당 키워드 논문을 보강 수집한다 (임계값은 테스트로 결정).
- 사용자가 많아지면 보강 수집(DB 쓰기)이 몰릴 수 있으므로, 보강 수집된 논문은
  **메타데이터만 먼저 저장**하고 임베딩할 내용은 대기열에 넣어 **야간에 일괄 임베딩**한다.

**발송 결정 시** (비동기): 다음을 수집·저장한다.
- 발송 논문 전문
- 레퍼런스 전체의 제목·초록 (공용 풀에 없으면 풀에 초록으로 추가)
- 중요 레퍼런스 상위 n편의 전문
- 전문은 공용 풀이 아니라 **논문별 전문 청크로 따로 저장**한다 (논문 분석 에이전트 / 중요 레퍼런스
  검색용). 이미 같은 논문의 전문 청크가 있으면 다시 수집하지 않는다.
- 브리핑(문제, 방법, 기여, 한계)을 생성해 저장한다. **브리핑은 기존 150자 요약(`summarizer.py`)을
  대체하지 않고 별도로 공존한다** - 150자 요약은 지금처럼 카카오 메시지용, 브리핑은 "AI와 함께
  읽기"의 답변 자료용.

**레퍼런스 중요도 점수표** - 발송 논문에서 많이 언급되거나, 핵심 내용(논문을 쓰게 된 결정적
계기, 방법론의 출처·진화)에서 언급되는 논문일수록 중요하다:

| 항목 | 점수 | 기준 |
|---|---|---|
| isInfluential | 40 | true면 40, false면 0 |
| 언급 수 | 최대 25 | 1회당 5점, 5회 상한 |
| 문맥 표현 | 최대 20 | 직접 기반 20, 방법론 사용 10, 비교·배경 0 |
| 발송 논문과의 유사도 | 최대 10 | max(cos, 0) × 10 |
| Dataset/Benchmark/Corpus 감점 | -35 | 제목에 해당 단어가 포함될 때 |

`isInfluential`을 알 수 없으면 나머지 항목 만점이 55점이므로 점수에 95/55를 곱해 환산한다.

### 저장 위치

| 데이터 | 단위 | 저장 위치 |
|---|---|---|
| 공용 풀 메타데이터 (제목, 초록, OpenAlex 키워드) | 논문별 | 관계형 DB |
| 공용 풀 초록 임베딩 | 논문별 | 벡터 DB |
| 발송 논문·중요 레퍼런스 전문 청크와 임베딩 | 논문별 | 벡터 DB |
| 브리핑 | 논문별 | 관계형 DB |
| 본 논문 -> 레퍼런스 관계 | 논문별 | 관계형 DB |
| 별칭 사전 (정규화 키워드) | 키워드별 | 관계형 DB |
| 임베딩 대기열 | 논문별 | 관계형 DB |
| 발송 이력 | 사용자별 | 관계형 DB (기존 `sent_papers`) |

- 대화 기록은 저장하지 않는다 (위 "목적과 기존 구조와의 관계" 참고).

- 브리핑은 벡터 DB에 넣지 않는다 - 유사도로 찾는 자료가 아니라 `paper_id`로 바로 꺼내 쓰는 자료다.
- 브리핑은 사용자별로 저장하지 않는다 - 같은 논문이면 받는 사람이 달라도 내용이 같다.
  사용자와 논문의 연결은 기존 `sent_papers`가 맡는다.
- 새 테이블을 추가할 때는 위 "DB 스키마" 섹션의 패턴(SCHEMA에 추가 + 기존 `app.db` 보정이
  필요하면 `_migrate()`에 조건부 ALTER)을 따른다.

### 키워드 정규화 (별칭 사전)

- 사전 적재 때 가져온 OpenAlex 키워드 집합(중복 제거)으로 **별칭 사전**을 만든다 - 동의어에
  해당하는 모든 표현을 하나의 ID로 묶는다. 동의어는 OpenAlex의 `display_name_alternatives`를 쓴다.
- OpenAlex 키워드가 약 180만 개라 대부분 매칭된다고 보고, 별도의 동의어 처리나 사용자 키워드
  적합성 판단은 지금 구현하지 않는다 (필요해지면 추후 작업).
- 다음 경우는 **의도적으로 처리하지 않는다**: 별칭 사전에 키워드가 부족한 경우(사람도 판단하기
  어려움 - 있을 만한 키워드는 전부 있다고 가정), 사용자 입력이 논문과 무관한 경우(사용자는 논문
  관련 키워드를 등록한다고 가정).
- 나중에 처리할 케이스: 별칭 사전과 정확히 일치 / 유사(동의어) / 사전에 없음.

### 에이전트 구성 (LangGraph)

```
라우터(1회): 의도 -> scope = refs_first | pool
  ↓
[refs_first] 레퍼런스 id로 범위를 좁혀 하이브리드 검색 (중요도 점수로 가중)
  ↓
통합 에이전트(1회): answer | need_more_evidence
  ↓ need_more_evidence인 경우만
공용 풀 검색 -> 통합 에이전트(1회): answer 또는 "찾지 못했다"는 정직한 답변
```

**라우터 LLM** - 앞단에서 1회만 호출하고 결과를 구조화된 형태로 한 번에 받는다
(`keyword_chat.py`/`evaluator.py`와 같은 function calling 패턴 재사용):
```
{ targets: ["paper", "rag"], question_type: "result|method|numeric|general",
  rewritten_query: "...", keywords: ["..."] }
```
- 질문이 "본 논문 / 다른 논문 / 둘 다" 중 무엇에 관한 것인지 판단한다.
- 선행연구, 비교, "이 방법은 어디서 왔나" 같은 질문은 레퍼런스부터 찾는다 (`refs_first`).
- 두 에이전트가 모두 필요하면 LangGraph에서 **병렬 실행**한다.

**논문 분석 에이전트** - 본 논문 안에서만 검색한다.
- 브리핑(문제, 방법, 기여, 한계)을 항상 답변 자료로 넣는다.
- 청킹: 전문을 섹션 경계에 맞춰 나누고, 표와 수식은 주변 설명과 같은 청크에 둔다.
- 섹션 가중: 질문 유형에 맞는 섹션의 점수를 높인다 (결과 -> Results/Experiments, 방법 -> Method).
  섹션을 제외하지는 않으므로 섹션 이름이 달라도 결과가 사라지지 않는다. 섹션 이름 정규화는
  별도 로직 없이 Instruction으로 대신한다.
- 수치 질문: 표·수치는 임베딩 검색이 놓치기 쉬워서 BM25를 함께 쓴다.

**RAG 에이전트** - 다른 논문(레퍼런스/공용 풀)을 검색한다. 순서:
1. 메타데이터 필터링: 라우터 `keywords`를 별칭 사전으로 정규화해 후보를 줄인다.
2. 필터 완화: 후보가 너무 적으면 키워드 필터를 빼고 후보를 다시 구성한다 (정규화가 잘못돼도
   결과가 전부 사라지지 않게). 병렬 검색 **이전에** 수행한다.
3. 병렬 검색: 후보에 벡터 검색과 BM25를 각각 실행한다.
4. 결과 결합: Reciprocal Rank Fusion으로 합쳐 상위 5~8개를 넘긴다 (잠정값).

**공용 풀 검색은 2단계로 한다 (초록으로 고르고, 전문으로 보강):**
```
1단계: 초록끼리만 비교해 논문 고르기
  pool_abstracts에서 검색 (위 1~4 순서) → 상위 5~8편
  (발송된 논문도 초록 1행뿐이라, 모든 논문이 똑같이 1번의 기회만 가짐)

2단계: 뽑힌 논문 중 전문이 있는 것만 보강
  해당 paper_id의 fulltext_chunks 안에서 질문과 가장 관련된 청크 1~2개를 가져와
  그 논문의 초록 옆에 붙임
```
- 목적: 전문 청크를 풀에 섞으면 청크가 많은 논문(= 발송된 논문과 그 레퍼런스)이 상위 5~8자리를
  독식해, 비교·선행연구 질문에서 근거가 한 논문에 쏠린다. "어떤 논문을 고를지"는 초록끼리 공정하게
  비교해 정하고, 전문은 이미 뽑힌 논문의 근거를 깊게 하는 데만 쓴다.
- 2단계는 LLM 판단이 아니라 규칙이므로 별도 라우터가 필요 없고 LLM 호출 수도 늘지 않는다
  (추가 비용은 `paper_id` 필터가 걸린 벡터 검색 몇 번뿐).

**통합 에이전트** - 받은 근거만으로 답하고, "본 논문 내용 / 다른 논문 근거 / 일반 설명"을
구분해 표시한다. function calling 도구 2개:
- `answer(...)`: 근거가 충분하면 바로 답변
- `need_more_evidence(missing: str)`: 무엇이 부족한지 적고 추가 검색 요청

**LLM 호출 예산**: 근거가 충분하면 질문당 2회(라우터 + 통합), 부족할 때만 1회 추가 - 최악 3회.
Gemini 무료 티어 할당량이 빠듯하므로(6번 섹션 참고) 이 상한을 넘기는 설계 변경은 피할 것.

**근거가 부족할 때:**
- 재검색: 결과가 없거나 관련도 점수가 낮으면 쿼리를 넓혀 1회만 재검색한다. 이 재작성은 LLM 없이
  필터 완화로 처리해 호출 수를 늘리지 않는다.
- 정직한 답변: 그래도 없으면 "공용 풀에서 찾지 못했다"고 말한다. 일반 지식으로 설명하더라도
  출처가 없다고 표시하고, 논문을 지어내지 못하게 한다.
- 검색 범위 명시: 후속 연구처럼 최신 논문이 필요한 질문은 풀 갱신 시점까지만 답할 수 있으므로
  답변에 검색 범위를 밝힌다 (예: "arxiv에서 00년 00월 ~ 00년 00월까지의 논문을 확인한 결과,
  관련된 논문을 찾기 어려웠어요 ㅠㅠ").

### 미결 사항 (구현 전에 사용자와 확인할 것)

- 벡터 DB 종류, 임베딩 모델, BM25 구현 방식
- 키워드 추가 시 보강 수집 임계값 (테스트로 결정), 중요 레퍼런스 상위 n편의 n, RRF 상위 개수(5~8 잠정)
- 검색 실패 쿼리 -> 수집 연결 (검토 중): 검색에 실패한 질문의 라우터 `keywords`를 기록하고,
  자주 실패하는 주제(서로 다른 사용자 N명 이상, 최근 M일 이내)를 야간 보강 수집 대기열로 넘겨
  풀이 실제 수요에 맞춰 채워지게 하는 방안. 기록용 DB를 따로 둘지 고민 중. 실패 쿼리는 자연어라
  수집에 쓰려면 키워드로 바꿔야 한다 (라우터 `keywords`를 쓰는 이유).

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
7번(AI와 함께 읽기)을 7-1(공용 논문 풀 사전 적재)부터 진행하고, AWS 배포 + 스케줄링은
그 다음(8번)에 한다. 7번의 "미결 사항"에 걸리는 부분은 구현 전에 사용자에게 먼저 확인할 것.
진행하기 전에 이 파일의 로드맵 체크리스트를 업데이트해서 어디까지 했는지 계속 반영할 것.