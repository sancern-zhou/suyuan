from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from docx import Document
from docx.text.paragraph import Paragraph
from docx.table import _Row

from app.utils.path_config import resolve_agent_path
from docx.shared import Pt
from docx.oxml.ns import qn

from .core import local_time


def stamp(value):
    return local_time(value).strftime('%m月%d日%H时')


def write_word(data, config, path):
    if config.get("template_path"):
        return write_template_word(data, config, path)
    document = Document()
    style = document.styles['Normal']
    style.font.name = '宋体'
    style.font.size = Pt(11)
    style.element.rPr.rFonts.set(qn('w:eastAsia'), '宋体')
    document.add_heading(config.get('report_title', '空气质量国控和省控站点运行监控日报'), 0)
    document.add_paragraph(local_time(data['window_end']).strftime('（%Y年%m月%d日）'))
    document.add_paragraph(config.get('organization', ''))
    document.add_paragraph(f"统计时段：{stamp(data['window_start'])}至{stamp(data['window_end'])}。")
    document.add_paragraph('通过站点小时数据接口检查、核对，整理全部小时数据缺失（含单项缺失），同时跟进前日及更早未结记录。')
    if not data['report_ready']:
        document.add_paragraph('本次取数不完整，报告为待核实稿；不能据此认定所有站点运行正常。')
    for kind in ('国控', '省控'):
        entries = [entry for entry in data['entries'] if entry['type'] == kind]
        document.add_heading(f"{kind}站点（本次监控范围{data['station_counts'][kind]}个）：", 1)
        if not entries:
            document.add_paragraph('本次监控范围内未发现已观察的小时数据缺失记录。')
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


def replace_text(paragraph, text):
    """Replace text while retaining the template paragraph and first run format."""
    run = next((r for r in paragraph.runs if r.text), None)
    properties = deepcopy(run._r.rPr) if run is not None and run._r.rPr is not None else None
    for child in list(paragraph._p):
        if child.tag != qn('w:pPr'):
            paragraph._p.remove(child)
    new_run = paragraph.add_run(text)
    if properties is not None:
        new_run._r.insert(0, properties)



def replace_spans(paragraph, spans):
    properties = [deepcopy(r._r.rPr) for r in paragraph.runs]
    replace_text(paragraph, '')
    for text, index in spans:
        run = paragraph.add_run(text)
        if properties[index] is not None:
            run._r.insert(0, deepcopy(properties[index]))

def missing_note(entry):
    names = {'sO2':'SO₂', 'nO2':'NO₂', 'pM10':'PM₁₀', 'co':'CO', 'o3':'O₃', 'pM2_5':'PM₂.₅'}
    parameters = entry.get('missing_parameters', [])
    return '缺失项目：' + '、'.join(names.get(p, p) for p in parameters) if parameters else ''


def incident_text(entry):
    recovery = '截止小时数据已恢复' if entry['recovered'] else '截止时未恢复，正在持续跟进'
    filled = '数据已回补' if entry['backfill_status'] == '已回补' else '数据' + entry['backfill_status']
    if entry.get('unrecoverable_confirmation'):
        filled += '（' + entry['unrecoverable_confirmation']['reason'] + '）'
    prefix = '前日及更早情况跟进：' if entry['carry_over'] else ''
    return (f"{prefix}{entry['city']}{entry['name']}：{stamp(entry['offline_start'])}至{stamp(entry['offline_end'])}，"
            f"累计影响数据时长{entry['affected_hours']}小时，{recovery}，{filled}；{missing_note(entry)}。")


