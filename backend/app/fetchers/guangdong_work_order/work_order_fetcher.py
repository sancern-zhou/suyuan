"""广东运维工单同步 Fetcher。

数据链路（项目确认的架构）::

    Operation_SC_GD（172.20.105.179，生产只读源，dbo.working_orders 等兼容视图）
      → guangdong_work_order_fetcher 定时抽取
      → 本地 PostgreSQL guangdong_mart schema（受控同步层）
      → execute_guangdong_mart_sql / 工单审计 / KG 等消费方。

增量策略：
- working_orders 按 ``update_time`` 水位增量（状态流转也会刷新 UPDATETIME）；
  首次运行回填近 BACKFILL_MONTHS 个月。
- working_order_details 源表无更新时间，随本轮触碰的工单按工单编码整删重插。
- wo_commonfile_links 按 WCFID 高水位追加（附件索引近 append-only）。
- dim_station / dim_device 每轮全量 upsert（行数小）。

连接配置来自部署环境文件：
- ``OPS_SQLSERVER_*``：运维源库（config.settings.ops_sqlserver_connection_string）
- ``OPS_MART_DATABASE_URL``：本地 PostgreSQL（guangdong_mart / guangdong_sync schema）
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import asyncpg
import pyodbc
import structlog

from app.fetchers.base.fetcher_interface import DataFetcher

logger = structlog.get_logger()

BACKFILL_MONTHS = 24
ORDER_WINDOW = timedelta(days=7)
DETAIL_CODE_CHUNK = 500
LINK_BATCH = 50_000


def _mart_dsn() -> str:
    dsn = os.getenv("OPS_MART_DATABASE_URL", "")
    if not dsn:
        raise RuntimeError(
            "OPS_MART_DATABASE_URL 未配置，guangdong_work_order_fetcher 无法写入本地同步库"
        )
    return dsn


def _ops_connection() -> pyodbc.Connection:
    from config.settings import Settings

    return pyodbc.connect(Settings().ops_sqlserver_connection_string, timeout=60)


def _clean(value: Any) -> Any:
    """pyodbc → asyncpg 兼容值（datetime/str/Decimal 直接可用，其余按需转换）。"""
    if isinstance(value, Decimal):
        return value
    return value


class GuangdongWorkOrderFetcher(DataFetcher):
    """工单 + 明细 + 附件索引 + 站点/设备维表 → 本地 guangdong_mart。"""

    def __init__(self) -> None:
        super().__init__(
            name="guangdong_work_order_fetcher",
            description="广东运维工单同步：SQL Server 源库 → 本地 PostgreSQL guangdong_mart",
            schedule="40 * * * *",
            version="1.0.0",
        )

    # ------------------------------------------------------------------ 入口
    async def fetch_and_store(self) -> None:
        mart = await asyncpg.connect(_mart_dsn(), timeout=10)
        try:
            await self._sync_orders(mart)
            await self._sync_links(mart)
            await self._sync_dimensions(mart)
        finally:
            await mart.close()

    # ------------------------------------------------------------- 工单主链路
    async def _sync_orders(self, mart: asyncpg.Connection) -> None:
        now = datetime.now()
        watermark = await mart.fetchval(
            "SELECT watermark FROM guangdong_sync.sync_watermark WHERE dataset = 'working_orders'"
        )
        if watermark is not None:
            # 水位列是 timestamptz（读回带 tzinfo）；窗口边界统一用 naive 本地时间。
            start: datetime = watermark.astimezone().replace(tzinfo=None)
        else:
            start = now - timedelta(days=BACKFILL_MONTHS * 30)
        end = now
        logger.info(
            "gd_work_order_sync_window",
            start=start.isoformat(),
            end=end.isoformat(),
            backfill=watermark is None,
        )

        total_orders = 0
        total_details = 0
        while start < end:
            window_end = min(start + ORDER_WINDOW, end)
            orders = await asyncio.to_thread(self._fetch_orders, start, window_end)
            if orders:
                codes = [row["working_order_code"] for row in orders if row["working_order_code"]]
                details = await asyncio.to_thread(self._fetch_details, codes)
                await self._write_details(mart, details)
                await self._write_orders(mart, orders)
                total_orders += len(orders)
                total_details += len(details)
            await self._save_watermark(
                mart,
                dataset="working_orders",
                watermark=window_end,
                rows_synced=total_orders,
            )
            start = window_end
        logger.info(
            "gd_work_order_sync_done",
            orders=total_orders,
            details=total_details,
        )

    def _fetch_orders(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        conn = _ops_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT
                    id, working_order_code, station_id, device_id,
                    order_title, order_content, order_type, order_status,
                    urgency_type, maintenance_type, create_time, update_time,
                    finish_time, plan_finish_time, order_overtime, total_overtime,
                    total_expense, workflow_id, current_workflow_point,
                    current_process_status, create_user_id, current_user_id,
                    department_id, contract_id
                FROM dbo.working_orders
                WHERE update_time > ? AND update_time <= ?
                ORDER BY update_time
                """,
                start,
                end,
            )
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            conn.close()

    def _fetch_details(self, codes: Sequence[str]) -> List[Dict[str, Any]]:
        if not codes:
            return []
        conn = _ops_connection()
        all_rows: List[Dict[str, Any]] = []
        try:
            cursor = conn.cursor()
            for offset in range(0, len(codes), DETAIL_CODE_CHUNK):
                chunk = list(codes[offset : offset + DETAIL_CODE_CHUNK])
                placeholders = ", ".join("?" for _ in chunk)
                cursor.execute(
                    f"""
                    SELECT
                        id, working_order_code, process_step,
                        PROCESSTASKID AS process_task_id,
                        process_user_id, process_start_time, process_end_time,
                        process_status, process_time, expense, submit_remark,
                        description_ta, participate_user_ids, dispatch_status,
                        standby_device_code, image_path, alarm_reason
                    FROM dbo.working_order_details
                    WHERE working_order_code IN ({placeholders})
                    """,
                    chunk,
                )
                columns = [column[0] for column in cursor.description]
                all_rows.extend(dict(zip(columns, row)) for row in cursor.fetchall())
            return all_rows
        finally:
            conn.close()

    async def _write_orders(
        self, mart: asyncpg.Connection, orders: Iterable[Dict[str, Any]]
    ) -> None:
        rows = [
            (
                row["id"], row["working_order_code"], row["station_id"], row["device_id"],
                row["order_title"], row["order_content"], row["order_type"], row["order_status"],
                row["urgency_type"], row["maintenance_type"], row["create_time"], row["update_time"],
                row["finish_time"], row["plan_finish_time"], row["order_overtime"],
                row["total_overtime"], row["total_expense"], row["workflow_id"],
                row["current_workflow_point"], row["current_process_status"],
                row["create_user_id"], row["current_user_id"], row["department_id"],
                row["contract_id"],
            )
            for row in orders
        ]
        await mart.executemany(
            """
            INSERT INTO guangdong_mart.working_orders (
                id, working_order_code, station_id, device_id,
                order_title, order_content, order_type, order_status,
                urgency_type, maintenance_type, create_time, update_time,
                finish_time, plan_finish_time, order_overtime, total_overtime,
                total_expense, workflow_id, current_workflow_point,
                current_process_status, create_user_id, current_user_id,
                department_id, contract_id
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24)
            ON CONFLICT (id) DO UPDATE SET
                working_order_code = EXCLUDED.working_order_code,
                station_id = EXCLUDED.station_id,
                device_id = EXCLUDED.device_id,
                order_title = EXCLUDED.order_title,
                order_content = EXCLUDED.order_content,
                order_type = EXCLUDED.order_type,
                order_status = EXCLUDED.order_status,
                urgency_type = EXCLUDED.urgency_type,
                maintenance_type = EXCLUDED.maintenance_type,
                create_time = EXCLUDED.create_time,
                update_time = EXCLUDED.update_time,
                finish_time = EXCLUDED.finish_time,
                plan_finish_time = EXCLUDED.plan_finish_time,
                order_overtime = EXCLUDED.order_overtime,
                total_overtime = EXCLUDED.total_overtime,
                total_expense = EXCLUDED.total_expense,
                workflow_id = EXCLUDED.workflow_id,
                current_workflow_point = EXCLUDED.current_workflow_point,
                current_process_status = EXCLUDED.current_process_status,
                create_user_id = EXCLUDED.create_user_id,
                current_user_id = EXCLUDED.current_user_id,
                department_id = EXCLUDED.department_id,
                contract_id = EXCLUDED.contract_id
            """,
            rows,
        )

    async def _write_details(
        self, mart: asyncpg.Connection, details: Iterable[Dict[str, Any]]
    ) -> None:
        rows = list(details)
        if not rows:
            return
        codes = list({row["working_order_code"] for row in rows if row["working_order_code"]})
        # 明细按工单编码整删重插，保证与源一致（同一工单可能被多窗口触碰）。
        await mart.execute(
            "DELETE FROM guangdong_mart.working_order_details WHERE working_order_code = ANY($1)",
            codes,
        )
        await mart.executemany(
            """
            INSERT INTO guangdong_mart.working_order_details (
                id, working_order_code, process_step, process_task_id,
                process_user_id, process_start_time, process_end_time,
                process_status, process_time, expense, submit_remark,
                description_ta, participate_user_ids, dispatch_status,
                standby_device_code, image_path, alarm_reason
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
            ON CONFLICT (id) DO NOTHING
            """,
            [
                (
                    row["id"], row["working_order_code"], row["process_step"],
                    row["process_task_id"], row["process_user_id"], row["process_start_time"],
                    row["process_end_time"], row["process_status"], row["process_time"],
                    row["expense"], row["submit_remark"], row["description_ta"],
                    row["participate_user_ids"], row["dispatch_status"],
                    row["standby_device_code"], row["image_path"], row["alarm_reason"],
                )
                for row in rows
            ],
        )

    # ------------------------------------------------------------- 附件高水位
    async def _sync_links(self, mart: asyncpg.Connection) -> None:
        highwater = await mart.fetchval(
            "SELECT highwater FROM guangdong_sync.sync_watermark WHERE dataset = 'wo_commonfile_links'"
        )
        last_id = int(highwater or 0)
        max_id = await asyncio.to_thread(self._fetch_max_link_id)
        if max_id is None:
            return
        total = 0
        while last_id < max_id:
            batch_end = min(last_id + LINK_BATCH, max_id)
            rows = await asyncio.to_thread(self._fetch_links, last_id, batch_end)
            if rows:
                await self._write_links(mart, rows)
            total += len(rows)
            last_id = batch_end
            await self._save_watermark(
                mart,
                dataset="wo_commonfile_links",
                highwater=last_id,
                rows_synced=total,
            )
        logger.info("gd_work_order_links_sync_done", links=total, max_id=max_id)

    def _fetch_max_link_id(self) -> Optional[int]:
        conn = _ops_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT MAX(WCFID) FROM dbo.WO_COMMONFILE")
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else None
        finally:
            conn.close()

    def _fetch_links(self, after_id: int, up_to_id: int) -> List[Dict[str, Any]]:
        conn = _ops_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, working_order_code, function_code, type_code,
                       file_name, file_path, create_user_id, create_time
                FROM dbo.wo_commonfile_links
                WHERE id > ? AND id <= ?
                ORDER BY id
                """,
                after_id,
                up_to_id,
            )
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            conn.close()

    async def _write_links(
        self, mart: asyncpg.Connection, rows: Iterable[Dict[str, Any]]
    ) -> None:
        await mart.executemany(
            """
            INSERT INTO guangdong_mart.wo_commonfile_links (
                id, working_order_code, function_code, type_code,
                file_name, file_path, create_user_id, create_time
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (id) DO UPDATE SET
                working_order_code = EXCLUDED.working_order_code,
                function_code = EXCLUDED.function_code,
                type_code = EXCLUDED.type_code,
                file_name = EXCLUDED.file_name,
                file_path = EXCLUDED.file_path,
                create_user_id = EXCLUDED.create_user_id,
                create_time = EXCLUDED.create_time
            """,
            [
                (
                    row["id"], row["working_order_code"], row["function_code"],
                    row["type_code"], row["file_name"], row["file_path"],
                    row["create_user_id"], row["create_time"],
                )
                for row in rows
            ],
        )

    # ------------------------------------------------------------- 维表
    async def _sync_dimensions(self, mart: asyncpg.Connection) -> None:
        stations = await asyncio.to_thread(self._fetch_stations)
        await mart.execute("DELETE FROM guangdong_mart.dim_station")
        if stations:
            await mart.executemany(
                """
                INSERT INTO guangdong_mart.dim_station (
                    station_id, station_code, station_name, region_id,
                    longitude, latitude, address, station_type, status,
                    unique_code, monitor_ip, mapping_station_id,
                    operation_type, description, create_time
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15)
                """,
                [
                    (
                        row["station_id"], row["station_code"], row["station_name"],
                        row["region_id"], row["longitude"], row["latitude"],
                        row["address"], row["station_type"], row["status"],
                        row["unique_code"], row["monitor_ip"], row["mapping_station_id"],
                        row["operation_type"], row["description"], row["create_time"],
                    )
                    for row in stations
                ],
            )

        devices = await asyncio.to_thread(self._fetch_devices)
        await mart.execute("DELETE FROM guangdong_mart.dim_device")
        if devices:
            await mart.executemany(
                """
                INSERT INTO guangdong_mart.dim_device (
                    device_id, device_code, device_type, device_brand,
                    device_model, station_id, device_id_state, pollutant_id,
                    enable_time, activation_time
                ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                """,
                [
                    (
                        row["device_id"], row["device_code"], row["device_type"],
                        row["device_brand"], row["device_model"], row["station_id"],
                        row["device_id_state"], row["pollutant_id"],
                        row["enable_time"], row["activation_time"],
                    )
                    for row in devices
                ],
            )
        await self._save_watermark(
            mart,
            dataset="dim_station_device",
            watermark=datetime.now(),
            rows_synced=len(stations) + len(devices),
        )
        logger.info("gd_dimensions_synced", stations=len(stations), devices=len(devices))

    def _fetch_stations(self) -> List[Dict[str, Any]]:
        conn = _ops_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT STATIONID AS station_id, CODE AS station_code,
                       NAME AS station_name, REGIONID AS region_id,
                       longitude, latitude, address,
                       DDSTATIONTYPE AS station_type, STATUS AS status,
                       UNIQUECODE AS unique_code, MonitorIp AS monitor_ip,
                       MappingStationId AS mapping_station_id,
                       OperationType AS operation_type,
                       DESCRIPTION AS description, CREATETIME AS create_time
                FROM dbo.base_station
                """
            )
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            conn.close()

    def _fetch_devices(self) -> List[Dict[str, Any]]:
        conn = _ops_connection()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DEVICEID AS device_id, DEVICECODE AS device_code,
                       DEVICETYPE AS device_type, DEVICEBRAND AS device_brand,
                       DEVICEMODEL AS device_model, STATIONID AS station_id,
                       DEVICEIDSTATE AS device_id_state, POLLUTANTID AS pollutant_id,
                       ENABLETIME AS enable_time, ACTIVATIONTIME AS activation_time
                FROM dbo.base_device
                """
            )
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            conn.close()

    # ------------------------------------------------------------- 水位
    async def _save_watermark(
        self,
        mart: asyncpg.Connection,
        *,
        dataset: str,
        watermark: Optional[datetime] = None,
        highwater: Optional[int] = None,
        rows_synced: int = 0,
    ) -> None:
        await mart.execute(
            """
            INSERT INTO guangdong_sync.sync_watermark (dataset, watermark, highwater, rows_synced, updated_at)
            VALUES ($1, $2, $3, $4, now())
            ON CONFLICT (dataset) DO UPDATE SET
                watermark = EXCLUDED.watermark,
                highwater = EXCLUDED.highwater,
                rows_synced = EXCLUDED.rows_synced,
                updated_at = now()
            """,
            dataset,
            watermark,
            highwater,
            rows_synced,
        )
