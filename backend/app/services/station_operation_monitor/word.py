from __future__ import annotations

from docx import Document
from docx.shared import Pt
from docx.oxml.ns import qn

from .core import local_time


def stamp(value):
    return local_time(value).strftime('%m月%d日%H时')


def write_word(data, config, path):
    document = Document()
    style = document.styles['Normal']
    style.font.name = '宋体'
    style.font.size = Pt(11)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    document.add_heading(config.get('report_title', '空气质量国控和省控站点运行监控日报'), 0)
    document.add_paragraph(local_time(data['window_end']).strftime('（%Y年%m月%d日）'))
    document.add_paragraph(config.get('organization', ''))
    document.add_paragraph(f"统计时段：{stamp(data['window_start'])}至{stamp(data['window_end'])}。")
    document.add_paragraph('通过站点小时数据接口检查、核对，统计超过4小时的连续数据缺失，同时跟进前日及更早未结记录。')
    if not data['report_ready']:
        document.add_paragraph('本次取数不完整，报告为待核实稿；不能据此认定所有站点运行正常。')
    for kind in ('国控', '省控'):
        entries = [entry for entry in data['entries'] if entry['type'] == kind]
        document.add_heading(f"{kind}站点（本次监控范围{data['station_counts'][kind]}个）：", 1)
        if not entries:
            document.add_paragraph('本次监控范围内未发现已观察的连续缺数超过4小时记录。')
        for entry in entries:
            restored = '截至统计截止小时数据已返回，设备恢复时间待核实' if entry['recovered'] else '截至统计截止时未恢复，正在持续跟进'
            filled = '数据已回补' if entry['backfill_status'] == '已回补' else '数据'+entry['backfill_status']
            if entry.get('unrecoverable_confirmation'):
                filled += '（'+entry['unrecoverable_confirmation']['reason']+'）'
            prefix = '前日及更早情况跟进：' if entry['carry_over'] else ''
            document.add_paragraph(f"{prefix}{entry['city']}{entry['name']}站：{stamp(entry['offline_start'])}至{stamp(entry['offline_end'])}，"
                                   f"累计影响数据{entry['affected_hours']}小时（本统计窗口{entry['window_affected_hours']}小时），{restored}，{filled}。")
    document.add_paragraph('编制、校核及期号：待人工确认。')
    document.add_heading('附件：站点离线记录表（按小时数据缺失判定）', 1)
    headers = ['序号','城市','站点','离线时间','是否已恢复','影响数据时长（小时）','是否影响数据有效性','排查结果','备注']
    for kind in ('国控', '省控'):
        document.add_heading(f'{kind}站点离线记录表', 2)
        table = document.add_table(rows=1, cols=len(headers))
        table.style = 'Table Grid'
        for cell, text in zip(table.rows[0].cells, headers):
            cell.text = text
        entries = [entry for entry in data['entries'] if entry['type'] == kind]
        for i, entry in enumerate(entries, 1):
            note = '数据已回补' if entry['backfill_status']=='已回补' else entry['backfill_status']
            if entry.get('unrecoverable_confirmation'):
                note += '；'+entry['unrecoverable_confirmation']['reason']+'；依据：'+entry['unrecoverable_confirmation']['evidence']
            if entry['backfill_sources']:
                note += '；' + '、'.join(entry['backfill_sources'])
            if entry['carry_over']:
                note += '；历史未结跟进'
            values = [str(i),entry['city'],entry['name'],f"{stamp(entry['offline_start'])}—{stamp(entry['offline_end'])}",
                      '是' if entry['recovered'] else '否',str(entry['affected_hours']), '待核实', '原因待核实',note]
            for cell, value in zip(table.add_row().cells, values):
                cell.text = value
        if not entries:
            for cell in table.add_row().cells:
                cell.text = '/'
    if data['unverified_stations']:
        document.add_heading('无记录候选站点（在运状态待核实）', 1)
        document.add_paragraph('以下候选站点未取得数据，尚未纳入已确认离线统计：' + '；'.join(
            f"{s['city']}{s['name']}（{s['code']}，{s['type']}）" for s in data['unverified_stations']))
    if data['collection_errors']:
        document.add_heading('取数异常', 1)
        for error in data['collection_errors']:
            document.add_paragraph('；'.join(str(v) for v in error.values()))
    document.add_heading('数据来源及说明', 1)
    document.add_paragraph('国控：'+'、'.join(data['national_sources'])+'。省控：'+data['provincial_source']+'。')
    for limitation in data['limitations']:
        document.add_paragraph(limitation)
    document.save(path)
    return path