def write_template_word(data, config, path):
    template_path = resolve_agent_path(config['template_path'])
    digest = hashlib.sha256(template_path.read_bytes()).hexdigest()
    if config.get('template_sha256') and config['template_sha256'] != digest:
        raise ValueError('日报模板版本校验失败')
    document = Document(template_path)
    paragraphs = document.paragraphs
    # This layout adapter deliberately validates the supplied Guangdong report structure.
    if (len(paragraphs) < 20 or len(document.tables) != 2
            or paragraphs[1].text != '运行监控日报'
            or paragraphs[6].text[:4] != '国控站点'
            or paragraphs[10].text[:4] != '省控站点'
            or any(len(t.columns) != 9 for t in document.tables)):
        raise ValueError('日报模板结构不匹配，请核对模板版本')
    end = local_time(data['window_end'])
    replace_text(paragraphs[2], f'（{end.year}年{end.month}月{end.day}日）')
    replace_text(paragraphs[3], config.get('organization', '广东省生态环境监测中心') +
                 '       ' + config.get('report_issue', f'{end.year}年期号待确认'))
    counts = data['station_counts']
    replace_text(paragraphs[5], f"通过站点小时数据检查、核对，统计时段为{stamp(data['window_start'])}至{stamp(data['window_end'])}，"
                 f"本次监控国控站点{counts['国控']}个、省控站点{counts['省控']}个，小时数据缺失的情况如下。")
    replace_text(paragraphs[6], f"国控站点（本次监控{counts['国控']}个）：")
    replace_text(paragraphs[10], f"省控站点（本次监控{counts['省控']}个）：")
    prototype = deepcopy(paragraphs[8]._p)
    for i in (8, 9):
        paragraphs[i]._p.getparent().remove(paragraphs[i]._p)
    for kind, anchor in [('国控', paragraphs[7]), ('省控', paragraphs[11])]:
        entries = [e for e in data['entries'] if e['type'] == kind]
        replace_text(anchor, f'过去24小时及历史未结记录中，共有{len(entries)}条数据缺失记录。'
                     if entries else '本次监控范围内，未发现已观察的数据缺失记录。')
        for entry in entries:
            element = deepcopy(prototype)
            anchor._p.addnext(element)
            anchor = Paragraph(element, anchor._parent)
            text = incident_text(entry)
            label, detail = text.split('：', 1)
            replace_spans(anchor, [(label + '：', 0), (detail, 1)])
    replace_spans(paragraphs[12], [('编制：', 0), (config.get('prepared_by', '待确认'), 1),
                                 ('                              ', 2), ('校核：', 3),
                                 (config.get('reviewed_by', '待确认'), 5)])
    for kind, table in zip(('国控', '省控'), document.tables):
        row_template = deepcopy(table.rows[1]._tr)
        for row in list(table.rows)[1:]:
            table._tbl.remove(row._tr)
        entries = [e for e in data['entries'] if e['type'] == kind]
        rows = entries or [None]
        for index, entry in enumerate(rows, 1):
            row_element = deepcopy(row_template)
            table._tbl.append(row_element)
            row = _Row(row_element, table)
            if entry is None:
                values = ['/'] * 9
            else:
                note = '数据已回补' if entry['backfill_status'] == '已回补' else entry['backfill_status']
                if missing_note(entry):
                    note += '；' + missing_note(entry)
                confirmation = entry.get('unrecoverable_confirmation')
                if confirmation:
                    note += '；' + confirmation['reason'] + '；依据：' + confirmation['evidence']
                if entry['backfill_sources']:
                    note += '；' + '、'.join(entry['backfill_sources'])
                if entry['carry_over']:
                    note += '；历史未结跟进'
                values = [str(index), entry['city'], entry['name'],
                          f"{stamp(entry['offline_start'])}—{stamp(entry['offline_end'])}",
                          '是' if entry['recovered'] else '否', str(entry['affected_hours']),
                          '待核实', '原因待核实', note]
            for cell, value in zip(row.cells, values):
                replace_text(cell.paragraphs[0], value)
                for extra in cell.paragraphs[1:]:
                    extra._p.getparent().remove(extra._p)
    # Keep the formal report and its two landscape tables intact; append audit notes separately.
    def add_note(text, first=False):
        element = deepcopy(paragraphs[5]._p)
        document.element.body.insert(len(document.element.body) - 1, element)
        paragraph = Paragraph(element, document._body)
        replace_text(paragraph, text)
        if first:
            paragraph.paragraph_format.page_break_before = True
        return paragraph
    add_note('数据核查说明', first=True)
    if not data['report_ready']:
        add_note('本次取数不完整，报告为待核实稿；不能据此认定所有站点运行正常。')
    add_note('国控：' + '、'.join(data['national_sources']) + '。省控：' + data['provincial_source'] + '。')
    for limitation in data['limitations']:
        add_note(limitation)
    if data['unverified_stations']:
        add_note('无记录候选站点（在运状态待核实）')
        add_note('以下候选站点未取得数据，尚未纳入已确认离线统计：' + '；'.join(
            f"{s['city']}{s['name']}（{s['code']}，{s['type']}）" for s in data['unverified_stations']))
    for error in data['collection_errors']:
        add_note('取数异常：' + '；'.join(str(v) for v in error.values()))
    document.save(path)
    validation = validate_template_format(template_path, path)
    validation['template_sha256'] = digest
    Path(path).with_suffix('.format.json').write_text(
        json.dumps(validation, ensure_ascii=False, indent=2), encoding='utf-8')
    return path


def validate_template_format(template_path, output_path):
    """Validate stable layout invariants, allowing variable body content and row counts."""
    template = Document(template_path)
    output = Document(output_path)
    checks = {}
    checks['sections'] = [s._sectPr.xml for s in template.sections] == [s._sectPr.xml for s in output.sections]
    checks['headers_footers'] = len(template.sections) == len(output.sections) and all(
        a.header._element.xml == b.header._element.xml and a.footer._element.xml == b.footer._element.xml
        for a, b in zip(template.sections, output.sections))
    checks['titles'] = len(output.paragraphs) >= 5 and all(
        template.paragraphs[i]._p.xml == output.paragraphs[i]._p.xml for i in (0, 1))
    checks['date_issuer_styles'] = len(output.paragraphs) >= 5 and all(
        template.paragraphs[i]._p.pPr.xml == output.paragraphs[i]._p.pPr.xml
        and template.paragraphs[i].runs[0]._r.rPr.xml == output.paragraphs[i].runs[0]._r.rPr.xml
        for i in (2, 3))
    checks['divider'] = len(output.paragraphs) >= 5 and template.paragraphs[4]._p.xml == output.paragraphs[4]._p.xml
    checks['tables'] = len(template.tables) == len(output.tables) == 2 and all(
        a._tbl.tblPr.xml == b._tbl.tblPr.xml and a._tbl.tblGrid.xml == b._tbl.tblGrid.xml
        and a.rows[0]._tr.xml == b.rows[0]._tr.xml
        for a, b in zip(template.tables, output.tables))
    checks['table_titles'] = all(
        any(p._p.xml == template.paragraphs[i]._p.xml for p in output.paragraphs) for i in (16, 18))
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise ValueError('日报格式校验失败：' + '、'.join(failures))
    return {'passed': True, 'checks': checks}
