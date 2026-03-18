from datetime import datetime, timedelta

import pytest

from app.agent.context.data_context_manager import DataContextManager
from app.agent.context.execution_context import ExecutionContext
from app.agent.memory.hybrid_manager import HybridMemoryManager
from app.tools.analysis.smart_chart_generator.tool import SmartChartGenerator


def _build_sample_guangdong_records():
    base_time = datetime(2025, 11, 10, 0, 0)
    records = []
    stations = ["肇庆站1", "肇庆站2", "肇庆站3"]
    for idx, station in enumerate(stations):
        for hour in range(6):
            time_point = (base_time + timedelta(hours=hour)).strftime("%Y-%m-%d %H:%M:%S")
            records.append(
                {
                    "station_name": station,
                    "time_point": time_point,
                    "measurements": {
                        "pM2_5": 30 + idx * 5 + hour,
                        "pM10": 60 + idx * 3,
                        "pO3": 90 + hour,
                    },
                }
            )
    return records


@pytest.mark.asyncio
async def test_guangdong_stations_data_id_end_to_end():
    """
    端到端验证：保存广东站点数据 → 调用 smart_chart_generator → 拿到 chart_config data_id。

    使用真实的 DataContextManager + ExecutionContext，确保 data_id 流程打通。
    """

    session_id = "test_session_guangdong_chart"
    hybrid_manager = HybridMemoryManager(session_id=session_id)
    data_manager = DataContextManager(hybrid_manager)
    context = ExecutionContext(
        session_id=session_id,
        iteration=1,
        data_manager=data_manager,
    )

    # 1. 保存广东站点样例数据，获取 data_id
    guangdong_records = _build_sample_guangdong_records()
    source_data_id = context.save_data(
        data=guangdong_records,
        schema="guangdong_stations",
        metadata={"source": "unit_test"},
    )

    assert source_data_id.startswith("guangdong_stations:")

    # 2. 调用 smart_chart_generator 生成 timeseries 图表
    tool = SmartChartGenerator()
    result = await tool.execute(
        context=context,
        data_id=source_data_id,
        chart_type="timeseries",
        title="广东站点PM2.5趋势",
        options={"top_n": 5},
    )

    assert result["success"] is True
    chart_payload = result["data"]
    assert chart_payload["type"] == "timeseries"
    assert chart_payload["meta"]["data_source"] == "smart_chart_generator"
    assert chart_payload["meta"]["original_data_id"] == source_data_id
    assert chart_payload["data"]["data"]["series"], "series 数据不能为空"

    # 3. 校验 ChartConfig 已保存并可重新加载
    chart_data_id = result["metadata"]["data_id"]
    assert chart_data_id.startswith("chart_config:")

    saved_chart_data = context.get_data(chart_data_id, expected_schema="chart_config")
    assert saved_chart_data, "保存的 chart_config 不应为空"
    saved_chart = saved_chart_data[0]
    assert saved_chart.chart_type == "timeseries"
    assert saved_chart.metadata["source_data_id"] == source_data_id
