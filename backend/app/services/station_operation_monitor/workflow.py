"""Fixed station daily report workflow; no Agent or language model execution."""
from __future__ import annotations

import asyncio
import json

from pydantic import BaseModel, ConfigDict

from app.utils.path_config import resolve_agent_path, format_agent_path

WORKFLOW_NAME = 'station_operation_daily_report'


class ReportArguments(BaseModel):
    model_config = ConfigDict(extra='forbid')
    date: str | None = None


async def run_daily_report(task, execution):
    from .runtime import generate_report, load_config
    from .word import render_pdf_preview
    from app.tools.resource_declarations import generated_file_products
    from app.agent.resources.resource_service import SessionResourceService
    from app.agent.resources.runtime import persist_tool_result_resources
    from app.agent.session import Session, get_session_manager
    from app.scheduled_tasks.conversation_persistence import ScheduledTaskConversationPersistence

    args = ReportArguments.model_validate(task.workflow_args or {})
    config = dict(load_config(), strict_template=True)
    if not config.get('template_path') or not config.get('template_sha256'):
        raise ValueError('固定日报工作流需要指定模板及模板版本')
    result = await asyncio.to_thread(generate_report, config, date=args.date)
    if not result['report_ready']:
        raise ValueError('日报取数不完整，未发布正式报告；请检查原始快照及取数记录')
    validation_path = resolve_agent_path(result['format_validation_path'])
    validation = json.loads(validation_path.read_text(encoding='utf-8'))
    if not validation.get('passed') or not validation.get('checks', {}).get('fixed_content'):
        raise ValueError('固定日报模板验收失败，未发布报告')
    word = resolve_agent_path(result['word_path'])
    pdf = await asyncio.to_thread(render_pdf_preview, word)
    result['pdf_path'] = format_agent_path(pdf)
    declarations = generated_file_products([word], tool_name=WORKFLOW_NAME,
                                            preview_paths={str(word):pdf})
    message = (f"站点运行日报已生成，共{result['incident_count']}条缺失记录。"
               f"监控国控{result['station_counts']['国控']}个、省控{result['station_counts']['省控']}个站点。"
               f"另有{result['unverified_station_count']}个候选站点在运状态待核实。")
    persistence = ScheduledTaskConversationPersistence()
    session = Session(session_id=execution.session_id, query=task.description,
                      created_at=execution.started_at,
                      conversation_history=[{'type':'user','content':task.description},
                          {'type':'final','role':'assistant','content':message,'data':{'answer':message}}],
                      metadata={'mode':'report','scheduled_task_id':task.task_id,
                                'scheduled_execution_id':execution.execution_id,
                                'scheduled_task_name':task.name})
    manager = get_session_manager()
    if not await manager.replace_session_transcript(session):
        raise RuntimeError('日报会话保存失败')
    publication = await persist_tool_result_resources(
        SessionResourceService.database(), execution.session_id, execution.execution_id,
        {'type':'tool_result','data':{'tool_name':WORKFLOW_NAME,
                                    'result':{'success':True,'resources':declarations}}}, turn_sequence=1)
    if publication is None or len(publication.changed_resource_ids) != 2:
        raise RuntimeError('日报资源注册失败')
    from app.conversations.schemas import ConversationSource
    await persistence.catalog.register_identity(
        session_id=execution.session_id, owner_user_id=task.owner_user_id,
        owner_username=task.owner_username, owner_display_name=task.owner_display_name,
        source=ConversationSource.WEB, mode='report', title=task.name, read_only_on_web=False)
    manifest = {'workflow':WORKFLOW_NAME,'version':'1','llm_calls':0,
                'phases':['collect_compute','fill_template','validate','render_pdf','publish_resources'],
                'result':result,'resource_ids':publication.changed_resource_ids}
    word.with_suffix('.workflow.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'summary':message,'final_message':message,
            'tool_call_details':{'conversation_available':True,'media':[str(word),str(pdf)],'result':{
                'success':True,'data':result,'resources':declarations}}}


def register_daily_report_workflow():
    from app.scheduled_tasks.workflow_tasks import register_workflow_handler
    register_workflow_handler(WORKFLOW_NAME, run_daily_report, version='1',
                              description='取数计算、固定模板填充、验收、PDF及会话资源发布；无需LLM。')
