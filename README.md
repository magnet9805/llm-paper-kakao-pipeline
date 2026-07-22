# paper-kakao-pipeline (MVP)

매일 Hugging Face Daily Papers의 인기 상위 논문 중, 관심 키워드(시계열×LLM,
멀티에이전트/A2A, RAG, LLM 추론 효율, 추론기법)에 해당하는 논문을 골라 요약해서
카카오톡 "나에게 보내기"로 발송하는 파이프라인의 MVP 버전.

이 단계에는 아직 FastAPI, Docker, LangGraph, MCP, RAGAS, AWS 배포가 없다.
파이썬 스크립트 하나가 수집 -> 요약 -> 발송을 순서대로 실행하는 최소 버전이며,
이후 단계에서 이 로직을 점진적으로 리팩터링해 나갈 예정.

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

2. `.env`에 `GEMINI_API_KEY`, `KAKAO_REST_API_KEY` 채우기
   - Gemini API 키(무료 티어): https://aistudio.google.com/apikey
   - 카카오 REST API 키: https://developers.kakao.com 에서 앱 생성 후 확인
     (카카오 로그인 활성화 + Redirect URI에 `http://localhost:5000/oauth` 등록 +
     동의항목에서 "카카오톡 메시지 전송" 활성화 필요)

관심 키워드 클러스터는 `collector.py`의 `KEYWORD_CLUSTERS`에서 수정할 수 있다.
`time_series` 클러스터만 예외적으로 "시계열 관련 단어"와 "LLM 관련 단어"가
**둘 다** 있어야 통과하도록 `require_all_of`로 묶여 있다 (순수 통계 시계열 논문 배제).

3. 카카오 토큰 최초 발급 (한 번만 실행)

```bash
uv run python kakao_auth_helper.py
```

## 실행

```bash
uv run python main.py
```

성공하면 카카오톡 "나에게 보내기"로 오늘의 논문 요약이 도착한다.

## 다음 단계 (로드맵)

- [ ] FastAPI로 감싸서 수동 트리거/설정 API 제공
- [ ] Docker 컨테이너화
- [ ] 논문 검색/조회 로직을 MCP 서버로 분리
- [ ] LangGraph로 Collector/Filter/Summarizer 노드 그래프화
- [ ] RAGAS로 요약 품질 평가 하네스 구축
- [ ] AWS 배포 + 스케줄링
- [ ] (선택) vLLM 셀프호스팅, A2A 멀티에이전트 통신
