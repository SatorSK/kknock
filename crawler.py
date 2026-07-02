"""kknock crawler — 동국대학교 공지 게시판 수집·파싱 모듈.

대상 게시판은 모두 로그인 없이 접근 가능한 공개 페이지이며,
요청 최소화를 위해 게시판 단위 인메모리 캐시(TTL)를 사용한다.
"""

from __future__ import annotations

import re
import time
import threading
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta

import httpx
from bs4 import BeautifulSoup

USER_AGENT = "kknock-mcp/0.1 (campus notice agent)"
CACHE_TTL_SECONDS = 30 * 60
LIST_PAGES_PER_BOARD = 2  # 게시판당 수집할 목록 페이지 수 (페이지당 ~12건)
HTTP_TIMEOUT = 10.0


@dataclass(frozen=True)
class Board:
    key: str
    label: str
    base: str
    list_path: str
    detail_path: str  # {id} 포맷
    style: str  # "list" (본교 CMS) | "table" (학과 CMS)


BOARDS: dict[str, Board] = {
    "haksa": Board(
        key="haksa",
        label="학사공지 (수업·학적·프로그램·특강)",
        base="https://www.dongguk.edu",
        list_path="/article/HAKSANOTICE/list",
        detail_path="/article/HAKSANOTICE/detail/{id}",
        style="list",
    ),
    "janghak": Board(
        key="janghak",
        label="장학공지 (교내·국가·외부 장학금)",
        base="https://www.dongguk.edu",
        list_path="/article/JANGHAKNOTICE/list",
        detail_path="/article/JANGHAKNOTICE/detail/{id}",
        style="list",
    ),
    "general": Board(
        key="general",
        label="일반공지 (국제교류·교환학생·행사·채용 포함)",
        base="https://www.dongguk.edu",
        list_path="/article/GENERALNOTICES/list",
        detail_path="/article/GENERALNOTICES/detail/{id}",
        style="list",
    ),
    "itrade": Board(
        key="itrade",
        label="국제통상학과 공지",
        base="https://itrade.dongguk.edu",
        list_path="/article/notice/list",
        detail_path="/article/notice/detail/{id}",
        style="table",
    ),
}


@dataclass
class Notice:
    board: str
    board_label: str
    notice_id: str
    title: str
    category: str | None
    posted_date: str | None  # YYYY-MM-DD
    deadline: str | None  # YYYY-MM-DD (제목에서 추출, 없으면 None)
    views: int | None
    has_attachment: bool
    is_pinned: bool
    url: str

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- deadline

_DEADLINE_PATTERNS = [
    # ~7/3, ~ 7.3, ~7/3(금), ~7/3 17:00
    re.compile(r"~\s*(?P<m>\d{1,2})\s*[./]\s*(?P<d>\d{1,2})"),
    # ~7월3일, ~ 7월 3일
    re.compile(r"~\s*(?P<m>\d{1,2})\s*월\s*(?P<d>\d{1,2})\s*일"),
    # ~2026.07.03 / ~2026-07-03
    re.compile(r"~\s*(?P<y>\d{4})\s*[.\-/]\s*(?P<m>\d{1,2})\s*[.\-/]\s*(?P<d>\d{1,2})"),
    # 7월 3일까지
    re.compile(r"(?P<m>\d{1,2})월\s*(?P<d>\d{1,2})일\s*(?:\([^)]*\)\s*)?(?:\d{1,2}:\d{2}\s*)?까지"),
    # 2026.07.03.(금)까지 / 7.3.까지
    re.compile(
        r"(?:(?P<y>\d{4})\s*[.\-/]\s*)?(?P<m>\d{1,2})\s*[.\-/]\s*(?P<d>\d{1,2})\s*\.?\s*(?:\([^)]*\)\s*)?(?:\d{1,2}:\d{2}\s*)?까지"
    ),
]


