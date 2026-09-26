"""Render merged alert facts and one interactive GIS timeline per pollutant."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

from app.utils.path_config import resolve_agent_path


def build_report_from_evidence(
    manifest_path: str, agent_text: dict[str, Any], *, amap_key: str | None = None
) -> str:
    manifest_file = resolve_agent_path(manifest_path)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if amap_key is None:
        config_path = manifest.get("render_config_path")
        if not config_path:
            raise ValueError("Missing render_config_path; regenerate the evidence package")
        config = json.loads(resolve_agent_path(config_path).read_text(encoding="utf-8"))
        amap_key = config.get("public_key") or ""
    if not amap_key:
        raise ValueError("AMAP_PUBLIC_KEY is required for the real map")
    files = manifest.get("evidence_files") or {}
    required = {"event_brief", "pollutant_maps", "provenance"}
    if not required.issubset(files):
        raise ValueError(f"Missing evidence files: {sorted(required - files.keys())}; regenerate the evidence package")
    event_data = json.loads(resolve_agent_path(files["event_brief"]).read_text(encoding="utf-8"))
    map_data = json.loads(resolve_agent_path(files["pollutant_maps"]).read_text(encoding="utf-8"))
    provenance = json.loads(resolve_agent_path(files["provenance"]).read_text(encoding="utf-8"))
    events = event_data.get("events") or []
    maps = map_data.get("maps") or []
    if len(events) != event_data.get("event_count") or len(events) != manifest.get("episode_count"):
        raise ValueError("Merged event counts disagree between manifest and evidence")
    if len(maps) != map_data.get("pollutant_count") or {m["pollutant"] for m in maps} != {e["pollutant"] for e in events}:
        raise ValueError("Pollutant maps do not match merged events")
    analyses = agent_text.get("event_analysis") or {}
    for event in events:
        value = analyses.get(event["event_id"])
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing Agent event analysis for {event['event_id']}")
    if not isinstance(agent_text.get("conclusion"), str) or not agent_text["conclusion"].strip():
        raise ValueError("Agent conclusion is required")
    return build_html_report({
        "target_date": manifest["target_date"], "events": events, "maps": maps,
        "summary_text": agent_text.get("summary_text") or "", "event_analysis": analyses,
        "conclusion": agent_text["conclusion"], "method": event_data.get("method") or "",
        "provenance": provenance.get("source_provenance") or {},
    }, amap_key=amap_key)


def _text(value: Any) -> str:
    return html.escape(str(value), quote=True) if value is not None else "—"


def _number(value: Any) -> str:
    return "—" if value is None else f"{float(value):g}"


def _time(value: Any) -> str:
    return str(value or "—").replace("T", " ")[:16]


def _alert_times(event: dict[str, Any]) -> str:
    intervals = event.get("alert_intervals") or [{
        "start_time": event.get("start_time"), "end_time": event.get("end_time"),
    }]
    return "、".join(
        f"{_time(item.get('start_time'))}—{_time(item.get('end_time'))}"
        for item in intervals
    )


def _comparison(item: dict[str, Any]) -> str:
    direction = item.get("vs_target") or "无法对比"
    if direction == "无法对比":
        return direction
    target = _number(item.get("target_comparison_mean"))
    if item.get("comparable_hours") != item.get("valid_hours"):
        station = _number(item.get("comparison_concentration_mean"))
        return f"{direction}国控点（同期本站{station}、国控点{target}）"
    return f"{direction}国控点（同期{target}）"


def _wind_text(event: dict[str, Any]) -> str:
    wind = event.get("wind") or {}
    if wind.get("status") != "ok":
        return "风向数据不足"
    return (f"{_text(wind.get('direction_name'))}风（{_number(wind.get('direction_deg'))}°，"
            f"有效{_text(wind.get('valid_hours'))}小时）")


def _comparison_table(event: dict[str, Any], unit: str) -> str:
    target_row = "<tr>" + "".join(f"<td>{_text(x)}</td>" for x in (
        "国控点", event.get("station_name"), "—", "—", _number(event.get("target_mean")), "—",
    )) + "</tr>"
    neighbor_rows = "".join("<tr>" + "".join(f"<td>{_text(x)}</td>" for x in (
        "上风向乡镇站", item.get("station_name"), _number(item.get("distance_km")),
        item.get("bearing_name"), _number(item.get("concentration_mean")), _comparison(item),
    )) + "</tr>" for item in event.get("upwind_township_stations") or [])
    if not neighbor_rows:
        neighbor_rows = '<tr><td colspan="6">无符合风向、坐标和有效浓度条件的上风向乡镇站。</td></tr>'
    return (
        "<div class='table-scroll'><table class='comparison-table'><thead><tr>"
        "<th>类型</th><th>站名</th><th>距离(km)</th><th>方位</th>"
        f"<th>浓度({unit})</th><th>对比</th></tr></thead>"
        f"<tbody>{target_row}{neighbor_rows}</tbody></table></div>"
    )


def build_html_report(payload: dict[str, Any], *, amap_key: str) -> str:
    events = payload.get("events") or []
    maps = payload.get("maps") or []
    analysis = payload.get("event_analysis") or {}
    rows = []
    by_station_pollutant: dict[tuple[str, str], list[str]] = {}
    station_names: dict[tuple[str, str], str] = {}
    for event in events:
        pollutant = str(event["pollutant"])
        proxy_note = "（NO₂小时浓度代理）" if pollutant == "NOX" else ""
        unit = "mg/m³" if pollutant == "CO" else "μg/m³"
        ratio = event.get("peak_rise_percent")
        change = f"{_number(event.get('start_concentration'))} → {_number(event.get('peak_concentration'))}"
        cells = (event.get("station_name"), pollutant,
                 _alert_times(event), change,
                 f"{ratio:g}%" if ratio is not None else "—", _number(event.get("peak_rise_absolute")))
        rows.append("<tr>" + "".join(f"<td>{_text(x)}</td>" for x in cells) + "</tr>")
        segments = event.get("segments") or []
        if segments:
            segment_html = []
            for number, segment in enumerate(segments, 1):
                segment_ratio = segment.get("peak_rise_percent")
                segment_change = (f"{_number(segment.get('start_concentration'))} → "
                                  f"{_number(segment.get('peak_concentration'))}")
                segment_html.append(
                    f"<div class='segment'><h5>第{number}段｜{_text(_alert_times(segment))}</h5>"
                    f"<p>浓度{proxy_note}：{_text(segment_change)} {unit}；"
                    f"峰值时间：{_text(_time(segment.get('peak_time')))}；"
                    f"峰值较{_text(segment.get('reference_kind') or '参考小时')}变化 "
                    f"{_number(segment.get('peak_rise_absolute'))} {unit}"
                    f"（{_text(f'{segment_ratio:g}%' if segment_ratio is not None else '基数为零或缺测')}）；"
                    f"主导上风向：{_wind_text(segment)}。</p>"
                    + _comparison_table(segment, unit) + "</div>"
                )
            facts = (
                f"<p>过程跨度：{_text(_time(event.get('start_time')))}—{_text(_time(event.get('end_time')))}；"
                f"包含{len(segments)}段实际告警，间隔{event.get('gap_hour_count', 0)}个无告警小时；"
                f"全过程浓度变化：{_text(change)} {unit}；峰值时间：{_text(_time(event.get('peak_time')))}。</p>"
                + "".join(segment_html)
            )
        else:
            facts = (
                f"<p>过程跨度：{_text(_time(event.get('start_time')))}—{_text(_time(event.get('end_time')))}；"
                f"浓度{proxy_note}：{_text(change)} {unit}；峰值时间：{_text(_time(event.get('peak_time')))}；"
                f"事件内峰值较{_text(event.get('reference_kind') or '参考小时')}变化 {_number(event.get('peak_rise_absolute'))} {unit}"
                f"（{_text(f'{ratio:g}%' if ratio is not None else '基数为零或缺测')}）；"
                f"末值 {_number(event.get('end_concentration'))} {unit}；主导上风向：{_wind_text(event)}。</p>"
                + _comparison_table(event, unit)
            )
        detail = (
            f"<article><h4>告警时段｜{_text(_alert_times(event))}</h4>"
            + facts
            + "<p class='muted'>浓度为相应时段有效小时均值；对比采用双方同期有效小时，缺测时比较口径可能与整段均值不同。</p>"
            + f"<p class='analysis'>{_text(analysis.get(event['event_id'], ''))}</p></article>"
        )
        group_key = (str(event.get("station_id")), pollutant)
        station_names.setdefault(group_key, str(event.get("station_name") or event.get("station_id")))
        by_station_pollutant.setdefault(group_key, []).append(detail)
    basic_table = ("<div class='table-scroll'><table class='facts-table'><thead><tr><th>站点</th><th>污染物</th><th>升高时段</th>"
                   "<th>浓度变化</th><th>升幅</th><th>绝对增量</th></tr></thead><tbody>" +
                   "".join(rows) + "</tbody></table></div>") if rows else "<p>昨日未识别告警过程。</p>"
    station_html = "".join(
        f"<section class='station'><h3>2.{i} "
        f"{_text(station_names[key] if station_names[key].endswith('站') else station_names[key] + '站')}"
        f"｜{_text(key[1])}（{len(items)}次过程）</h3>{''.join(items)}</section>"
        for i, (key, items) in enumerate(by_station_pollutant.items(), 1)
    )
    map_html = "".join(
        f"<section class='map-card'><div class='map-title'><h3>{_text(item['pollutant'])} 时序变化地图{'（NO₂小时浓度代理）' if item['pollutant'] == 'NOX' else ''}</h3>"
        f"<div class='basemap-switch' role='group' aria-label='底图切换'><button id='base-satellite-{i}' class='selected' type='button'>卫星影像</button>"
        f"<button id='base-light-{i}' type='button'>简洁地图</button><button id='base-terrain-{i}' type='button'>3D地形</button></div></div>"
        f"<div class='map-stage'><div id='map-{i}' class='map'></div><div class='map-hud'>"
        f"<strong id='hud-time-{i}'>—</strong><span id='hud-alert-{i}'>等待数据</span></div></div>"
        f"<div class='playback'><button id='play-{i}' type='button'>▶ 播放</button><button id='pause-{i}' type='button'>❚❚ 暂停</button>"
        f"<label>速度 <select id='speed-{i}'><option value='1500'>0.7×</option><option value='1000' selected>1×</option>"
        f"<option value='500'>2×</option></select></label><span id='time-{i}' class='playback-time'>—</span>"
        f"<input id='slider-{i}' type='range' min='0' max='0' value='0' aria-label='逐小时时间轴'></div>"
        f"<div id='timeline-{i}' class='timeline' role='group' aria-label='24小时时序横幅'></div>"
        f"<div class='map-legend'><span>低</span><i class='legend-gradient'></i><span>高</span>"
        f"<strong id='legend-{i}'></strong><span class='legend-alert'><b></b>告警国控站</span></div>"
        f"<p id='status-{i}' class='muted'>正在加载高德地图...</p><p id='active-{i}' class='muted'></p></section>"
        for i, item in enumerate(maps)
    )
    body = (
        "<section class='main'><h1>许昌市空气质量回顾分析日报</h1>"
        f"<p>报告日期：{_text(payload.get('target_date'))}</p></section>"
        "<section class='main'><h2>一、持续升高基本情况</h2>"
        f"<p>{_text(payload.get('summary_text') or f'昨日合并后识别告警过程 {len(events)} 次。')}</p>"
        + basic_table + "<p class='muted'>同站同污染物告警重叠、接续或仅隔1个无告警小时合并为一次；表中列出实际告警时段，过程统计覆盖合并后的时间跨度。浓度变化及绝对增量为过程内峰值相对告警前一小时有效值的变化，该小时缺测时退用过程内首个有效小时值。CO 单位为 mg/m³，其余为 μg/m³。</p></section>"
        + "<section class='main'><h2>二、持续升高原因分析</h2>"
        "<p class='muted'>风向为观测风来向。上风向候选仅表示方位与风向一致，不单独证明污染传输或来源。</p>"
        + (station_html or "<p>昨日无可分析告警过程。</p>")
        + "<h3>污染物时序变化地图</h3><p class='muted'>每种告警污染物一张真实高德地图；逐小时显示有效站点，红色光环标识当前小时处于告警过程的国控站。站点填色表示该污染物浓度，色阶在全天保持一致。地图仅展示观测事实。</p>"
        + map_html + "</section>"
        + f"<section class='main'><h2>四、结论</h2><p>{_text(payload.get('conclusion'))}</p></section>"
    )
    # Escape HTML-sensitive characters in data before embedding in a script.
    map_json = json.dumps(maps, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    event_json = json.dumps([{"event_id": e["event_id"], "station_id": e["station_id"], "pollutant": e["pollutant"]}
                             for e in events], ensure_ascii=False).replace("<", "\\u003c")
    url_json = json.dumps(f"https://webapi.amap.com/maps?v=2.1Beta&key={amap_key}&plugin=AMap.Scale")
    fallback_url_json = json.dumps(f"https://webapi.amap.com/maps?v=2.0&key={amap_key}&plugin=AMap.Scale")
    script = (MAP_SCRIPT.replace("__MAP_DATA__", map_json).replace("__EVENT_DATA__", event_json)
              .replace("__AMAP_URL__", url_json).replace("__AMAP_FALLBACK_URL__", fallback_url_json))
    return HTML_HEAD + body + "</main><script>" + script + "</script></body></html>"


HTML_HEAD = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>许昌市空气质量回顾分析日报</title><style>
body{margin:0;background:#f2f5f8;color:#182536;font-family:Arial,"Noto Sans CJK SC",sans-serif}main{max-width:1280px;margin:auto;padding:20px}
section.main,section.station,section.map-card{background:white;border:1px solid #d9e2ec;margin-bottom:16px;padding:18px}
h1,h2{margin:0 0 10px}h3{margin:14px 0 9px}h4{margin:18px 0 7px}p{line-height:1.7}.muted{color:#64748b;font-size:13px}
.analysis{border-left:3px solid #208b87;padding:8px 12px;background:#f2faf9}.station article{border-top:1px solid #e3e8ed;padding-top:4px}
.table-scroll{width:100%;overflow-x:auto}table{width:100%;min-width:780px;table-layout:fixed;border-collapse:collapse;margin:10px 0 18px;font-size:13px;font-variant-numeric:tabular-nums}th,td{border:1px solid #dbe3ec;padding:8px;text-align:left;overflow-wrap:anywhere}th{background:#eff4f7;font-weight:600}tbody tr:nth-child(even){background:#f8fafc}
.facts-table th:nth-child(1){width:14%}.facts-table th:nth-child(2){width:10%}.facts-table th:nth-child(3){width:24%}.facts-table th:nth-child(4){width:20%}.facts-table th:nth-child(5){width:12%}.facts-table th:nth-child(6){width:20%}
.comparison-table th:nth-child(1){width:14%}.comparison-table th:nth-child(2){width:20%}.comparison-table th:nth-child(3){width:12%}.comparison-table th:nth-child(4){width:10%}.comparison-table th:nth-child(5){width:16%}.comparison-table th:nth-child(6){width:28%}
.facts-table th:nth-child(5),.facts-table td:nth-child(5),.facts-table th:nth-child(6),.facts-table td:nth-child(6),.comparison-table th:nth-child(3),.comparison-table td:nth-child(3),.comparison-table th:nth-child(5),.comparison-table td:nth-child(5){text-align:right}
.map-card{overflow:hidden}.map-title{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-bottom:12px}.map-title h3{margin:0}
button,select{font:inherit}.basemap-switch{display:flex;gap:4px;padding:4px;background:#e8eef3;border-radius:10px}.basemap-switch button{border:0;background:transparent;border-radius:7px;padding:7px 11px;color:#526377;cursor:pointer}.basemap-switch button.selected{background:#fff;color:#12334a;box-shadow:0 1px 5px #213a5230}.basemap-switch button:disabled{opacity:.45;cursor:not-allowed}
.map-stage{position:relative;overflow:hidden;border:1px solid #c9d5df;border-radius:14px;background:#dbe5e9;box-shadow:0 12px 30px #24435a1c}.map{height:520px;background:#dbe5e9}.map-hud{position:absolute;z-index:50;top:14px;left:14px;display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:10px 15px;border-radius:10px;background:#10283bdc;color:#fff;box-shadow:0 5px 18px #0003;pointer-events:none;font-variant-numeric:tabular-nums}.map-hud strong{font-size:17px;letter-spacing:.03em}.map-hud span{font-size:12px;color:#d4e6ef}
.playback{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:15px 0 8px}.playback button{padding:8px 13px;border:1px solid #c7d5df;border-radius:8px;background:#fff;color:#17445e;cursor:pointer}.playback button:hover{background:#eaf5f8}.playback button:disabled{opacity:.5;cursor:not-allowed}.playback label{color:#526377;font-size:13px}.playback select{padding:6px;border:1px solid #c7d5df;border-radius:7px;background:#fff}.playback-time{margin-left:auto;font-variant-numeric:tabular-nums;font-weight:600;color:#17374c}.playback input[type=range]{width:100%;accent-color:#168a9c;cursor:pointer}
.timeline{display:grid;grid-auto-flow:column;grid-auto-columns:minmax(50px,1fr);gap:4px;overflow-x:auto;padding:4px 2px 10px;scrollbar-color:#aec0cc transparent}.timeline button{position:relative;min-height:44px;border:1px solid #d8e2e9;border-radius:7px;background:#f5f8fa;color:#547084;font-size:11px;font-variant-numeric:tabular-nums;cursor:pointer;scroll-snap-align:center}.timeline button.alert-hour:after{content:'';position:absolute;bottom:5px;left:calc(50% - 2px);width:5px;height:5px;border-radius:50%;background:#e44843}.timeline button.current{background:#17475c;color:#fff;border-color:#17475c;box-shadow:0 3px 8px #163e5140}.timeline button.current:after{background:#ffb8a2}
.map-legend{display:flex;align-items:center;gap:9px;flex-wrap:wrap;margin:12px 0 4px;color:#526377;font-size:12px}.legend-gradient{display:inline-block;width:175px;height:10px;border-radius:6px;background:linear-gradient(90deg,#2563b4,#13a89b,#e8c14a,#e9693c,#c92735)}.map-legend strong{font-weight:500;font-variant-numeric:tabular-nums}.legend-alert{margin-left:auto;display:flex;align-items:center;gap:6px}.legend-alert b{display:inline-block;width:13px;height:13px;border:3px solid #df3a3a;border-radius:50%;box-shadow:0 0 0 3px #df3a3a33}
@media(max-width:700px){main{padding:8px}.map{height:390px}.map-hud{right:12px;top:12px;left:12px}.playback-time{width:100%;margin-left:0}.timeline{grid-auto-columns:52px}.legend-alert{margin-left:0}}
@media(prefers-reduced-motion:reduce){.timeline button,.playback button{transition:none}}
</style></head><body><main>'''


MAP_SCRIPT = '''
const MAPS=__MAP_DATA__, EVENTS=__EVENT_DATA__;
const AMAP_URL=__AMAP_URL__, AMAP_FALLBACK_URL=__AMAP_FALLBACK_URL__;
const instances=[], timers=[], playing=[];
const reduceMotion=window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches;
let terrainAvailable=false;
function el(id){return document.getElementById(id)}
function unitOf(item){return item.pollutant==='CO'?'mg/m³':'μg/m³'}
function scaleOf(item){
 const low=Number(item.scale_min), high=Number(item.scale_max);
 return {low:Number.isFinite(low)?low:0,high:Number.isFinite(high)?high:1};
}
function colorAt(q){
 const stops=[[37,99,180],[19,168,155],[232,193,74],[233,105,60],[201,39,53]];
 const value=Math.max(0,Math.min(1,q))*(stops.length-1), index=Math.min(stops.length-2,Math.floor(value));
 const fraction=value-index;
 return 'rgb('+stops[index].map((channel,j)=>Math.round(channel+(stops[index+1][j]-channel)*fraction)).join(',')+')';
}
function fitDay(i){
 const holder=instances[i];if(!holder||holder.fitted)return;
 let minLng=Infinity,maxLng=-Infinity,minLat=Infinity,maxLat=-Infinity;
 for(const frame of MAPS[i].frames)for(const record of frame.records||[]){
  const lng=Number(record.longitude),lat=Number(record.latitude);
  if(!Number.isFinite(lng)||!Number.isFinite(lat))continue;
  minLng=Math.min(minLng,lng);maxLng=Math.max(maxLng,lng);
  minLat=Math.min(minLat,lat);maxLat=Math.max(maxLat,lat);
 }
 if(!Number.isFinite(minLng))return;
 const padLng=Math.max(.015,(maxLng-minLng)*.06),padLat=Math.max(.015,(maxLat-minLat)*.06);
 holder.map.setBounds(new AMap.Bounds([minLng-padLng,minLat-padLat],[maxLng+padLng,maxLat+padLat]),true,[65,65,65,65]);
 holder.fitted=true;
}
function updateMarkers(i,frame,activeStations){
 const holder=instances[i];if(!holder)return;
 const item=MAPS[i],scale=scaleOf(item),seen=new Set();holder.activeHalos=[];
 for(const record of frame.records||[]){
  const id=String(record.station_id),value=Number(record.concentration);
  if(!Number.isFinite(value)||!Number.isFinite(Number(record.longitude))||!Number.isFinite(Number(record.latitude)))continue;
  seen.add(id);holder.records.set(id,record);
  const q=scale.high>scale.low?(value-scale.low)/(scale.high-scale.low):.5;
  const alert=activeStations.has(id),center=[Number(record.longitude),Number(record.latitude)];
  let marker=holder.markers.get(id);
  const options={center:center,radius:alert?13:6+6*Math.max(0,Math.min(1,q)),fillColor:colorAt(q),fillOpacity:.92,
    strokeColor:alert?'#fff':'#e5f2f6',strokeWeight:alert?2.5:1.5,zIndex:alert?32:12,cursor:'pointer'};
  if(!marker){
   marker=new AMap.CircleMarker(options);marker.setMap(holder.map);holder.markers.set(id,marker);
   marker.on('click',()=>{
    const current=holder.records.get(id);if(!current)return;
    const label=document.createElement('div');label.className='station-popup';
    label.textContent=(current.station_name||id)+'｜'+(current.station_type==='township'?'乡镇站':'国控/常规站')+'｜'+current.concentration+' '+unitOf(item);
    new AMap.InfoWindow({content:label,offset:new AMap.Pixel(0,-12)}).open(holder.map,[current.longitude,current.latitude]);
   });
  }else{marker.setOptions(options);marker.show()}
  let halo=holder.halos.get(id);
  if(alert){
   if(!halo){
    halo=new AMap.CircleMarker({center:center,radius:18,fillColor:'#df3a3a',fillOpacity:.16,
      strokeColor:'#df3a3a',strokeOpacity:.9,strokeWeight:2,zIndex:25});
    halo.setMap(holder.map);holder.halos.set(id,halo);
   }else{halo.setOptions({center:center,radius:18});halo.show()}
   holder.activeHalos.push(halo);
  }else if(halo){halo.hide()}
 }
 holder.markers.forEach((marker,id)=>{if(!seen.has(id))marker.hide()});
 holder.halos.forEach((halo,id)=>{if(!seen.has(id))halo.hide()});
 fitDay(i);
}
function draw(i,index){
 const item=MAPS[i],frame=item.frames[index];if(!frame)return;
 const slider=el('slider-'+i);slider.value=index;
 const active=new Set(frame.active_event_ids||[]);
 const activeStations=new Set(EVENTS.filter(event=>event.pollutant===item.pollutant&&active.has(event.event_id)).map(event=>String(event.station_id)));
 const timestamp=frame.time.replace('T',' ').slice(0,16);
 el('time-'+i).textContent=timestamp+'（'+(index+1)+'/'+item.frames.length+'）';
 el('hud-time-'+i).textContent=timestamp;
 el('hud-alert-'+i).textContent=active.size?active.size+' 次告警过程 · '+(playing[i]?'播放中':'已暂停'):'当前小时无告警 · '+(playing[i]?'播放中':'已暂停');
 const names=[...new Set((frame.records||[]).filter(r=>activeStations.has(String(r.station_id))).map(r=>r.station_name||r.station_id))];
 el('active-'+i).textContent=names.length?'当前告警国控站：'+names.join('、'):'当前小时无该污染物告警国控站';
 const scale=scaleOf(item);
 el('legend-'+i).textContent=scale.low+' — '+scale.high+' '+unitOf(item)+'（全天固定色阶）';
 el('timeline-'+i).querySelectorAll('button').forEach((button,j)=>{
  button.classList.toggle('current',j===index);button.setAttribute('aria-current',j===index?'true':'false');
 });
 const current=el('timeline-'+i).children[index];if(current)current.scrollIntoView({block:'nearest',inline:'nearest'});
 updateMarkers(i,frame,activeStations);
}
function pause(i){playing[i]=false;clearTimeout(timers[i]);timers[i]=null;
 el('play-'+i).disabled=false;el('pause-'+i).disabled=true;
 const slider=el('slider-'+i);if(MAPS[i].frames.length)draw(i,Number(slider.value));
}
function scheduleNext(i){
 if(!playing[i])return;
 const delay=Number(el('speed-'+i).value)||1000;
 timers[i]=setTimeout(()=>{
  const slider=el('slider-'+i),next=(Number(slider.value)+1)%MAPS[i].frames.length;
  draw(i,next);scheduleNext(i);
 },delay);
}
function play(i){if(playing[i]||!MAPS[i].frames.length)return;
 playing[i]=true;el('play-'+i).disabled=true;el('pause-'+i).disabled=false;
 draw(i,Number(el('slider-'+i).value));scheduleNext(i);
}
function initControls(){MAPS.forEach((item,i)=>{
 const slider=el('slider-'+i),timeline=el('timeline-'+i);slider.max=Math.max(0,item.frames.length-1);
 item.frames.forEach((frame,index)=>{
  const button=document.createElement('button');button.type='button';button.textContent=frame.time.slice(11,16);
  button.title=frame.time.replace('T',' ')+'｜'+(frame.active_event_ids||[]).length+' 次告警过程';
  if((frame.active_event_ids||[]).length)button.classList.add('alert-hour');
  button.onclick=()=>draw(i,index);timeline.appendChild(button);
 });
 slider.oninput=()=>draw(i,Number(slider.value));
 el('play-'+i).onclick=()=>play(i);el('pause-'+i).onclick=()=>pause(i);
 el('speed-'+i).onchange=()=>{if(playing[i]){clearTimeout(timers[i]);scheduleNext(i)}};
 el('base-satellite-'+i).onclick=()=>createMap(i,'satellite');
 el('base-light-'+i).onclick=()=>createMap(i,'light');
 el('base-terrain-'+i).onclick=()=>createMap(i,'terrain');
 el('pause-'+i).disabled=true;
 if(item.frames.length)draw(i,0);else{
  el('status-'+i).textContent='无有效小时地图数据';el('play-'+i).disabled=true;
 }
})}
function hasWebGL(){try{const canvas=document.createElement('canvas');return !!(canvas.getContext('webgl')||canvas.getContext('experimental-webgl'))}catch(_){return false}}
function createMap(i,mode){
 const previous=instances[i],oldMap=previous&&previous.map;
 if(mode==='terrain'&&!terrainAvailable){el('status-'+i).textContent='当前环境不支持 3D 地形，已保留卫星影像';return}
 let center=[113.85,34.05],zoom=9,fitted=false;
 if(oldMap){try{center=oldMap.getCenter();zoom=oldMap.getZoom();fitted=previous.fitted}catch(_){}}
 try{
  const options={center:center,zoom:zoom,viewMode:'2D',showIndoorMap:false};
  if(mode==='satellite')options.layers=[new AMap.TileLayer.Satellite(),new AMap.TileLayer.RoadNet()];
  else if(mode==='light')options.mapStyle='amap://styles/whitesmoke';
  else{options.viewMode='3D';options.terrain=true;options.pitch=38;options.mapStyle='amap://styles/whitesmoke'}
  if(oldMap)oldMap.destroy();
  const map=new AMap.Map('map-'+i,options);
  instances[i]={map:map,mode:mode,markers:new Map(),halos:new Map(),records:new Map(),activeHalos:[],fitted:fitted};
  for(const option of ['satellite','light','terrain'])el('base-'+option+'-'+i).classList.toggle('selected',option===mode);
  el('status-'+i).textContent=mode==='terrain'?'3D 地形已启用':mode==='satellite'?'高德卫星影像与路网已加载':'高德浅色地图已加载';
  draw(i,Number(el('slider-'+i).value));
 }catch(error){
  instances[i]=null;el('status-'+i).textContent='底图切换失败：'+error.message;
  if(mode==='terrain')createMap(i,'satellite');
  else if(mode==='satellite')createMap(i,'light');
 }
}
let lastPulse=0;
function pulse(time){
 if(!reduceMotion&&!document.hidden&&time-lastPulse>=50){
  lastPulse=time;
  for(const holder of instances){if(!holder)continue;
   const radius=18+3*Math.sin(time/260);for(const halo of holder.activeHalos)halo.setRadius(radius);
  }
 }
 requestAnimationFrame(pulse);
}
function startMaps(beta){terrainAvailable=beta&&hasWebGL();
 MAPS.forEach((_,i)=>{
  const button=el('base-terrain-'+i);button.disabled=!terrainAvailable;
  button.title=terrainAvailable?'高德 3D 地形（Beta）':'需要高德 JS API 2.1Beta 与 WebGL';
  try{createMap(i,'satellite')}catch(error){el('status-'+i).textContent='地图初始化失败：'+error.message}
 });
 if(!reduceMotion)requestAnimationFrame(pulse);
}
function loadMap(){
 function inject(url,success,failure){const script=document.createElement('script');script.src=url;
  script.onload=()=>window.AMap&&AMap.Map?success():failure();script.onerror=failure;document.head.appendChild(script);
 }
 inject(AMAP_URL,()=>startMaps(true),()=>inject(AMAP_FALLBACK_URL,()=>startMaps(false),()=>{
  MAPS.forEach((_,i)=>el('status-'+i).textContent='高德地图加载失败，请检查网络或 Key 配置');
 }));
}
initControls();if(MAPS.length)loadMap();
'''


def write_html_report(path: str, payload: dict[str, Any], *, amap_key: str) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(build_html_report(payload, amap_key=amap_key), encoding="utf-8")
    return str(target)
