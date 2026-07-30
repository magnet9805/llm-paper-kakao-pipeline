# astral의 uv 공식 이미지 - Python + uv가 이미 설치돼 있어 별도로 pip install uv를
# 할 필요가 없다. 이 프로젝트는 pip/venv 대신 uv만 쓰기로 했으므로(CLAUDE.md 참고)
# 컨테이너 안에서도 동일하게 uv로 의존성을 관리한다.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# 바이트코드 컴파일 + 하드링크 대신 복사(COPY_MODE) - 볼륨이 아닌 일반 이미지 레이어라
# 링크가 의미 없고, 컴파일해두면 컨테이너 최초 기동이 조금 더 빠르다.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# 의존성 설치를 소스 코드 복사보다 먼저 해서, 코드만 바뀌었을 때는 이 레이어가
# 캐시되어 uv sync를 다시 돌리지 않게 한다.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY . .
RUN uv sync --locked --no-dev

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# 웹 서비스(server.py)를 기본으로 띄운다. 개인용 스크립트(main.py)를 한 번 실행하고
# 싶다면 `docker run <image> uv run python main.py`로 커맨드를 덮어쓰면 된다.
CMD ["uv", "run", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
