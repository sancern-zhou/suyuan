"""Prepare a preview; apply explicitly immediately before restarting the deployment worker."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--deployment-root',required=True)
    parser.add_argument('--env-file',default='backend/.env')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--preview',action='store_true')
    args=parser.parse_args()
    deployment=Path(args.deployment_root).expanduser().resolve()
    sys.path.insert(0,str(deployment/'backend'))
    from app.utils.path_config import resolve_agent_path,get_data_registry,format_agent_path
    from dotenv import load_dotenv
    env_file=resolve_agent_path(args.env_file)
    load_dotenv(env_file,override=True)
    from app.utils.deployment_preflight import configured_data_registry
    configured_data_registry(env_file)
    from app.scheduled_tasks.models.task import ScheduledTask
    from app.services.station_operation_monitor.runtime import collect,generate_report,load_config
    profile=Path(__file__).resolve().parent
    config=load_config(profile/'config.json')
    definition=ScheduledTask.model_validate_json((profile.parent/'scheduled_tasks/gd_station_operation_daily.json').read_text())
    prepared=get_data_registry()/'station_operation_monitor_prepared'
    prepared.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(profile/'template.docx',prepared/'template.docx')
    config['template_path']=format_agent_path(prepared/'template.docx')
    (prepared/'config.json').write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    (prepared/'task_definition.json').write_text(definition.model_dump_json(indent=2),encoding='utf-8')
    summary={'prepared_config':format_agent_path(prepared/'config.json'),
             'task_definition':format_agent_path(prepared/'task_definition.json'),
             'schedule':'每天北京时间10:30','collection_schedule':'每小时25分','applied':False}
    if args.preview:
        result=collect(config,root=prepared/'preview')
        summary['collection']=result
        summary['report']=generate_report(config,root=prepared/'preview',refresh=True)
    if args.apply:
        # Run with the deployment worker stopped to avoid concurrent JSON task-store writes.
        from app.scheduled_tasks.storage.task_storage import TaskStorage
        runtime=get_data_registry()/'station_operation_monitor'
        runtime.mkdir(parents=True,exist_ok=True)
        config_file=runtime/'config.json'
        if not config_file.exists():
            temp=runtime/'config.json.new'
            shutil.copyfile(profile/'template.docx',runtime/'template.docx')
            applied_config=dict(config,template_path=format_agent_path(runtime/'template.docx'))
            temp.write_text(json.dumps(applied_config,ensure_ascii=False,indent=2),encoding='utf-8')
            temp.replace(config_file)
        storage=TaskStorage()
        if storage.get(definition.task_id) is None:
            if storage.tasks_file.exists():
                backup=prepared/('tasks.before-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')
                shutil.copyfile(storage.tasks_file,backup)
            storage.create(definition)
        summary['applied']=True
        summary['task_id']=definition.task_id
        summary['runtime_config']=format_agent_path(config_file)
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    main()
