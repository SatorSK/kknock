# 똑똑 (kknock) — 캠퍼스 공지 MCP 서버

> 정보를 찾아다니는 시대에서, 에이전트가 대신 떠먹여주는 시대로.

동국대학교의 학사·장학·일반(국제교류)·학과 공지를 실시간 수집·구조화해서
AI 에이전트가 읽을 수 있는 도구(MCP tools)로 제공하는 서버입니다.
**Agentic Player 10** 출품작.

## 무엇이 되나

카카오톡 AI에게 이렇게 물으면 kknock이 답합니다:

- "요즘 학교 공지 뭐 있어?" → `list_notices`
- "마감 임박한 장학금 있어?" → `upcoming_deadlines` (D-day 계산 포함)
- "이번 주 학교 소식 정리해줘" → `weekly_digest`
- "그 공지 신청 방법 알려줘" → `get_notice` (본문·첨부 파싱)

## 도구 목록

| Tool | 설명 |
|---|---|
| `list_boards` | 수집 게시판 안내 |
| `list_notices(board, keyword, limit)` | 최신 공지 목록 + 키워드 검색 |
| `upcoming_deadlines(days, board)` | 마감 임박 공지, D-day 순 정렬 |
| `get_notice(board, notice_id)` | 공지 본문 전문 + 첨부파일 |
| `weekly_digest(days)` | 최근 N일 공지 게시판별 다이제스트 |

## 설계 포인트 (안정성)

- **LLM 비의존 파싱**: 게시판 자체 카테고리 + 정규식 마감일 추출 → 외부 API 장애·비용 없음
- **TTL 캐시(30분)**: 학교 서버에 부담을 주지 않고, 수집 실패 시 이전 캐시 유지
- **모든 응답에 수집 시각(`fetched_at`) 명시**: 데이터 신선도를 에이전트가 판단 가능
- **부분 실패 허용**: 페이지 하나가 죽어도 나머지 게시판은 정상 응답

## 실행

```bash
pip install -r requirements.txt
python server.py   # http://0.0.0.0:8080/mcp (PORT 환경변수로 변경 가능)
```

Docker:

```bash
docker build -t kknock .
docker run -p 8080:8080 kknock
```

## 수집 대상 (모두 공개 게시판)

- 학사공지: https://www.dongguk.edu/article/HAKSANOTICE/list
- 장학공지: https://www.dongguk.edu/article/JANGHAKNOTICE/list
- 일반공지: https://www.dongguk.edu/article/GENERALNOTICES/list
- 국제통상학과: https://itrade.dongguk.edu/article/notice/list

게시판 추가는 `crawler.py`의 `BOARDS`에 항목 하나를 더하는 것으로 끝납니다 —
같은 CMS를 쓰는 모든 대학 게시판으로 확장 가능한 구조입니다.
