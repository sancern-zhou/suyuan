@echo off
rem Daily job 02:30: dict/full refresh + �ֵ��SCD2���� + daily marts + reconciliation + DQ
rem   dbt ��(2026-10-02): dbt snapshot �� 19 ���ֵ�/����������й�ϣ������
rem   (alm_rule �޸���ʱ���е������Դ��н�: �����ʷ�� jiangsu_snapshot.alm_rule)
rem   dbt build tag:daily: dim_device/�ոſ�/�ʿذ���/�¶ȿ���/ͣ����(�����ݲ���)
cd /d E:\Tools\suyuan-jiangsu\sync
set FULLLIST=opa_user_info bsd_device bsd_devicetype qc_task bsd_city qc_arrangeresult qc_historymonthresultoverview pw_task opa_performance_tworate opa_performance_qaqc opa_qcqa_deduction mtc_blackout mtc_dataentry mtc_dataentry_data mtc_fault wo_commonfile log_device qc_backorderarrangelog bsd_supply bsd_moniter_parameter dev_scrap bsd_region bsd_usergroup bsd_usergroup_user bsd_usergroup_station bsd_usergroup_station_devicetype bsd_maintenanceunit mtc_faultcontent mtc_faultcontentitem alm_rule wfl_workflow wfl_workflowtask rf_ruleitem qa_standardmaterialstorage
for %%t in (%FULLLIST%) do (
    E:\Tools\Python311\python.exe sync_table.py %%t --full >> sync_%%t.log 2>&1
)
rem վ������Сʱ��Ƭ��(integrated_h_2026_*, 100վ): ��������(�״��Զ�ȫ������2026-10��)
echo [%date% %time%] env hourly shards begin >> sync_integrated_env.log 2>&1
E:\Tools\Python311\python.exe sync_env_hourly.py >> sync_integrated_env.log 2>&1
echo [%date% %time%] env hourly shards exit=%errorlevel% >> sync_integrated_env.log
echo [%date% %time%] dbt snapshot + build tag:daily >> sync_mart.log 2>&1
rem PYTHONUTF8=1: dbt �� UTF-8 ��������ע�͵�ģ���ļ�(�ƻ�����Ĭ�� GBK �� UnicodeDecodeError)
set "PYTHONUTF8=1"
E:\Tools\suyuan-jiangsu\dbt-venv\Scripts\dbt.exe snapshot --project-dir E:\Tools\suyuan-jiangsu\dbt --profiles-dir E:\Tools\suyuan-jiangsu\dbt --no-use-colors >> sync_mart.log 2>&1
echo [%date% %time%] dbt snapshot exit=%errorlevel% >> sync_mart.log
E:\Tools\suyuan-jiangsu\dbt-venv\Scripts\dbt.exe build --project-dir E:\Tools\suyuan-jiangsu\dbt --profiles-dir E:\Tools\suyuan-jiangsu\dbt --select tag:daily --no-use-colors >> sync_mart.log 2>&1
echo [%date% %time%] dbt build tag:daily exit=%errorlevel% >> sync_mart.log
rem dbt ʧ��ʱ�üƻ����� LastTaskResult �� 0(dq �� SLA �澯Ҫ����ŷ���, �˳��뵱���ɼ�)
if not "%errorlevel%"=="0" exit /b %errorlevel%
set CHECKLIST=mtc_working_order mtc_working_order_detail alm_summary opa_kq_attendance bsd_station mot_alarm opa_user_info bsd_device bsd_devicetype qc_task bsd_city qc_his_result_2026 qc_arrangeresult qc_historymonthresultoverview pw_taskitem mtc_taskitem pw_task opa_performance_tworate opa_performance_qaqc opa_qcqa_deduction mtc_blackout mtc_dataentry mtc_dataentry_data mtc_fault wo_commonfile log_device qc_backorderarrangelog bsd_supply bsd_moniter_parameter dev_scrap bsd_region bsd_usergroup bsd_usergroup_user bsd_usergroup_station bsd_usergroup_station_devicetype bsd_maintenanceunit mtc_faultcontent mtc_faultcontentitem alm_rule wfl_workflow qa_standardmaterialstorage
for %%t in (%CHECKLIST%) do (
    E:\Tools\Python311\python.exe sync_table.py %%t --check >> sync_check.log 2>&1
)
rem �����������(���ʶ�/��ֵ/ͬ������/��ԼƯ��), ����� jiangsu_sync.dq_results
rem ODS 兜底通道: 每日重授一次 agent_reader 的 SELECT(幂等), 新增同步表不用手工授权
E:\Tools\Python311\python.exe gen_ods_fallback_contract.py --grant >> sync_mart.log 2>&1
E:\Tools\Python311\python.exe dq_check.py >> sync_dq.log 2>&1
