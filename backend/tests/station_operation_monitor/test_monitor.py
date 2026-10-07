from datetime import datetime,timedelta

import pytest

from app.services.station_operation_monitor.core import MonitorStore, hours, local_time, normalize, parse_value
from app.services.station_operation_monitor.runtime import collect, generate_report


BASE=local_time('2026-10-06T10:00:00')
ROSTER=[{'code':'A','name':'一站','city':'测试市','type':'国控','confirmed':True,'active':True},
        {'code':'B','name':'二站','city':'测试市','type':'省控','confirmed':True,'active':True},
        {'code':'OLD','name':'旧站','city':'测试市','type':'国控'}]


def rows(start,end,codes=('A','B'),missing=()):
    return [{'code':code,'timePoint':hour,'sO2':'7(H)','nO2':'0','pM10':'11(Re)',
             'co':'0.4','o3':'30','pM2_5':'8'} for code in codes for hour in hours(start,end)
            if (code,hour) not in missing]


def ingest(store,start,end,records,source='primary',observed=None,**kwargs):
    store.ingest(source=source,city='测试市',start=start,end=end,records=records,
                 observed_at=observed or end+timedelta(minutes=30),**kwargs)


def report(store,end):
    return store.report(end,national_sources=['primary','secondary'],provincial_source='primary')


def test_hour_grid_and_quality_flags():
    assert len(list(hours(BASE,BASE+timedelta(days=1))))==24
    assert parse_value('7(H)')==(7,'H')
    assert parse_value('0')==(0,None)
    assert parse_value('-99')[0] is None
    assert parse_value('—')[0] is None
    r=normalize(rows(BASE,BASE+timedelta(hours=1))[0])
    assert r['present'] and not r['quality_complete']
    assert r['marks']['sO2']=='H' and r['marks']['pM10']=='Re'


def test_failure_does_not_create_offline_and_old_stations_not_active(tmp_path):
    store=MonitorStore(tmp_path/'state.sqlite');store.seed(ROSTER)
    end=BASE+timedelta(days=1)
    ingest(store,BASE,end,rows(BASE,end))
    ingest(store,BASE,end,[],success=False,detail='timeout')
    r=report(store,end)
    assert not r['entries']
    assert not r['report_ready']
    assert [s['code'] for s in r['unverified_stations']]==['OLD']


def test_cross_day_recovery_does_not_imply_backfill(tmp_path):
    store=MonitorStore(tmp_path/'state.sqlite');store.seed(ROSTER)
    missing_hours=list(hours(BASE,BASE+timedelta(hours=5)))
    absent={('A',h) for h in missing_hours}
    end=BASE+timedelta(days=1)
    ingest(store,BASE,end,rows(BASE,end,missing=absent))
    entry=report(store,end)['entries'][0]
    assert entry['affected_hours']==5 and entry['recovered']
    assert entry['backfill_status']=='待回补'
    # More than the immediately preceding day must remain visible until closure.
    next_end=end+timedelta(days=3)
    ingest(store,next_end-timedelta(days=1),next_end,rows(next_end-timedelta(days=1),next_end))
    entry=report(store,next_end)['entries'][0]
    assert entry['carry_over'] and entry['window_affected_hours']==0
    assert entry['backfill_status']=='待回补'


def test_either_source_must_fill_entire_gap_not_mixed_hours(tmp_path):
    store=MonitorStore(tmp_path/'state.sqlite');store.seed(ROSTER)
    end=BASE+timedelta(days=1)
    absent={('A',h) for h in list(hours(BASE,BASE+timedelta(hours=5)))}
    ingest(store,BASE,end,rows(BASE,end,missing=absent))
    # Fill only three of five through second source: still pending.
    ingest(store,BASE,BASE+timedelta(hours=3),rows(BASE,BASE+timedelta(hours=3),codes=('A',)),
           source='secondary',station_types=['国控'],observed=end+timedelta(minutes=31))
    assert report(store,end)['entries'][0]['backfill_status']=='待回补'
    ingest(store,BASE,end,rows(BASE,end,codes=('A',)),source='secondary',station_types=['国控'],
           observed=end+timedelta(minutes=32))
    entry=report(store,end)['entries'][0]
    assert entry['backfill_status']=='已回补' and entry['backfill_sources']==['secondary']
    # Originally observed evidence survives the fill.
    assert entry['affected_hours']==5