def extract_deadline(text: str, base: date | None = None) -> str | None:
    """공지 제목/본문 텍스트에서 마감일을 추출해 ISO 날짜 문자열로 반환.

    연도가 없는 표기(~7/3)는 base(게시일 또는 오늘) 기준으로 추정하되,
    base보다 40일 이상 과거가 되면 다음 해로 넘긴다.
    """
    base = base or date.today()
    candidates: list[date] = []
    for pat in _DEADLINE_PATTERNS:
        for m in pat.finditer(text):
            try:
                month = int(m.group("m"))
                day = int(m.group("d"))
                year_g = m.groupdict().get("y")
                year = int(year_g) if year_g else base.year
                cand = date(year, month, day)
            except (ValueError, IndexError):
                continue
            if not year_g and cand < base - timedelta(days=40):
                try:
                    cand = date(year + 1, month, day)
                except ValueError:
                    continue
            candidates.append(cand)
    if not candidates:
        return None
    # 기간 표기(6.30.~7.11.)면 마지막 날짜가 마감일
    return max(candidates).isoformat()


# ---------------------------------------------------------------- parsing

_DATE_RE = re.compile(r"(\d{4})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})")
_GO_DETAIL_RE = re.compile(r"goDetail\((\d+)\)")


def _norm_date(text: str) -> str | None:
    m = _DATE_RE.search(text)
    if not m:
        return None
    y, mo, d = (int(g) for g in m.groups())
    try:
        return date(y, mo, d).isoformat()
    except ValueError:
        return None


def _parse_list_style(html: str, board: Board) -> list[Notice]:
    """본교 CMS: <li><a onclick="goDetail(id)"><em>카테고리</em><p class="tit">…"""
    soup = BeautifulSoup(html, "lxml")
    notices = []
    for a in soup.select('a[onclick*="goDetail"]'):
        m = _GO_DETAIL_RE.search(a.get("onclick", ""))
        if not m:
            continue
        nid = m.group(1)

        tit = a.select_one("p.tit")
        if tit is None:
            continue
        for span in tit.select("span.mobile"):
            span.decompose()
        title = tit.get_text(" ", strip=True)

        em = a.select_one("em")
        category = em.get_text(strip=True) if em else None

        info_spans = a.select("div.info span")
        posted = None
        views = None
        for span in info_spans:
            t = span.get_text(strip=True)
            if posted is None:
                posted = _norm_date(t)
                if posted is not None:
                    continue
            vm = re.search(r"조회\s*([\d,]+)", t)
            if vm:
                views = int(vm.group(1).replace(",", ""))

        base_date = date.fromisoformat(posted) if posted else None
        notices.append(
            Notice(
                board=board.key,
                board_label=board.label,
                notice_id=nid,
                title=title,
                category=category,
                posted_date=posted,
                deadline=extract_deadline(title, base_date),
                views=views,
                has_attachment=a.select_one("span.file") is not None,
                is_pinned=a.select_one("div.mark span.fix") is not None,
                url=board.base + board.detail_path.format(id=nid),
            )
        )
    return notices


def _parse_table_style(html: str, board: Board) -> list[Notice]:
    """학과 CMS: <tr><td>번호</td><td class="tit"><a onclick="goDetail(id)">…"""
    soup = BeautifulSoup(html, "lxml")
    notices = []
    for tr in soup.select("tr"):
        a = tr.select_one('a[onclick*="goDetail"]')
        if a is None:
            continue
        m = _GO_DETAIL_RE.search(a.get("onclick", ""))
        if not m:
            continue
        nid = m.group(1)
        title = a.get_text(" ", strip=True)

        row_text = tr.get_text(" ", strip=True)
        posted = _norm_date(row_text)
        views = None
        tds = tr.find_all("td")
        for td in reversed(tds):
            t = td.get_text(strip=True)
            if t.isdigit():
                views = int(t)
                break

        num_td = tds[0].get_text(strip=True) if tds else ""
        base_date = date.fromisoformat(posted) if posted else None
        notices.append(
            Notice(
                board=board.key,
                board_label=board.label,
                notice_id=nid,
                title=title,
                category=None,
                posted_date=posted,
                deadline=extract_deadline(title, base_date),
                views=views,
                has_attachment=bool(tr.select_one("span.file, img[alt*='첨부']")),
                is_pinned=not num_td.isdigit(),
                url=board.base + board.detail_path.format(id=nid),
            )
        )
    return notices


