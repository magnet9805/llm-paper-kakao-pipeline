# 프로젝트 컨텍스트 (Claude Code용)

세션 시작 시 자동으로 읽히는 파일. 작업 전에 반드시 참고할 것.

## 프로젝트 개요

관심 키워드에 맞는 최신 논문(멀티에이전트, RAG, LLM 기반 시계열예측, 추론기법 등)을
매일 요약해 카카오톡으로 보내주는 "관심 논문 카톡 알리미" 웹 서비스.

- 스택: FastAPI, SQLite, Authlib(카카오 로그인), Gemini API(무료 티어), Docker, MCP, LangGraph
- 설계 원칙: 인증·세션·DB 같은 주변부는 표준 라이브러리에 위임해 최소 구현하고,
  리소스는 핵심 로직(수집·필터링·LLM 기반 요약/키워드 추출/에이전트)에 집중한다.
- 패키지 관리는 **uv만** 사용 (`uv add`, `uv sync`, `uv run`). pip/requirements.txt 금지.

## 로드맵

1. [x] MVP: HF Daily Papers 수집 + 키워드 필터 + Gemini 요약 + 카카오 발송 (개인용 스크립트 `main.py`)
2. [x] FastAPI + 카카오 소셜 로그인 + SQLite 멀티유저 (2-1 로그인, 2-2 키워드 CRUD,
   2-3 사용자별 발송 `POST /api/send-now`, 2-4 LLM 대화형 키워드 추출, 2-5 홈 진입점 + 그룹별 on/off)
3. [x] Docker 컨테이너화
4. [x] 논문 검색을 MCP 서버로 분리
5. [x] LangGraph로 Collector/Filter/Summarizer 그래프화
6. [x] 요약 품질 평가 하네스 (ragas 대신 `evaluator.py` 직접 구현)
7. [ ] **Agent System 고도화: 직무 갭 분석 에이전트** -> `docs/career_agent.md`
8. [ ] AWS 배포 + 도메인(`aipaperkakao.kro.kr`) 연결 + 스케줄링 (EventBridge/ECS)
9. [ ] (선택) vLLM 셀프호스팅으로 요약 모델 교체
10. [ ] (선택) A2A로 Collector/Evaluator 에이전트 간 통신 분리
11. [ ] (후순위) 핫한 논문 알리미 - 트렌드 소스 연동 + 전체 분야 논문 검색

## 논문 수집

- 소스: HF Daily Papers `https://huggingface.co/api/daily_papers?date=YYYY-MM-DD&limit=100`
  (구글 스칼라는 공식 API 없음 + 크롤링 약관 위반 소지로 제외)
- `upvotes` 상위 30개를 추린 뒤 키워드로 필터링. 한 클러스터라도 매칭되면 통과(OR),
  여러 클러스터에 걸릴수록 랭킹 우선.
- 기본 프리셋 클러스터(`collector.py`의 `KEYWORD_CLUSTERS`, 동등 가중치):
  `time_series`(LLM 기반만, `require_all_of`로 시계열 단어 AND LLM 단어), `multi_agent`,
  `rag`, `inference_efficiency`, `reasoning`

## 인증: 카카오 소셜 로그인 단일

이메일/비밀번호 가입은 없음. 카카오 OAuth 한 번으로 로그인과 메시지 발송 권한(`talk_message`)을
동시에 얻는다. 라이브러리: Authlib + Starlette `SessionMiddleware`.

```
GET  /auth/kakao/login     카카오로 리다이렉트
GET  /auth/kakao/callback  토큰 교환 -> users upsert -> 세션 쿠키
POST /auth/logout
GET  /auth/me
```

**Authlib + 카카오 함정 (실전 확인):**
- `oauth.register(...)`에 `token_endpoint_auth_method="client_secret_post"` 필수.
  기본값(Basic 헤더)이면 `invalid_client: Not exist client_id [null]`.
- scope에 `profile_nickname profile_image talk_message`를 명시해야 한다. 빠지면 로그인은
  되는데 닉네임/프로필이 조용히 `null`.

## DB (SQLite)

```sql
users(id, kakao_id UNIQUE, nickname, profile_image_url,
      kakao_access_token, kakao_refresh_token, kakao_token_expires_at, created_at)
keyword_groups(id, user_id -> users, title,
               source CHECK IN ('manual','llm_chat'), is_active DEFAULT 1, created_at)
keywords(id, group_id -> keyword_groups ON DELETE CASCADE, keyword_text)
sent_papers(id, user_id -> users, hf_id, sent_at, UNIQUE(user_id, hf_id))  -- 사용자별 중복 발송 방지
```