def test_stale_recheck_cannot_erase_later_backfill(tmp_path):
    store=MonitorStore(tmp_path/'state.sqlite');store.seed(ROSTER)
    end=BASE+timedelta(days=1)
    ingest(store,BASE,end,[],observed=end+timedelta(minutes=20))
    ingest(store,BASE,end,rows(BASE,end),observed=end+timedelta(minutes=30))
    ingest(store,BASE,end,[],observed=end+timedelta(minutes=25))
    entry=report(store,end)['entries'][0]
    assert entry['backfill_status']=='已回补' and entry['recovered']


def test_four_hours_excluded_five_included(tmp_path):
    store=MonitorStore(tmp_path/'state.sqlite');store.seed(ROSTER)
    end=BASE+timedelta(days=1)
    missing={('A',h) for h in hours(BASE,BASE+timedelta(hours=4))}
    missing.update(('B',h) for h in hours(BASE,BASE+timedelta(hours=5)))
    ingest(store,BASE,end,rows(BASE,end,missing=missing))
    assert [e['code'] for e in report(store,end)['entries']]==['B']


class FakeSource:
    calls=[]
    def __init__(self,config):pass
    def fetch(self,codes,start,end):
        self.calls.append((codes,start,end))
        return rows(start,end,codes=[c for c in codes if c!='OLD'])


def config():
    return {'stations':ROSTER,'sources':[{'name':'primary'}],
            'national_sources':['primary'],'provincial_source':'primary','bootstrap_hours':48}


def test_collector_slicing_raw_preservation_and_word(tmp_path):
    now=BASE+timedelta(days=1,minutes=30)
    result=collect(config(),now=now,root=tmp_path,source_factory=FakeSource)
    assert result['success']
    assert len(list((tmp_path/'snapshots').rglob('*.json.gz')))>=2
    r=generate_report(config(),now=now,root=tmp_path,refresh=False)
    assert r['report_ready'] and r['unverified_station_count']==1
    from docx import Document
    content='\n'.join(p.text for p in Document(r['word_path']).paragraphs)
    assert '独立发布源未接入' in content
    assert '无记录候选站点' in content


def test_arrival_grace_and_future_window_rejected(tmp_path):
    with pytest.raises(ValueError):
        collect(config(),now=BASE+timedelta(minutes=10),end=BASE,root=tmp_path,source_factory=FakeSource)
    with pytest.raises(ValueError):
        generate_report(config(),now=BASE,root=tmp_path,refresh=False)


def test_partial_return_recovers_transmission_but_not_all_missing_data(tmp_path):
    store=MonitorStore(tmp_path/'state.sqlite');store.seed(ROSTER)
    end=BASE+timedelta(days=1)
    absent={('B',h) for h in hours(BASE,BASE+timedelta(hours=5))}
    ingest(store,BASE,end,rows(BASE,end,missing=absent))
    partial=rows(BASE,end)
    for record in partial:
        if record['code']=='B':record['co']='—'
    ingest(store,BASE,end,partial,observed=end+timedelta(minutes=40))
    entry=report(store,end)['entries'][0]
    assert entry['recovered'] and entry['backfill_status']=='待回补'


def test_malformed_response_not_persisted_as_station_outage(tmp_path):
    class Malformed(FakeSource):
        def fetch(self,codes,start,end):
            return [{'code':'A','timePoint':'not-a-time'}]
    result=collect(config(),now=BASE+timedelta(days=1,minutes=30),root=tmp_path,source_factory=Malformed)
    assert not result['success']
    store=MonitorStore(tmp_path/'monitor.sqlite3')
    assert not report(store,BASE+timedelta(days=1))['entries']


