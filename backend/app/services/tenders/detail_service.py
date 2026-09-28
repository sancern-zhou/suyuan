"""On-demand detail hydration. SQL transaction locks prevent duplicate paid calls."""
import asyncio
import json

import pyodbc
from bs4 import BeautifulSoup

from config.settings import settings
from .sources.zhiliao_ai import ZhiliaoAiClient


class TenderDetailService:
    def __init__(self, connection_string=None, client_factory=ZhiliaoAiClient):
        self.connection_string = connection_string or settings.sqlserver_connection_string
        self.client_factory = client_factory

    async def get(self, *, bid_id=None, title=None, refresh=False):
        # Keep blocking ODBC calls and the transaction off the agent event loop.
        return await asyncio.to_thread(self._get, bid_id, title, refresh)

    def _get(self, bid_id, title, refresh):
        conn = pyodbc.connect(self.connection_string, timeout=20)
        conn.timeout = 60
        try:
            cur = conn.cursor()
            cur.execute("SET XACT_ABORT ON; SET LOCK_TIMEOUT 10000")
            fields = "id,bid_id,title,url,publish_date,purchaser,bid_type"
            if bid_id is not None:
                cur.execute(f"SELECT TOP 21 {fields} FROM dbo.tender_notices WHERE bid_id=? ORDER BY id", bid_id)
            else:
                cur.execute(f"SELECT TOP 21 {fields} FROM dbo.tender_notices WHERE title=? ORDER BY id", title)
                rows = cur.fetchall()
                if not rows:
                    escaped = title.replace("[", "[[]").replace("%", "[%]").replace("_", "[_]")
                    cur.execute(f"SELECT TOP 21 {fields} FROM dbo.tender_notices WHERE title LIKE ? ORDER BY publish_date DESC,id DESC", "%"+escaped+"%")
                else:
                    return self._resolve(conn, cur, rows, refresh)
            return self._resolve(conn, cur, cur.fetchall(), refresh)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _resolve(self, conn, cur, rows, refresh):
        if not rows:
            return dict(success=False, status="not_found", cost_units=0,
                        summary="本地未找到该公告。请先用中标信息查询工具定位已入库公告及 bid_id。")
        if len(rows) != 1:
            return dict(success=True, status="needs_selection", cost_units=0,
                        summary="存在多个匹配公告，请按日期、采购单位和 bid_id 确认具体公告后再获取详情。",
                        has_more=len(rows)>20,
                        candidates=[dict(zip(("id","bid_id","title","url","publish_date","purchaser","bid_type"),
                                             [str(v) if hasattr(v,"isoformat") else v for v in row])) for row in rows[:20]])
        row = rows[0]
        if row[1] is None:
            return dict(success=False, status="legacy_source", cost_units=0,
                        summary="这是历史来源公告，没有知了 bid_id，无法直接调用知了详情接口；请查询同项目的知了公告。")
        # Transaction-scoped database lock also serializes requests across processes.
        cur.execute("""DECLARE @r int; EXEC @r=sys.sp_getapplock @Resource=?,
            @LockMode='Exclusive',@LockOwner='Transaction',@LockTimeout=10000; SELECT @r""",
                    f"tender_detail:{row[1]}")
        if cur.fetchone()[0] < 0:
            raise RuntimeError("该公告正在获取详情，请稍后重试")
        cur.execute("SELECT raw_content,detail_json,attachment_urls_json,detail_fetched_at FROM dbo.tender_notices WHERE id=?",row[0])
        cached = cur.fetchone()
        if cached[3] is not None and cached[0] and not refresh:
            conn.commit()
            fields = (json.loads(cached[1] or "{}").get("data") or {})
            return dict(success=True,status="cached",bid_id=row[1],title=row[2],url=row[3],
                        content=cached[0],attachment_urls=json.loads(cached[2] or "[]"),
                        details={k:v for k,v in fields.items() if k not in {"source","source_ext","attachment_urls"}},
                        fetched_at=cached[3].isoformat()+"Z",cost_units=0,stored=True)
        bid_type = row[6]
        if bid_type not in {"招标","中标"}:
            raise ValueError("公告缺少有效 bid_type，不能猜测详情类型")
        data, audit = asyncio.run(self._fetch(row[1],bid_type))
        if data.get("bid_id") is not None and str(data["bid_id"]) != str(row[1]):
            raise ValueError("详情响应的公告 ID 不匹配，拒绝保存")
        content = "\n\n".join(BeautifulSoup(str(data[k]),"html.parser").get_text("\n",strip=True)
                               for k in ("source","source_ext") if data.get(k))
        if not content.strip():
            raise ValueError("接口正文为空，未覆盖已有详情")
        attachments = data.get("attachment_urls") or []
        cost = audit.get("cost_units")
        cur.execute("""UPDATE dbo.tender_notices SET raw_content=?,detail_json=?,
            attachment_urls_json=?,detail_fetched_at=SYSUTCDATETIME(),detail_cost_units=?,
            content_updated_at=SYSUTCDATETIME(),updated_at=SYSDATETIME() WHERE id=?""",
            content,json.dumps(dict(data=data,meta=audit),ensure_ascii=False),
            json.dumps(attachments,ensure_ascii=False),cost,row[0])
        if cur.rowcount != 1:
            raise RuntimeError("详情落库记录数异常")
        conn.commit()
        return dict(success=True,status="fetched",bid_id=row[1],title=row[2],url=row[3],
                    content=content,attachment_urls=attachments,cost_units=cost,stored=True,
                    details={k:v for k,v in data.items() if k not in {"source","source_ext","attachment_urls"}})

    async def _fetch(self, bid_id, bid_type):
        client = self.client_factory()
        try:
            data = await client.get_bid_detail(bid_id,bid_type)
            return data, (client.request_audit[-1] if client.request_audit else {})
        finally:
            await client.close()
