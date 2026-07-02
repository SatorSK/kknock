"""로컬 스모크 테스트: MCP 클라이언트로 전 도구를 실제 호출해본다."""

import asyncio
import json

from fastmcp import Client

from server import mcp


async def main() -> None:
    async with Client(mcp) as c:
        tools = await c.list_tools()
        print("tools:", [t.name for t in tools])

        r = await c.call_tool("list_boards", {})
        print("\n[list_boards]", json.dumps(r.data, ensure_ascii=False)[:300])

        r = await c.call_tool("list_notices", {"limit": 5})
        data = r.data
        print(f"\n[list_notices] count={data['count']} total={data['total_collected']}")
        for n in data["notices"]:
            print(f"  {n['board']}: [{n['category']}] {n['title'][:50]} d={n['deadline']}")

        r = await c.call_tool("list_notices", {"keyword": "장학", "limit": 5})
        print(f"\n[list_notices 장학] count={r.data['count']}")

        r = await c.call_tool("upcoming_deadlines", {"days": 30})
        print(f"\n[upcoming_deadlines 30d] count={r.data['count']}")
        for n in r.data["notices"][:5]:
            print(f"  D-{n['d_day']}: {n['title'][:55]} ({n['deadline']})")

        r = await c.call_tool("weekly_digest", {"days": 14})
        print(f"\n[weekly_digest 14d] total={r.data['total']} boards={list(r.data['boards'])}")

        first = data["notices"][0]
        r = await c.call_tool("get_notice", {"board": first["board"], "notice_id": first["notice_id"]})
        d = r.data
        print(f"\n[get_notice] {d.get('title','?')[:50]} | 본문 {len(d.get('content',''))}자 | 첨부 {len(d.get('attachments',[]))}개")

        r = await c.call_tool("get_notice", {"board": "haksa", "notice_id": "999999999"})
        print(f"\n[get_notice 오류처리] error={'error' in r.data}")


if __name__ == "__main__":
    asyncio.run(main())