def test_http_empty_and_truncated_response_are_not_accepted():
    from app.services.station_operation_monitor.runtime import StationHourHTTPSource
    class Response:
        status_code=200
        def raise_for_status(self):pass
        def json(self):return {'success':True,'result':[]}
    class Session:
        def post(self,*args,**kwargs):return Response()
    source=StationHourHTTPSource({'base_url':'https://example.invalid','hour_endpoint':'/hours'})
    source.token='test';source.session=Session()
    with pytest.raises(RuntimeError,match='empty'):
        source.fetch(['A'],BASE,BASE+timedelta(hours=1))


def test_report_no_observations_is_incomplete(tmp_path):
    store=MonitorStore(tmp_path/'state.sqlite');store.seed(ROSTER)
    r=report(store,BASE+timedelta(days=1))
    assert not r['report_ready'] and not r['entries']


@pytest.mark.asyncio
async def test_fetcher_propagates_collection_failure(monkeypatch):
    from app.fetchers import station_operation_monitor as module
    monkeypatch.setattr(module,'load_config',lambda:{'collection_cron':'25 * * * *'})
    monkeypatch.setattr(module,'collect',lambda:{'success':False,'failed_slices':[{}]})
    fetcher=module.StationOperationMonitorFetcher()
    assert fetcher.schedule=='25 * * * *'
    with pytest.raises(RuntimeError):
        await fetcher.fetch_and_store()


def test_cross_day_secondary_backfill_is_reported_on_observation_day(tmp_path):
    store=MonitorStore(tmp_path/'state.sqlite');store.seed(ROSTER)
    end=BASE+timedelta(days=1)
    absent={('A',h) for h in hours(BASE,BASE+timedelta(hours=5))}
    ingest(store,BASE,end,rows(BASE,end,missing=absent))
    next_end=end+timedelta(days=2)
    ingest(store,next_end-timedelta(days=1),next_end,rows(next_end-timedelta(days=1),next_end))
    ingest(store,BASE,end,rows(BASE,end,codes=('A',)),source='secondary',station_types=['国控'],
           observed=next_end+timedelta(minutes=30))
    entry=report(store,next_end)['entries'][0]
    assert entry['backfill_status']=='已回补' and entry['carry_over']


def test_unrecoverable_requires_attributable_confirmation(tmp_path):
    store=MonitorStore(tmp_path/'monitor.sqlite3');store.seed(ROSTER)
    end=BASE+timedelta(days=1)
    absent={('B',h) for h in hours(BASE,BASE+timedelta(hours=5))}
    ingest(store,BASE,end,rows(BASE,end,missing=absent))
    cfg=config()
    confirmation={'code':'B','start':BASE.isoformat(),'end':(BASE+timedelta(hours=5)).isoformat(),
                  'reason':'原始记录丢失','confirmed_by':'运维核实','confirmed_at':end.isoformat()}
    cfg['unrecoverable_confirmations']=[confirmation]
    r=generate_report(cfg,now=end+timedelta(minutes=30),root=tmp_path,refresh=False)
    import json
    assert json.load(open(r['report_input_path']))['entries'][0]['backfill_status']=='待回补'
    confirmation['evidence']='工单TEST-001的核实记录'
    r=generate_report(cfg,now=end+timedelta(minutes=30),root=tmp_path,refresh=False)
    assert json.load(open(r['report_input_path']))['entries'][0]['backfill_status']=='无法回补'


def test_pending_rechecks_skip_already_filled_intervals(tmp_path):
    store=MonitorStore(tmp_path/'state.sqlite');store.seed(ROSTER)
    end=BASE+timedelta(days=1)
    absent={('B',h) for h in hours(BASE,BASE+timedelta(hours=2))}
    absent.update(('B',h) for h in hours(BASE+timedelta(hours=20),BASE+timedelta(hours=22)))
    ingest(store,BASE,end,rows(BASE,end,missing=absent))
    intervals=store.pending_hours()
    assert len(intervals)==2
    assert all(local_time(i['end'])-local_time(i['start'])==timedelta(hours=1) for i in intervals)
