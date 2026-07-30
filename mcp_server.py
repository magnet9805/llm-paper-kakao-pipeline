"""
논문 검색/조회 로직(collector.py)을 MCP(Model Context Protocol) 서버로 노출한다.
Claude Desktop 같은 MCP 클라이언트나 향후 LangGraph 노드가, 이 앱의 파이썬 모듈을
직접 import하지 않고도 표준 프로토콜로 논문 검색 도구를 재사용할 수 있게 하기 위함
(로드맵 4번, CLAUDE.md 참고).

server.py(FastAPI 웹 서비스)는 이 서버를 거치지 않고 collector.py를 그대로 직접
호출한다 - 같은 프로세스 안에서 이뤄지는 호출까지 프로토콜 왕복으로 바꿀 이유가
없기 때문. MCP 서버는 "이 앱 바깥"에서 논문 검색 기능을 재사용하기 위한 별도의
진입점이다.

실행:
    uv run mcp dev mcp_server.py      # MCP Inspector로 도구 직접 테스트
    uv run python mcp_server.py       # stdio 서버로 실행 (Claude Desktop 등에서 이 커맨드로 spawn)
"""

from mcp.server.mcpserver import MCPServer

from collector import fetch_top_daily_papers, filter_by_keywords

mcp = MCPServer("paper-search")


@mcp.tool()
def list_daily_papers(date: str | None = None, top_n: int = 30) -> list[dict]:
    """
    Hugging Face Daily Papers에서 date(생략 시 어제 날짜) 기준 upvotes 상위
    top_n개 논문을 키워드 필터링 없이 그대로 가져온다. "오늘 뭐가 화제인지"
    훑어보고 싶을 때 쓴다.

    date는 "YYYY-MM-DD" 형식. 오늘 날짜는 아직 논문이 덜 쌓여있을 수 있어
    생략하면 어제 날짜를 쓴다 (collector.py의 관례를 그대로 따름).
    """
    return fetch_top_daily_papers(target_date=date, top_n=top_n)


@mcp.tool()
def search_papers(
    keyword_groups: list[list[str]], date: str | None = None, top_n: int = 30
) -> list[dict]:
    """
    Hugging Face Daily Papers에서 date(생략 시 어제) 기준 상위 top_n개 논문 중
    keyword_groups 조건에 매칭되는 논문을 검색한다.

    keyword_groups는 "그룹의 리스트"다 - 그룹 사이는 AND, 그룹 안 키워드끼리는
    OR로 매칭된다. 논문 하나의 제목+초록에 각 그룹의 키워드가 최소 하나씩은
    다 등장해야 매칭된 것으로 친다.

    예시:
    - RAG 관련 논문만 찾고 싶다면 그룹을 하나만 넘기면 된다:
      keyword_groups=[["retrieval-augmented", "rag"]]
    - "시계열 예측이면서 동시에 LLM 기반인 논문"처럼 두 조건을 동시에 만족해야
      한다면 그룹을 두 개 넘긴다:
      keyword_groups=[["time series", "forecasting"], ["llm", "language model"]]
      (순수 통계/전통 ML 시계열 논문을 걸러내기 위한 용도 - collector.py의
      time_series 클러스터와 동일한 방식)

    date는 "YYYY-MM-DD" 형식, 생략하면 어제 날짜를 쓴다.
    """
    papers = fetch_top_daily_papers(target_date=date, top_n=top_n)
    cluster = {"require_all_of": keyword_groups}
    # seen_ids=set(): 이 도구는 특정 사용자의 발송 이력과 무관한 범용 검색이므로,
    # filter_by_keywords가 기본값으로 읽으려는 개인용 스크립트의 seen_papers.json을
    # 참조하지 않도록 명시적으로 빈 집합을 넘긴다.
    matched = filter_by_keywords(papers, clusters={"search": cluster}, seen_ids=set())
    return [{k: v for k, v in paper.items() if k != "matched_clusters"} for paper in matched]


if __name__ == "__main__":
    mcp.run()