- SQLite는 연결마다 `PRAGMA foreign_keys = ON`을 해야 CASCADE가 동작한다 (`db.py`의 `get_connection()`에 반영됨).
- 컬럼 추가: SCHEMA에 새 컬럼을 넣고 `db.py`의 `_migrate()`에 조건부 `ALTER TABLE ... ADD COLUMN`을 추가하는
  패턴을 재사용한다. **CHECK 제약은 ALTER로 못 바꾼다** (테이블 재생성 필요).
- `DB_PATH` 환경변수로 경로 오버라이드 (기본 `app.db`, Docker에서는 `/app/data/app.db`).

## API (구현 완료, 전부 `require_login` + `WHERE user_id = ?`로 소유권 확인)

```
POST   /api/keyword-groups                    그룹 생성 (title, keywords[], source)
GET    /api/keyword-groups                    내 그룹 목록
PATCH  /api/keyword-groups/{id}               제목 수정
PATCH  /api/keyword-groups/{id}/active        발송 on/off ({is_active: bool})
DELETE /api/keyword-groups/{id}               삭제 (키워드 CASCADE)
POST   /api/keyword-groups/{id}/keywords      키워드 추가
DELETE /api/keywords/{id}                     키워드 삭제
POST   /api/keyword-chat                      LLM 대화 한 턴 (무상태, 프론트가 history 전달)
POST   /api/send-now                          지금 논문 받아보기 (수동 트리거)
```

## 사용자별 발송

개인용 스크립트의 collector/summarizer/kakao_sender를 재사용하고 "사용자별로 다른 부분"만 바꿨다:

| 개인용 (`main.py`) | 웹 (`server.py`) |
|---|---|
| 고정 `KEYWORD_CLUSTERS` | 사용자의 활성 키워드 그룹 (그룹 1개 = 클러스터 1개, `_clusters_from_keyword_groups()`) |
| `seen_papers.json` | `sent_papers` 테이블 |
| `kakao_token.json` | `users` 테이블의 토큰 (`refresh_user_access_token`) |

`is_active=False` 그룹은 발송 대상에서만 빠지고 삭제되지는 않는다. 자동 스케줄링은 로드맵 8번에서 붙인다.

## 프론트엔드 (서버 렌더링, `templates/`)

SPA 없이 Jinja2 + 바닐라 JS (프론트는 최소 구성이 설계 원칙).

- `base.html` 공통 레이아웃 / `index.html` 홈 / `mypage.html` 그룹 관리
- `_chat_modal.html`, `_manual_modal.html`: 홈과 마이페이지가 `{% include %}`로 공유하는 팝업.
  페이지별 후처리만 `onGroupRegistered(group)` 훅으로 분리 (새 진입점이 늘어도 이 패턴 재사용).
- 홈 진입점: "관심 키워드 등록"(직접 입력 팝업), "AI 기반 관심 키워드 찾기"(대화 팝업). 둘 다 페이지 이동 없이 팝업.
- 마이페이지 편집 UX: 수정 아이콘 -> 모달. 키워드 `✕` 삭제는 confirm 후 즉시 API 반영,
  `+` 추가는 알약형 입력칸 + `✓`/`✕`. 제목 변경만 [저장]이 필요. 이 패턴은 대화형 등록 확인 팝업에도 재사용됨.

## LLM 대화형 키워드 추출 (`keyword_chat.py`, 구현 완료)

- 모델 `gemini-flash-latest`, function calling `propose_keyword_group(title, keywords[5~8])`.
- 시스템 프롬프트: 대화 초반 1~2턴은 제안하지 말 것, keywords는 **영어**로 (논문 원문이 영어).
- 흐름: 멀티턴 대화 -> tool_use로 제안 -> 키워드 칩(토글 선택) -> [선택] -> 등록 확인 팝업
  (제목 수정 가능, [취소]/[등록]) -> **[등록] 시점에만** `POST /api/keyword-groups` 호출.
- 카드 상태 3가지: active / registered(✓ 등록됨) / dismissed(선택 없이 다음 메시지를 보내면 회색 + 비활성).
- 한 세션에서 여러 그룹 등록 가능 (등록 후에도 모달은 닫히지 않음). 안내 문구는 프론트 고정 문구.

