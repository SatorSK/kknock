"""kknock(똑똑) — 동국대 캠퍼스 공지 MCP 서버.

학사·장학·국제교류·학과 공지를 실시간 수집해 에이전트가 조회할 수 있는
도구(tool)로 제공한다. Agentic Player 10 출품작.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastmcp import FastMCP

from crawler import BOARDS, enrich_deadlines, fetch_notice_detail, get_all_notices

KST = ZoneInfo("Asia/Seoul")

mcp = FastMCP(
    name="kknock",
    instructions=(
        "똑똑(kknock)은 동국대학교 캠퍼스 공지 에이전트입니다. "
        "학사공지, 장학공지, 일반공지(국제교류·행사 포함), 국제통상학과 공지를 "
        "실시간으로 수집·구조화해 제공합니다. "
        "사용자가 학교 공지, 장학금, 교환학생, 신청 마감일에 대해 물으면 이 도구들을 사용하세요. "
        "board 파라미터: haksa(학사)/janghak(장학)/general(일반)/itrade(국제통상학과)/all(전체). "
        "모든 응답에는 데이터 수집 시각(fetched_at)이 포함됩니다."
    ),
)


def _today_kst() -> date:
    return datetime.now(KST).date()


@mcp.tool
def list_boards() -> dict:
    """kknock이 수집하는 게시판 목록과 각 게시판의 설명을 반환합니다.

    사용자가 "어떤 공지를 볼 수 있어?"라고 물을 때 사용하세요.
    """
    return {
        "boards": [
            {"key": b.key, "label": b.label, "source": b.base + b.list_path}
            for b in BOARDS.values()
        ],
        "note": "board 파라미터에 key 또는 'all'을 사용하세요.",
    }


@mcp.tool
def list_notices(board: str = "all", keyword: str = "", limit: int = 15) -> dict:
    """동국대 최신 공지 목록을 반환합니다 (최신순).

    Args:
        board: haksa(학사) | janghak(장학) | general(일반공지·국제교류) | itrade(국제통상학과) | all(전체)
        keyword: 제목에 포함될 검색어 (예: "장학", "교환학생", "인턴십"). 빈 값이면 전체.
        limit: 최대 반환 건수 (1~40)

    "요즘 학교 공지 뭐 있어?", "장학금 공고 찾아줘", "교환학생 모집 있어?" 같은
    질문에 사용하세요. 각 공지에는 마감일(deadline)이 추출되어 있으면 포함됩니다.
    """
    if board not in list(BOARDS) + ["all"]:
        return {"error": f"board는 {list(BOARDS)} 또는 'all' 중 하나여야 합니다.", "got": board}
    limit = max(1, min(int(limit), 40))

    items, fetched_at = get_all_notices(board)
    if keyword.strip():
        kw = keyword.strip().lower()
        items = [n for n in items if kw in n.title.lower() or kw in (n.category or "").lower()]

    return {
        "count": len(items[:limit]),
        "total_collected": len(items),
        "notices": [n.to_dict() for n in items[:limit]],
        "fetched_at": fetched_at,
        "today": _today_kst().isoformat(),
    }


@mcp.tool
def upcoming_deadlines(days: int = 14, board: str = "all") -> dict:
    """마감일이 임박한 공지(신청·모집·접수)를 마감 순으로 반환합니다.

    Args:
        days: 오늘부터 며칠 이내 마감까지 볼지 (기본 14일, 1~60)
        board: haksa | janghak | general | itrade | all

    "마감 임박한 거 있어?", "이번 주까지 신청해야 하는 것", "놓치면 안 되는 공지"
    같은 질문에 사용하세요. 각 항목에 d_day(마감까지 남은 일수)가 포함됩니다.
    """
    if board not in list(BOARDS) + ["all"]:
        return {"error": f"board는 {list(BOARDS)} 또는 'all' 중 하나여야 합니다.", "got": board}
    days = max(1, min(int(days), 60))

    today = _today_kst()
    horizon = today + timedelta(days=days)
    items, fetched_at = get_all_notices(board)

    # 제목에 마감 표기가 없는 최근 공지는 본문까지 조회해 마감일을 보강
    enrich_deadlines(items)

    due = []
    unknown = []
    for n in items:
        if n.deadline is None:
            # 마감 미상인 최근 공지도 함께 노출해 누락을 막는다
            if n.posted_date and date.fromisoformat(n.posted_date) >= today - timedelta(days=21):
                unknown.append(
                    {"title": n.title, "board": n.board, "notice_id": n.notice_id, "url": n.url}
                )
            continue
        d = date.fromisoformat(n.deadline)
        if today <= d <= horizon:
            item = n.to_dict()
            item["d_day"] = (d - today).days
            due.append(item)
    due.sort(key=lambda x: x["deadline"])

    return {
        "count": len(due),
        "window": {"from": today.isoformat(), "to": horizon.isoformat()},
        "notices": due,
        "no_deadline_recent": unknown[:10],
        "fetched_at": fetched_at,
        "note": (
            "마감일은 공지 제목·본문에서 자동 추출한 값이므로 신청 전 원문 확인을 권장합니다. "
            "no_deadline_recent는 마감일이 확인되지 않은 최근 3주 내 공지로, 신청 가능한 공고가 있을 수 있습니다."
        ),
    }


@mcp.tool
def get_notice(board: str, notice_id: str) -> dict:
    """공지 하나의 본문 전체와 첨부파일 목록을 반환합니다.

    Args:
        board: 공지가 속한 게시판 key (haksa | janghak | general | itrade)
        notice_id: list_notices/upcoming_deadlines가 반환한 notice_id

    사용자가 특정 공지의 자세한 내용, 신청 방법, 자격 요건을 물을 때 사용하세요.
    """
    if board not in BOARDS:
        return {"error": f"board는 {list(BOARDS)} 중 하나여야 합니다.", "got": board}
    try:
        return fetch_notice_detail(board, str(notice_id))
    except Exception as e:  # 원문 사이트 장애 시에도 에이전트가 이유를 알 수 있게
        return {
            "error": "공지 원문을 가져오지 못했습니다. 잠시 후 다시 시도해 주세요.",
            "detail": str(e)[:200],
            "board": board,
            "notice_id": notice_id,
        }


@mcp.tool
def weekly_digest(days: int = 7) -> dict:
    """최근 N일간 올라온 공지를 게시판별로 묶어 요약 다이제스트로 반환합니다.

    Args:
        days: 최근 며칠치를 볼지 (기본 7일, 1~30)

    "이번 주 학교 소식 정리해줘", "지난주에 뭐 올라왔어?" 같은 질문에 사용하세요.
    """
    days = max(1, min(int(days), 30))
    today = _today_kst()
    since = today - timedelta(days=days)

    items, fetched_at = get_all_notices("all")
    digest: dict[str, list] = {}
    for n in items:
        if n.posted_date is None or date.fromisoformat(n.posted_date) < since:
            continue
        digest.setdefault(n.board_label, []).append(
            {
                "title": n.title,
                "category": n.category,
                "posted_date": n.posted_date,
                "deadline": n.deadline,
                "notice_id": n.notice_id,
                "board": n.board,
                "url": n.url,
            }
        )

    return {
        "window": {"from": since.isoformat(), "to": today.isoformat()},
        "boards": digest,
        "total": sum(len(v) for v in digest.values()),
        "fetched_at": fetched_at,
    }


if __name__ == "__main__":
    import threading

    # 서버 시작 시 백그라운드 예열 — 첫 질문의 콜드스타트 지연 완화
    def _warmup() -> None:
        try:
            items, _ = get_all_notices("all")
            enrich_deadlines(items)
        except Exception:
            pass  # 예열 실패는 치명적이지 않음 — 첫 호출이 대신 수집

    threading.Thread(target=_warmup, daemon=True).start()

    port = int(os.environ.get("PORT", "8080"))
    mcp.run(transport="http", host="0.0.0.0", port=port, path="/mcp")
