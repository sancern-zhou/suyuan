from __future__ import annotations

import asyncio

from app.tools.base.tool_interface import LLMTool, ToolCategory
from app.tools.resource_declarations import generated_file_products
from app.utils.path_config import resolve_agent_path


class StationOperationDailyTool(LLMTool):
    def __init__(self):
        super().__init__(
            name='station_operation_daily',
            description='抓取站点原始小时数据并确定性计算运行状态，仅对连续缺数超过4小时的事件生成昨日10时至今日10时的Word日报；数据恢复上传即结束跟进，已恢复事件仅记录过去24小时的缺失，持续未恢复上传事件继续跟进，不设天数上限。',
            category=ToolCategory.ANALYSIS,
            requires_context=False,
            function_schema={
                'name': 'station_operation_daily',
                'description': '使用部署配置的站点名录及小时接口，保存原始快照，仅将连续缺数超过4小时的事件记入日报；数据恢复上传即结束跟进（回补仅作备注），已恢复事件超过24小时窗口不再跟进，持续未恢复上传事件不设跟进天数上限。action=record_feedback 用于用户在对话中反馈缺失原因/是否无法回补时，记录原因到日报排查结果并关闭该事件跟进。不得把缺数直接解释成设备故障。',
                'parameters': {'type':'object','properties': {
                    'action': {'type':'string','enum':['collect','report','record_feedback'],'default':'report'},
                    'date': {'type':'string','description':'可选报告日期YYYY-MM-DD；默认北京时间今天'},
                    'station': {'type':'string','description':'站点编码或站点名称（record_feedback必填）'},
                    'reason': {'type':'string','description':'用户反馈的缺失原因（record_feedback必填）'},
                    'unrecoverable': {'type':'boolean','description':'是否无法回补，按用户明确表述（record_feedback必填）'},
                    'start': {'type':'string','description':'缺失开始时间，可选，ISO格式'},
                    'end': {'type':'string','description':'缺失结束时间，可选，ISO格式'},
                    'feedback_by': {'type':'string','description':'反馈人姓名或标识，可选'},
                }},
            },
        )

    async def execute(self, action='report', date=None, station=None, reason=None,
                      unrecoverable=None, start=None, end=None, feedback_by=None, **kwargs):
        from app.services.station_operation_monitor.runtime import collect, generate_report
        try:
            resources = []
            if action == 'collect':
                result = await asyncio.to_thread(collect)
            elif action == 'report':
                result = await asyncio.to_thread(generate_report, date=date)
                from app.services.station_operation_monitor.word import render_pdf_preview
                from app.utils.path_config import format_agent_path
                word_path = resolve_agent_path(result['word_path'])
                pdf_path = await asyncio.to_thread(render_pdf_preview, word_path)
                result['pdf_path'] = format_agent_path(pdf_path)
                resources = generated_file_products(
                    [word_path], tool_name=self.name, preview_paths={str(word_path):pdf_path})
            elif action == 'record_feedback':
                if not station or not str(reason or '').strip() or unrecoverable is None:
                    raise ValueError('record_feedback 需要station、reason、unrecoverable参数，请先向用户确认')
                from app.services.station_operation_monitor.feedback import record_feedback
                result = await asyncio.to_thread(
                    record_feedback, station=station, reason=reason, unrecoverable=unrecoverable,
                    start=start, end=end, feedback_by=feedback_by)
            else:
                raise ValueError('unsupported action')
            if action == 'record_feedback':
                summary = (f"已记录反馈并关闭跟进：{result['record']['name']}站"
                           + ('' if result['matched_events'] else '；未匹配到未结缺数区间，请与用户核对时段'))
            else:
                summary = '日报已生成' if result.get('report_ready') else '采集完成或已生成待核实报告，请查看取数状态及说明'
            return {'success':result.get('success', True), 'data':result, 'resources':resources, 'summary':summary}
        except ValueError as exc:
            return {'success':False, 'data':{'error':str(exc)}, 'summary':str(exc)}
        except Exception as exc:
            # Config/network exceptions can contain secret material; expose only their class.
            return {'success':False,'data':{'error_type':type(exc).__name__},
                    'summary':'站点运行监控执行失败，请检查部署配置、日志及接口状态。'}