## Docker

`Dockerfile`(베이스 `ghcr.io/astral-sh/uv:python3.12-bookworm-slim`), `.dockerignore`, `docker-compose.yml`.

- 의존성 레이어 캐싱: `pyproject.toml`/`uv.lock`만 먼저 COPY -> `uv sync --locked --no-install-project`.
- `app-data` 볼륨을 `/app/data`에 마운트, `DB_PATH=/app/data/app.db`.
- `.env`는 이미지에 COPY 금지, `env_file`로 실행 시점에만 주입.
- 포트 8000:8000 -> 카카오 Redirect URI는 로컬과 동일 (`http://localhost:8000`).

## MCP 서버 (`mcp_server.py`)

`collector.py`의 `fetch_top_daily_papers`, `filter_by_keywords`를 도구 2개로 노출:
`list_daily_papers`, `search_papers(keyword_groups, ...)` (그룹 사이 AND, 그룹 안 OR).

- **설계 판단**: MCP는 "이 앱 바깥"에서 재사용하기 위한 별도 진입점이다. `server.py`와
  `pipeline_graph.py`는 `collector.py`를 **직접 import**한다 (같은 프로세스에서 프로토콜 왕복 불필요).
- **`mcp==2.0.0` 주의**: `from mcp.server.mcpserver import MCPServer` (구 `fastmcp.FastMCP`는 없음).
  옛 이름으로 되돌리지 말고, 설치된 버전을 직접 확인할 것.
- `search_papers`는 `seen_ids`에 빈 집합을 명시적으로 넘긴다 (안 그러면 로컬 `seen_papers.json`을 읽음).
- 실행: `uv run mcp dev mcp_server.py` (Inspector), `uv run python mcp_server.py` (stdio).
- 테스트 함정: `call_tool` 결과는 `.content`가 아니라 `.structured_content["result"]`를 볼 것.

## LangGraph 파이프라인 (`pipeline_graph.py`)

`collector -> filter -> summarizer` 선형 `StateGraph`. `main.py`와 `/api/send-now` 모두
`run_pipeline(target_date, top_n, clusters, seen_ids, papers_per_send)` 하나로 호출한다.
State(`PipelineState`): 입력(`target_date, top_n, clusters, seen_ids, papers_per_send`) +
출력(`raw_papers, filtered_papers, summarized_papers`). 필터 통과 논문이 0편이면 summarizer는 Gemini를 호출하지 않는다.
테스트는 `papers_per_send=0`(그래프 연결만) -> `=1`(실제 API 1건)로 할당량을 아낀다.

## 요약 품질 평가 (`evaluator.py`)

**ragas는 다시 시도하지 말 것.** (1) `ragas`가 `langchain_community.chat_models.vertexai`를 무조건
import하는데 최신 `langchain-community`에 없고, 구버전으로 고정하면 `langgraph`의 `langchain-core>=1.4.7`과
충돌해 uv가 해결 불가. (2) 핵심 지표가 "질문->검색->답변" RAG용이라 검색 단계가 없는 이 파이프라인과 안 맞음.

대안: Gemini를 LLM-as-judge로 쓰는 직접 구현. 기준 `faithful`(지어낸 내용 없음, LLM),
`relevant`(핵심 기여 반영, LLM), `concise`(150자 이하, `len()`으로 결정론적).
`uv run python evaluator.py`로 3편 샘플 채점 (무료 티어 20건/일이라 샘플을 작게 유지).
충실한 요약 vs 환각 요약 쌍으로 판별력을 검증함.

## 직무 갭 분석 에이전트 (로드맵 7)

상세 설계(State, Planner 라우팅, 도구, 스키마, API, 평가, 이력서 개인정보 처리)는
**`docs/career_agent.md`**에 있다. 구현 전에 반드시 읽을 것. 아래는 핵심 요약.

- **목적**: AI 직무 준비 사용자의 희망 직무 채용공고 요구 스킬 vs 보유 스킬(+사용 증거 신뢰도)을 비교해
  보완 스킬을 찾고, 이를 기존 관심 키워드 그룹(`POST /api/keyword-groups`, `source="career_gap"`)으로 연결한다.
