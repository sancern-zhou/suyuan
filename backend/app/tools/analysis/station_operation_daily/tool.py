from __future__ import annotations

import asyncio

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.resource_declarations import generated_file_products
from app.utils.path_config import resolve_agent_path


class StationOperationDailyTool(LLMTool):
    def __init__(self):
        super().__init__(
            name='station_operation_daily',
            description='抓取站点原始小时数据并确定性计算运行状态，生成昨日10时至今日10时的Word日报，跟进历史未结记录。',
            category=ToolCategory.ANALYSIS,
            requires_context=False,
            function_schema={
                'name': 'station_operation_daily',
                'description': '使用部署配置的站点名录及小时接口，保存原始快照，计算小时数据缺失、恢复、回补并生成日报。不得把缺数直接解释成设备故障。',
                'parameters': {'type':'object','properties': {
                    'action': {'type':'string','enum':['collect','report'],'default':'report'},
                    'date': {'type':'string','description':'可选报告日期YYYY-MM-DD；默认北京时间今天'},
                }},
            },
        )

    async def execute(self, action='report', date=None, **kwargs):
        from app.services.station_operation_monitor.runtime import collect, generate_report
        try:
            if action == 'collect':
                result = await asyncio.to_thread(collect)
            elif action == 'report':
                result = await asyncio.to_thread(generate_report, date=date)
                result['resources'] = generated_file_products(
                    [resolve_agent_path(result['word_path'])], tool_name=self.name)
            else:
                raise ValueError('unsupported action')
            return {'success':result['success'], 'data':result,
                    'summary': '日报已生成' if result.get('report_ready') else '采集完成或已生成待核实报告，请查看取数状态及说明'}
        except Exception as exc:
            # Config/network exceptions can contain secret material; expose only their class.
            return {'success':False,'data':{'error_type':type(exc).__name__},
                    'summary':'站点运行监控执行失败，请检查部署配置、日志及接口状态。'}
