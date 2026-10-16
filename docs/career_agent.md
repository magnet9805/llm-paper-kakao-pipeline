# 직무 갭 분석 에이전트 상세 설계

> CLAUDE.md 로드맵 7번의 상세 스펙. 기존 CLAUDE.md의 해당 섹션을 그대로 옮긴 것.

## Agent System 고도화: 직무 갭 분석 에이전트 (로드맵 7)

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
  마감된 공고는 `is_active=0`. 스케줄링은 로드맵 8번(EventBridge)에서 붙이고, 그 전에는 수동 실행.
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