# 공용 논문 풀 접근 인터페이스 (초안 v0.1)

> 대상: 에이전트 개발 담당 (7-4 RAG 에이전트, 7-5 라우터/통합 에이전트)
> 작성: DB/서버 담당. **합의 전 초안** - 함수 이름·인자·반환 형태에 의견 주세요.
> 합의되면 DB 쪽은 이 시그니처대로 `paper_pool.py`를 구현하고, 에이전트 쪽은 구현을
> 기다리지 않고 이 시그니처 기준으로 (필요하면 가짜 데이터로) 개발을 시작하면 됩니다.

## 원칙

- 에이전트 코드는 SQL을 직접 쓰지 않고 `paper_pool.py`의 함수만 호출한다.
  DB 구조(테이블/인덱스)가 바뀌어도 에이전트 코드는 바뀌지 않게 하기 위함.
- 반환값은 dict/dataclass 같은 순수 파이썬 객체. DB 커넥션·커서를 밖으로 넘기지 않는다.
- 저장소: PostgreSQL + pgvector (관계형 + 벡터 + 전문 검색을 DB 하나로).

## 식별자 규칙

| 이름 | 형식 | 예 | 비고 |
|---|---|---|---|
| `paper_id` | arXiv ID, **버전 접미사 없음** | `"2005.11401"`, `"hep-th/9901001"` | HF Daily Papers의 `hf_id`(= `sent_papers.hf_id`)와 같은 체계라 그대로 조인 가능 |
| `keyword_id` | OpenAlex keyword slug | `"retrieval-augmented-generation"` | URL 접두사(`https://openalex.org/keywords/`)는 떼고 저장 |

## 데이터 형태

```python
@dataclass
class PoolKeyword:
    keyword_id: str        # "attention-mechanism"
    display_name: str      # "attention mechanism"
    score: float           # 0~1, OpenAlex가 이 논문-키워드 연결에 매긴 점수

@dataclass
class PoolPaper:
    paper_id: str
    title: str
    abstract: str
    categories: list[str]          # ["cs.CL", "cs.LG"]
    published_date: date | None    # arXiv 최초 제출일
    openalex_id: str | None        # "W2626778328"
    keywords: list[PoolKeyword]    # score 내림차순
```

## 함수 (7-1에서 구현)

```python
def get_paper(paper_id: str) -> PoolPaper | None
def get_papers(paper_ids: list[str]) -> list[PoolPaper]        # 순서는 입력 순서 유지, 없는 id는 건너뜀

def normalize_keywords(texts: list[str]) -> dict[str, list[str]]
    # 사용자/라우터 키워드 -> keyword_id 목록 (별칭 사전 정확 일치).
    # 예: {"RAG": ["retrieval-augmented-generation"], "transformer": ["transformer", ...], "foo": []}
    # - 한 표현이 여러 keyword_id에 걸릴 수 있음 (OpenAlex 별칭이 모호한 경우) -> 리스트로 반환
    # - 사전에 없으면 빈 리스트 (= RAG 에이전트의 "필터 완화" 분기 조건)
    # - 비교 전 정규화: 소문자, 앞뒤 공백 제거, 연속 공백/하이픈/언더스코어 -> 공백 1개

def find_candidates(keyword_ids: list[str], limit: int = 2000) -> list[str]
    # 키워드 중 하나라도 달린 논문의 paper_id 목록 (메타데이터 필터링 1단계).
    # 겹치는 키워드 수 많은 순 -> 키워드 점수 합 높은 순으로 정렬.

def count_by_keywords(keyword_ids: list[str]) -> int
    # find_candidates의 총 개수 (7-2 "결과가 적으면 보강 수집" 임계값 판단용)

def pool_coverage() -> dict
    # {"paper_count": int, "min_date": date, "max_date": date, "updated_at": datetime}
    # 통합 에이전트의 "검색 범위 명시" 답변용 ("arxiv에서 00년 00월 ~ 00년 00월까지 ...")
```

## 함수 (7-2 / 7-4에서 추가 예정 - 시그니처만 미리 공유)

```python
def search_text(query: str, candidate_ids: list[str] | None = None, k: int = 50) -> list[tuple[str, float]]
    # 키워드(BM25 계열) 검색. (paper_id, score) 점수 내림차순. candidate_ids=None이면 풀 전체.

def search_vector(query: str, candidate_ids: list[str] | None = None, k: int = 50) -> list[tuple[str, float]]
    # 초록 임베딩 유사도 검색. 쿼리 임베딩은 함수 안에서 계산 (임베딩 모델을 에이전트 쪽이 몰라도 되게).
```

- RRF 결합, 상위 5~8개 선택, 필터 완화 판단은 **에이전트 쪽 로직**으로 둔다 (검색 전략이라서).
  DB 쪽은 "후보 좁히기"와 "점수 매긴 목록 돌려주기"까지만 맡는다.
- 전문 청크(`fulltext_chunks`), 브리핑, 레퍼런스 관계는 7-3에서 별도 함수로 추가.

## 아직 정하지 않은 것 (같이 결정 필요)

1. **임베딩 모델** - 차원 수가 테이블 컬럼(`vector(N)`)을 정하므로 7-2 시작 전에 확정 필요.
2. **BM25 구현** - Postgres 기본 전문 검색(`ts_rank`)은 엄밀한 BM25가 아님.
   BM25 확장(예: ParadeDB `pg_search`)을 쓸지, 기본 기능으로 충분한지 7-4 품질 보고 결정.
3. `find_candidates`의 기본 `limit`, 정렬 기준이 RAG 에이전트 쪽 기대와 맞는지.
