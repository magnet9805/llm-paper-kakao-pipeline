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
   - 2-3. 기존 collector.py를 사용자별 키워드로 파라미터화해서 카카오 발송까지 연결
   - 2-4. LLM 대화형 키워드 추출 (아래 스펙대로 구현)
3. [ ] Docker 컨테이너화
4. [ ] 논문 검색/조회 로직을 MCP 서버로 분리
5. [ ] LangGraph로 Collector/Filter/Summarizer 노드 그래프화
6. [ ] RAGAS로 요약 품질 평가 하네스 구축
7. [ ] AWS 배포 + 도메인 연결 + 스케줄링 (EventBridge/ECS)
8. [ ] (선택) vLLM 셀프호스팅으로 요약 모델 교체
9. [ ] (선택) A2A로 Collector/Evaluator 에이전트 간 통신 분리
10. [ ] (후순위) 핫한 논문 알리미 - 트렌드 소스 연동 + 전체 분야 논문 검색

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
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE keywords (
    id INTEGER PRIMARY KEY,
    group_id INTEGER NOT NULL REFERENCES keyword_groups(id) ON DELETE CASCADE,
    keyword_text TEXT NOT NULL
);
```

> SQLite는 `ON DELETE CASCADE`를 기본적으로 무시한다 - 연결마다 `PRAGMA foreign_keys = ON`을
> 실행해야 실제로 동작한다 (`db.py`의 `get_connection()`에 이미 반영되어 있음).

**관심 키워드 그룹 API 엔드포인트 (구현 완료, `server.py`):**
```
POST   /api/keyword-groups                       # 그룹 생성 (title, keywords[]) - source="manual" 고정
GET    /api/keyword-groups                        # 내 그룹 목록 조회 (마이페이지용)
PATCH  /api/keyword-groups/{group_id}              # 그룹 제목 수정
DELETE /api/keyword-groups/{group_id}              # 그룹 전체 삭제 (키워드도 CASCADE로 같이 삭제)
POST   /api/keyword-groups/{group_id}/keywords     # 그룹에 키워드 하나 추가
DELETE /api/keywords/{keyword_id}                  # 키워드 하나 삭제
```
모든 엔드포인트는 `require_login` 의존성으로 로그인을 요구하고, 그룹/키워드가 요청한
사용자 소유인지 SQL의 `WHERE user_id = ?` 절로 확인한다 (남의 그룹 id를 넣어도 404).

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
  로그인 여부에 따라 로그인 버튼 또는 마이페이지 링크를 보여줌.
- `templates/mypage.html`: 마이페이지 (`GET /mypage`). 키워드 그룹 목록 + 그룹별
  수정/삭제 아이콘 버튼(연필/휴지통, 그룹 박스 우측) + "+ 새 그룹 등록" 토글 버튼.

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
- **이 x-삭제(confirm 팝업) / +-추가(체크·엑스 버튼) 패턴은 로드맵 2-4(LLM 대화형
  키워드 추출)의 칩 선택 UI에도 그대로 재사용할 것.**
- "+ 새 그룹 등록"은 상시 노출된 폼이 아니라, 클릭 전엔 점선 테두리 버튼(호버 시
  테두리 강조)만 보이고 클릭하면 폼이 펼쳐지는 방식.

## LLM 대화형 키워드 추출 - 확정된 스펙

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

## 코딩/설계 컨벤션

- 패키지 관리: uv만 사용. `pip install`이나 `requirements.txt` 다시 만들지 말 것
- 인증/DB/세션은 라이브러리(Authlib, SessionMiddleware, SQLAlchemy 등)에 최대한 의존하고
  직접 구현을 최소화할 것 - 핵심 로직에 리소스를 집중하기 위함
- 카카오 발송: "나에게 보내기" API. 사용자별 refresh_token으로 access_token 자동 갱신 필수
- 각 단계 변경 시 커밋 단위를 기능 단위로 잘게 나눌 것 (예: `feat: 카카오 소셜 로그인 추가`)
- 비밀값(.env)은 절대 커밋하지 않음, `.env.example`만 레포에 유지

## 다음에 할 일

2-1, 2-2 완료됨. 다음은 2-3(기존 collector.py를 사용자별 키워드로
파라미터화해서 카카오 발송까지 연결)부터 진행. 진행하기 전에 이 파일의
로드맵 체크리스트를 업데이트해서 어디까지 했는지 계속 반영할 것.