# ---------------------------------------------------------------- fetch + cache

_cache: dict[str, tuple[float, list[Notice]]] = {}
_cache_lock = threading.Lock()


def _fetch_board(board: Board) -> list[Notice]:
    items: list[Notice] = []
    seen: set[str] = set()
    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT, follow_redirects=True
    ) as client:
        for page in range(1, LIST_PAGES_PER_BOARD + 1):
            url = f"{board.base}{board.list_path}?pageIndex={page}"
            try:
                resp = client.get(url)
                resp.raise_for_status()
            except httpx.HTTPError:
                continue  # 페이지 하나 실패해도 나머지는 반환
            parser = _parse_list_style if board.style == "list" else _parse_table_style
            for n in parser(resp.text, board):
                if n.notice_id not in seen:
                    seen.add(n.notice_id)
                    items.append(n)
    return items


def get_board_notices(board_key: str, force_refresh: bool = False) -> tuple[list[Notice], str]:
    """게시판 공지 목록과 수집 시각(ISO)을 반환. TTL 내에는 캐시 사용."""
    board = BOARDS[board_key]
    now = time.time()
    with _cache_lock:
        cached = _cache.get(board_key)
        if cached and not force_refresh and now - cached[0] < CACHE_TTL_SECONDS:
            return cached[1], datetime.fromtimestamp(cached[0]).isoformat(timespec="seconds")
    items = _fetch_board(board)
    with _cache_lock:
        if items or board_key not in _cache:
            _cache[board_key] = (now, items)
        else:
            # 이번 수집이 실패(0건)면 이전 캐시 유지
            now, items = _cache[board_key]
    return items, datetime.fromtimestamp(now).isoformat(timespec="seconds")


def get_all_notices(board_key: str = "all") -> tuple[list[Notice], dict[str, str]]:
    keys = list(BOARDS) if board_key == "all" else [board_key]
    all_items: list[Notice] = []
    fetched_at: dict[str, str] = {}
    for key in keys:
        items, ts = get_board_notices(key)
        all_items.extend(items)
        fetched_at[key] = ts
    all_items.sort(key=lambda n: (n.posted_date or "", n.notice_id), reverse=True)
    return all_items, fetched_at


# ---------------------------------------------------------------- detail

def fetch_notice_detail(board_key: str, notice_id: str) -> dict:
    """공지 상세: 본문 텍스트와 첨부파일 목록."""
    board = BOARDS[board_key]
    url = board.base + board.detail_path.format(id=notice_id)
    with httpx.Client(
        headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT, follow_redirects=True
    ) as client:
        resp = client.get(url)
        resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")

    cont = soup.select_one(".view_cont")
    content = cont.get_text("\n", strip=True) if cont else ""
    content = re.sub(r"\n{3,}", "\n\n", content)
    if cont is None:
        raise ValueError(f"공지를 찾을 수 없습니다 (board={board_key}, id={notice_id})")

    files = [
        fa.get_text(" ", strip=True)
        for fa in soup.select(".view_files a")
        if fa.get_text(strip=True)
    ]

    title_el = soup.select_one(".board_view h4, .board_view .tit, .view_tit, h3")
    title = title_el.get_text(" ", strip=True) if title_el else (soup.title.get_text(strip=True) if soup.title else "")

    deadline = extract_deadline(title + "\n" + content)
    return {
        "board": board_key,
        "board_label": board.label,
        "notice_id": notice_id,
        "title": title,
        "content": content[:4000],
        "content_truncated": len(content) > 4000,
        "attachments": files,
        "deadline": deadline,
        "url": url,
    }


if __name__ == "__main__":
    # 수동 점검용: 각 게시판 상위 3건 출력
    for key in BOARDS:
        items, ts = get_board_notices(key)
        print(f"\n=== {key} ({len(items)}건, fetched {ts})")
        for n in items[:3]:
            print(f"  [{n.category or '-'}] {n.title[:60]} | {n.posted_date} | 마감:{n.deadline} | id={n.notice_id}")
