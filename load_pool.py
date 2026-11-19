"""
공용 논문 풀 사전 적재 (로드맵 7-1).

Kaggle arXiv dump -> CS/AI 카테고리 필터 -> OpenAlex에서 키워드 조회 -> 키워드 개체(별칭) 조회
-> PostgreSQL 적재. 단계마다 data/pool_build/ 아래 중간 파일을 남기고, OpenAlex 조회 단계는
이미 조회한 id를 기록해두어 하루 예산($1)이 떨어져 끊겨도 다음 날 같은 명령으로 이어서 돈다.

    uv run python load_pool.py filter   --dump data/arxiv-metadata-oai-snapshot.json
    uv run python load_pool.py openalex [--max-requests N]
    uv run python load_pool.py keywords [--max-requests N]
    uv run python load_pool.py load
    uv run python load_pool.py status
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

from db import get_connection
from pool_db import init_pool_db, normalize_keyword_text

load_dotenv()

BUILD_DIR = Path("data/pool_build")
FILTERED = BUILD_DIR / "filtered.jsonl"
WORKS = BUILD_DIR / "openalex_works.jsonl"
WORKS_CHECKED = BUILD_DIR / "openalex_checked.txt"
KEYWORDS = BUILD_DIR / "keywords.jsonl"
KEYWORDS_CHECKED = BUILD_DIR / "keywords_checked.txt"

OPENALEX = "https://api.openalex.org"
BATCH = 100  # OpenAlex 필터에 |로 묶는 id 수. 1회 조회 = $0.0001
HEADERS = {"User-Agent": "paper-pool-loader"}


class BudgetExhausted(Exception):
    pass


def is_target_category(cat: str) -> bool:
    """적재 범위: CS + AI 인접 분야 (CLAUDE.md 7-1 결정)."""
    return cat.startswith("cs.") or cat.startswith("eess.") or cat == "stat.ML"


def _clean(text: str) -> str:
    return " ".join(text.split())


# ---------------------------------------------------------------- 1. filter

def cmd_filter(dump_path: str) -> None:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    total = kept = 0
    with open(dump_path, encoding="utf-8") as src, open(FILTERED, "w", encoding="utf-8") as out:
        for line in src:
            total += 1
            r = json.loads(line)
            cats = r["categories"].split()
            abstract = _clean(r.get("abstract") or "")
            if not abstract or not any(is_target_category(c) for c in cats):
                continue
            created = r["versions"][0]["created"]  # "Mon, 2 Apr 2007 19:18:42 GMT"
            published = datetime.strptime(created, "%a, %d %b %Y %H:%M:%S %Z").date().isoformat()
            out.write(json.dumps({
                "paper_id": r["id"],
                "title": _clean(r["title"]),
                "abstract": abstract,
                "categories": cats,
                "published_date": published,
            }, ensure_ascii=False) + "\n")
            kept += 1
    print(f"filter: {total:,}편 중 {kept:,}편 -> {FILTERED}")


# ---------------------------------------------------------------- OpenAlex 공통

def _get(client: httpx.Client, path: str, params: dict) -> dict:
    key = os.environ.get("OPENALEX_API_KEY")
    if key:
        params = {**params, "api_key": key}
    for attempt in range(5):
        try:
            resp = client.get(f"{OPENALEX}{path}", params=params)
        except httpx.TransportError:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 429:
            # 초당 요청 제한이면 잠깐 쉬면 풀리지만, 일일 예산 소진이면 계속 429가 난다.
            if attempt >= 2:
                raise BudgetExhausted(resp.text[:300])
            time.sleep(5 * (attempt + 1))
            continue
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError(f"OpenAlex 요청 반복 실패: {path}")


def _read_checked(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.open(encoding="utf-8") if line.strip()}


def _run_batches(name, pending, fetch_batch, out_path, checked_path, max_requests):
    """pending을 BATCH개씩 조회. 결과를 먼저 쓰고 나서 checked에 기록 -> 중간에 죽어도 누락 없음
    (최악의 경우 마지막 배치가 결과 파일에 중복으로 들어가고, load 단계에서 중복은 무시된다)."""
    requests = 0
    cost = 0.0
    started = time.time()
    with out_path.open("a", encoding="utf-8") as out, checked_path.open("a", encoding="utf-8") as chk:
        for i in range(0, len(pending), BATCH):
            if max_requests is not None and requests >= max_requests:
                print(f"{name}: --max-requests {max_requests}회 도달, 중단")
                break
            batch = pending[i:i + BATCH]
            try:
                records, batch_cost = fetch_batch(batch)
            except BudgetExhausted as e:
                print(f"{name}: OpenAlex 429 반복 - 일일 예산 소진으로 보고 중단합니다. "
                      f"내일 같은 명령으로 이어서 실행하세요.\n  응답: {e}")
                break
            for rec in records:
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            out.flush()
            chk.write("".join(f"{x}\n" for x in batch))
            chk.flush()
            requests += 1
            cost += batch_cost
            if requests % 50 == 0:
                done = i + len(batch)
                rate = done / (time.time() - started)
                eta_min = (len(pending) - done) / rate / 60 if rate else 0
                print(f"{name}: {done:,}/{len(pending):,} 조회, 이번 실행 비용 ${cost:.4f}, "
                      f"남은 시간 약 {eta_min:.0f}분")
    print(f"{name}: 이번 실행 {requests:,}회 요청, 비용 약 ${cost:.4f}")


# ---------------------------------------------------------------- 2. openalex (논문 -> 키워드)

def _arxiv_id_of(work: dict, by_doi: dict[str, str]) -> str | None:
    """
    OpenAlex 응답 work가 이번 배치의 어느 arXiv 논문인지 찾는다.

    work["doi"]만 보면 안 된다: arXiv 판이 학술지 출판본과 한 work로 합쳐진 경우
    (주로 옛 논문) work["doi"]는 학술지 DOI(예: 10.1007/...)이고, arXiv DOI는
    locations[].id("doi:10.48550/arxiv.0704.0002")에만 남는다. 처음엔 work["doi"]로만
    매칭해서 2007년 논문 일치율이 42%로 나왔다.
    """
    candidates = [(work.get("doi") or "").lower().removeprefix("https://doi.org/")]
    for loc in work.get("locations") or []:
        loc_id = (loc.get("id") or "").lower()
        if loc_id.startswith("doi:"):
            candidates.append(loc_id.removeprefix("doi:"))
        elif loc_id.startswith("pmh:oai:arxiv.org:"):
            candidates.append("10.48550/arxiv." + loc_id.removeprefix("pmh:oai:arxiv.org:"))
    for doi in candidates:
        if doi in by_doi:
            return by_doi[doi]
    return None


def cmd_openalex(max_requests: int | None) -> None:
    checked = _read_checked(WORKS_CHECKED)
    pending = []
    with FILTERED.open(encoding="utf-8") as f:
        for line in f:
            pid = json.loads(line)["paper_id"]
            if pid not in checked:
                pending.append(pid)
    print(f"openalex: 남은 논문 {len(pending):,}편 (이미 조회 {len(checked):,}편), "
          f"예상 요청 {-(-len(pending) // BATCH):,}회")

    with httpx.Client(headers=HEADERS, timeout=60) as client:
        def fetch_batch(batch):
            by_doi = {f"10.48550/arxiv.{pid}".lower(): pid for pid in batch}
            data = _get(client, "/works", {
                "filter": "doi:" + "|".join(by_doi),
                "select": "id,doi,keywords,locations",
                "per_page": 200,
            })
            records = []
            for w in data["results"]:
                pid = _arxiv_id_of(w, by_doi)
                if pid is None:
                    continue
                records.append({
                    "paper_id": pid,
                    "openalex_id": w["id"].rsplit("/", 1)[-1],
                    "keywords": [
                        {"id": k["id"].rsplit("/", 1)[-1], "display_name": k["display_name"],
                         "score": k["score"]}
                        for k in (w.get("keywords") or [])
                    ],
                })
            return records, data["meta"].get("cost_usd") or 0.0

        _run_batches("openalex", pending, fetch_batch, WORKS, WORKS_CHECKED, max_requests)


# ---------------------------------------------------------------- 3. keywords (키워드 -> 별칭)

def cmd_keywords(max_requests: int | None) -> None:
    keyword_ids = set()
    with WORKS.open(encoding="utf-8") as f:
        for line in f:
            for k in json.loads(line)["keywords"]:
                keyword_ids.add(k["id"])
    checked = _read_checked(KEYWORDS_CHECKED)
    pending = sorted(keyword_ids - checked)
    print(f"keywords: 풀에 등장한 키워드 {len(keyword_ids):,}개 중 남은 {len(pending):,}개")

    with httpx.Client(headers=HEADERS, timeout=60) as client:
        def fetch_batch(batch):
            data = _get(client, "/keywords", {
                "filter": "id:" + "|".join(batch),
                "select": "id,display_name,display_name_alternatives,works_count",
                "per_page": 200,
            })
            records = [{
                "keyword_id": k["id"].rsplit("/", 1)[-1],
                "display_name": k["display_name"],
                "alternatives": k.get("display_name_alternatives") or [],
                "works_count": k.get("works_count"),
            } for k in data["results"]]
            return records, data["meta"].get("cost_usd") or 0.0

        _run_batches("keywords", pending, fetch_batch, KEYWORDS, KEYWORDS_CHECKED, max_requests)


# ---------------------------------------------------------------- 4. load (PostgreSQL)

def _copy_rows(cur, table: str, columns: list[str], rows) -> int:
    n = 0
    with cur.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as cp:
        for row in rows:
            cp.write_row(row)
            n += 1
    return n


def cmd_load() -> None:
    """임시 테이블에 COPY한 뒤 INSERT ... ON CONFLICT DO NOTHING - 몇 번을 다시 돌려도 안전하다."""
    init_pool_db()

    works = {}
    with WORKS.open(encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            works[rec["paper_id"]] = rec
    print(f"load: OpenAlex에 있는 논문 {len(works):,}편")

    with get_connection() as conn, conn.cursor() as cur:
        cur.execute("""
            CREATE TEMP TABLE tmp_papers (LIKE pool_papers INCLUDING DEFAULTS) ON COMMIT DROP;
            ALTER TABLE tmp_papers DROP COLUMN search_tsv;
            CREATE TEMP TABLE tmp_keywords (LIKE oa_keywords) ON COMMIT DROP;
            CREATE TEMP TABLE tmp_aliases (LIKE keyword_aliases) ON COMMIT DROP;
            CREATE TEMP TABLE tmp_paper_keywords (LIKE paper_keywords) ON COMMIT DROP;
        """)

        def paper_rows():
            with FILTERED.open(encoding="utf-8") as f:
                for line in f:
                    p = json.loads(line)
                    w = works.get(p["paper_id"])
                    if w is None:  # OpenAlex에 없는 논문은 적재하지 않음 (CLAUDE.md 적재 규칙)
                        continue
                    yield (p["paper_id"], w["openalex_id"], p["title"], p["abstract"],
                           p["categories"], p["published_date"], "kaggle")

        n = _copy_rows(cur, "tmp_papers",
                       ["paper_id", "openalex_id", "title", "abstract", "categories",
                        "published_date", "source"], paper_rows())
        print(f"load: 논문 {n:,}행 COPY")

        # 키워드: works 응답의 display_name을 기본으로 두고, keywords 단계에서 받은 개체 정보로 덮는다
        # (keywords 단계가 덜 끝났어도 FK가 깨지지 않게).
        keywords = {}
        for w in works.values():
            for k in w["keywords"]:
                keywords.setdefault(k["id"], {"display_name": k["display_name"],
                                              "alternatives": [], "works_count": None})
        if KEYWORDS.exists():
            with KEYWORDS.open(encoding="utf-8") as f:
                for line in f:
                    k = json.loads(line)
                    keywords[k["keyword_id"]] = k

        _copy_rows(cur, "tmp_keywords", ["keyword_id", "display_name", "works_count"],
                   ((kid, k["display_name"], k["works_count"]) for kid, k in keywords.items()))

        def alias_rows():
            for kid, k in keywords.items():
                seen = set()
                # slug도 별칭에 넣는다 - display_name이 "transformer models"라 slug "transformer"로만
                # 들어오는 사용자 입력이 안 걸리는 경우가 있다.
                candidates = [(k["display_name"], True), (kid, False)] + \
                             [(a, False) for a in k["alternatives"]]
                for text, primary in candidates:
                    norm = normalize_keyword_text(text)
                    if norm and norm not in seen:
                        seen.add(norm)
                        yield (norm, kid, primary)

        n = _copy_rows(cur, "tmp_aliases", ["alias_norm", "keyword_id", "is_primary"], alias_rows())
        print(f"load: 키워드 {len(keywords):,}개, 별칭 {n:,}행 COPY")

        def paper_keyword_rows():
            for pid, w in works.items():
                for k in w["keywords"]:
                    yield (pid, k["id"], k["score"])

        n = _copy_rows(cur, "tmp_paper_keywords", ["paper_id", "keyword_id", "score"],
                       paper_keyword_rows())
        print(f"load: 논문-키워드 {n:,}행 COPY")

        cur.execute("""
            INSERT INTO pool_papers (paper_id, openalex_id, title, abstract, categories, published_date, source)
                SELECT DISTINCT ON (paper_id) paper_id, openalex_id, title, abstract, categories, published_date, source
                FROM tmp_papers ON CONFLICT DO NOTHING;
            INSERT INTO oa_keywords SELECT * FROM tmp_keywords
                ON CONFLICT (keyword_id) DO UPDATE SET
                    display_name = EXCLUDED.display_name,
                    works_count = COALESCE(EXCLUDED.works_count, oa_keywords.works_count);
            INSERT INTO keyword_aliases SELECT * FROM tmp_aliases ON CONFLICT DO NOTHING;
            INSERT INTO paper_keywords
                SELECT DISTINCT ON (t.paper_id, t.keyword_id) t.* FROM tmp_paper_keywords t
                JOIN pool_papers p USING (paper_id) ON CONFLICT DO NOTHING;
            INSERT INTO pool_meta VALUES ('updated_at', now()::text)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;
        """)
        cur.execute("ANALYZE pool_papers; ANALYZE paper_keywords; ANALYZE keyword_aliases;")
    cmd_status()


def cmd_status() -> None:
    def lines(p: Path) -> int:
        return sum(1 for _ in p.open(encoding="utf-8")) if p.exists() else 0
    print(f"[중간 파일] filtered {lines(FILTERED):,} / openalex 조회 {lines(WORKS_CHECKED):,} "
          f"(일치 {lines(WORKS):,}) / 키워드 조회 {lines(KEYWORDS_CHECKED):,} (받음 {lines(KEYWORDS):,})")
    try:
        with get_connection() as conn:
            row = conn.execute("""
                SELECT (SELECT count(*) FROM pool_papers) AS papers,
                       (SELECT count(*) FROM oa_keywords) AS keywords,
                       (SELECT count(*) FROM keyword_aliases) AS aliases,
                       (SELECT count(*) FROM paper_keywords) AS paper_keywords,
                       (SELECT min(published_date) FROM pool_papers) AS min_date,
                       (SELECT max(published_date) FROM pool_papers) AS max_date
            """).fetchone()
        print(f"[DB] 논문 {row['papers']:,} / 키워드 {row['keywords']:,} / 별칭 {row['aliases']:,} / "
              f"논문-키워드 {row['paper_keywords']:,} / 기간 {row['min_date']} ~ {row['max_date']}")
    except Exception as e:  # DB가 안 떠 있어도 중간 파일 현황은 보이게
        print(f"[DB] 접속 불가: {e.__class__.__name__}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("filter")
    p.add_argument("--dump", default="data/arxiv-metadata-oai-snapshot.json")
    for name in ("openalex", "keywords"):
        p = sub.add_parser(name)
        p.add_argument("--max-requests", type=int, default=None,
                       help="이번 실행에서 보낼 최대 요청 수 (테스트용)")
    sub.add_parser("load")
    sub.add_parser("status")
    args = parser.parse_args()

    if args.cmd == "filter":
        cmd_filter(args.dump)
    elif args.cmd == "openalex":
        cmd_openalex(args.max_requests)
    elif args.cmd == "keywords":
        cmd_keywords(args.max_requests)
    elif args.cmd == "load":
        cmd_load()
    else:
        cmd_status()


if __name__ == "__main__":
    sys.exit(main())