- **기존 논문 파이프라인(`pipeline_graph.py`)은 변경하지 않는다.** 그래프/State/파일을 분리한다.
- **위치**: 전용 페이지 `/career` + 홈 세 번째 버튼 + 마이페이지 커리어 섹션. 기존 `_chat_modal.html`에 넣지 않는다.
- **확정 결정**: 이력서 업로드는 선택 / 스킬은 증거 슬롯(project, role, how, outcome)으로 신뢰도 산정.
- **구조**: Planner(규칙 기반 라우팅, LLM은 발화 해석에만) + ① 상황 파악 -> ② 공고 검색 -> ③ 갭 분석.
  `gap_score = demand * (1 - credit)`, 갭 계산은 LLM 없이 집계.
- **데이터**: 사람인/워크넷 공식 API만 사용(크롤링 금지), 스킬 추출은 별칭 사전 기반 규칙이 기본(LLM은 일일 상한 내 보강),
  임베디드 벡터 저장소 + 로컬 임베딩. 의존성 추가 전 `uv`가 `langgraph`와 충돌 없이 풀리는지 확인.
- **개인정보**: 이력서 원문 저장 금지, 이메일/전화 마스킹, 외부 LLM 전송 고지, 커리어 데이터 전체 삭제 기능.
- **평가**: ragas 없이 직접 구현, 되돌아가기 시나리오 4개를 궤적 평가 테스트로 사용.
- **주의**: `keyword_groups.source`에 `'career_gap'`을 넣으려면 CHECK 제약 때문에 테이블 재생성 마이그레이션이 필요
  (싫으면 `'llm_chat'` 재사용).

## 협업 규칙

- `main`은 PR로만 변경. 브랜치는 사람 단위 (`feat/...`).
- 충돌이 잦은 파일은 한 PR에서 작게, 먼저 머지된 쪽에 맞춰 rebase: `server.py`, `db.py`,
  `pyproject.toml`/`uv.lock`, `CLAUDE.md`.
- 새 모듈은 인터페이스(함수 시그니처/State)를 먼저 합의한 뒤 구현한다.
- 설계 결정이 바뀌면 코드 PR과 별개로 이 파일(또는 `docs/`)을 수정하는 PR을 올린다.

## 코딩/설계 컨벤션

- uv만 사용. 인증/DB/세션은 라이브러리에 최대한 위임.
- 카카오 발송은 "나에게 보내기" API, 사용자별 refresh_token으로 access_token 자동 갱신 필수.
- 커밋은 기능 단위로 잘게 (예: `feat: 카카오 소셜 로그인 추가`).
- `.env`는 절대 커밋하지 않고 `.env.example`만 유지.

## 다음에 할 일

완료: 로드맵 1~6. 지금은 **로드맵 7 (직무 갭 분석 에이전트)** 를 `docs/career_agent.md`의
구현 순서대로 진행한다. 변경 시 이 파일의 로드맵 체크박스를 갱신할 것.

**지금 바로 (사용자가 직접)**
- 사람인 API access-key, 워크넷 인증키 신청 (승인 대기 중에는 샘플/목 데이터로 A-1~A-5 진행)

**구현 순서 (A-1 -> A-8)**
1. A-1 공고 수집/구조화/스킬 정규화 + DB 스키마 (`jobs_ingest.py`, `skill_aliases`)
2. A-2 공고 검색 도구 + 벡터 인덱스 (`search_jobs`, `get_job_detail`) - 의존성 호환 확인 후 저장소 결정
3. A-3 ① 상황 파악 에이전트 (직무 확정 + 증거 슬롯/신뢰도, 대화 경로만)
4. A-4 ③ 갭 분석 (`compute_gap` 순수 함수 + 갭 카드)
5. A-5 Planner 라우팅 + 되돌아가기 시나리오 4개 + 체크포인터
6. A-6 `/career` 프론트 + 홈 진입점 + 마이페이지 + 키워드 그룹 연결
7. A-7 평가 하네스 (`career_eval.py`)
8. A-8 이력서 업로드 (선택 기능, 마지막. 착수 전 LLM 무료 티어 데이터 약관 확인)

**팀 분담 제안**: 담당 A = A-3~A-7(에이전트/프론트), 담당 B = A-1~A-2(데이터/검색) + 이후 로드맵 8(AWS).
공유 파일(`server.py`, `db.py`, 의존성)은 PR을 작게 나눠 충돌을 줄인다.

**그 다음**: 로드맵 8 (AWS 배포 + 도메인 + 스케줄링 - 공고 수집 배치 스케줄도 여기서 함께 붙임) -> 선택 항목(9, 10) -> 11.