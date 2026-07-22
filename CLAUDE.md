# 프로젝트 컨텍스트 (Claude Code용)

이 파일은 Claude Code가 세션 시작 시 자동으로 읽는 컨텍스트 파일이다.
claude.ai에서 나눈 설계 논의 내용을 요약해뒀으니, 작업 전에 반드시 참고할 것.

## 프로젝트 목적

Hugging Face Daily Papers에서 매일 인기 상위 논문 중 관심 키워드에 해당하는
논문을 골라 요약해서 카카오톡 "나에게 보내기"로 발송하는 파이프라인.

최종적으로는 아래 9개 기술 스택을 전부 경험/포함하는 것이 목표
(취업 포트폴리오 목적):
RAGAS, vLLM, Docker, AWS, FastAPI, LangGraph/LangChain, A2A, 에이전트 평가,
하네스 엔지니어링, MCP

## 현재 단계: MVP (완료)

- 수집(collector.py) -> 요약(summarizer.py) -> 발송(kakao_sender.py)을
  main.py가 순서대로 실행하는 가장 단순한 버전
- 아직 FastAPI, Docker, LangGraph, MCP, RAGAS, AWS, vLLM, A2A는 없음
- 패키지 관리는 pip/venv가 아니라 **uv**를 사용 (`uv add`, `uv sync`, `uv run`)

## 개발 로드맵 (이 순서로 진행하기로 함)

1. [x] MVP: HF Daily Papers 수집 + 키워드 필터 + Gemini API(무료 티어) 요약 + 카카오 발송
2. [ ] FastAPI로 감싸서 수동 트리거/설정 API 제공
3. [ ] Docker 컨테이너화
4. [ ] 논문 검색/조회 로직을 MCP 서버로 분리
5. [ ] LangGraph로 Collector/Filter/Summarizer 노드 그래프화
6. [ ] RAGAS로 요약 품질 평가 하네스 구축
7. [ ] AWS 배포 + 스케줄링 (EventBridge/ECS, 카카오 토큰 자동 갱신)
8. [ ] (선택) vLLM 셀프호스팅으로 요약 모델 교체
9. [ ] (선택) A2A로 Collector/Evaluator 에이전트 간 통신 분리

한 번에 다 만들지 않고, 단계별로 점진적으로 리팩터링하는 방식으로 진행 중.
각 단계는 이후 velog 블로그 포스팅 소재로도 활용할 예정.

## 논문 수집 소스: Hugging Face Daily Papers (arXiv 직접 크롤링 아님)

- API: `https://huggingface.co/api/daily_papers?date=YYYY-MM-DD&limit=100`
- 구글 스칼라는 공식 API가 없고 크롤링이 ToS 위반이라 사용하지 않기로 함
- `upvotes` 필드 기준으로 그날의 상위 30개(top_n)를 추린 뒤 키워드로 필터링

## 관심 키워드 클러스터 (collector.py의 KEYWORD_CLUSTERS)

지원 직무(AI/데이터 직무, 은행권 AI 서비스 평가 등)와 본인 연구 이력을 고려해
아래 5개 클러스터로 확정함 (동등 가중치, 우선순위 없음):

1. **time_series**: LLM 기반 시계열예측만 (통계/전통 ML 시계열은 배제)
   - 특수 로직: `require_all_of`로 "시계열 단어" AND "LLM 단어"가 둘 다 있어야 통과
2. **multi_agent**: 멀티에이전트, A2A(agent2agent), tool use 등
3. **rag**: retrieval-augmented generation, hybrid retrieval 등
4. **inference_efficiency**: vLLM 관련 - speculative decoding, KV cache, quantization 등
5. **reasoning**: chain-of-thought, test-time scaling 등

한 클러스터라도 매칭되면 통과(OR), 여러 클러스터에 걸릴수록 랭킹에서 우선순위를 줌.

## 코딩/설계 컨벤션

- 패키지 관리: uv만 사용. `pip install`이나 `requirements.txt` 다시 만들지 말 것
- 카카오 발송: "나에게 보내기" API. refresh_token으로 access_token 자동 갱신 로직 필수
  (`kakao_auth_helper.py`로 최초 1회 수동 인증, 이후 `kakao_sender.py`가 자동 갱신)
- 각 단계 변경 시 커밋 단위를 기능 단위로 잘게 나눌 것 (예: `feat: FastAPI 엔드포인트 추가`)
- 비밀값(.env)은 절대 커밋하지 않음, `.env.example`만 레포에 유지

## 다음에 할 일

로드맵의 2번(FastAPI 리팩터링)부터 시작하면 됨. 진행하기 전에 이 파일의
로드맵 체크리스트를 업데이트해서 어디까지 했는지 계속 반영할 것.
