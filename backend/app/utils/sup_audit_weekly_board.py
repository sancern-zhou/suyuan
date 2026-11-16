# -*- coding: utf-8 -*-
"""组分站审核规则命中率周报看板。

扫描审计产物（latest_finished_work_orders_deterministic_audit.json），按
(rule_id, tag) 聚合命中量、涉及工单/站点、站点集中度，并按噪音治理军规
自动标红需要人工复核的规则：

  - CONCENTRATED  单站占该规则命中 ≥60%（口径可能不适用该站，参考 MARGA/
                  EquipmentStatus 先例）
  - HIGH_RATE     命中工单占该 tag 全部工单 ≥50%（近 100% 命中=判定口径错误）
  - HIGH_VOLUME   年化命中 ≥200 条（量大需抽检确认真实性）
  - 其余正常

输出：终端表格 + 可选 HTML（--html <path>）。

用法：
  python -m app.utils.sup_audit_weekly_board --audit-result <json> [--html out.html]
  python -m app.utils.sup_audit_weekly_board --runs-dir <dir>   # 聚合多窗口
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# 噪音治理军规阈值（与 sup-screenshot-rules-implementation-plan.md 一致）
CONCENTRATION_ALERT = 0.60   # 单站占比
TAG_RATE_ALERT = 0.50        # 该 tag 工单命中率
VOLUME_ALERT = 200           # 年化命中条数

# 已确认为"文档硬要求"的高量规则：命中量大属真实合规缺口，不做口径告警
KNOWN_LEGIT_HIGH_VOLUME = {
    "SUP_ATTACHMENT_REQUIRED_MISSING",
    "FORM_DATA_MISSING",
}


def _extract_tag(issue: dict[str, Any]) -> str:
    evidence = issue.get("evidence")
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except (ValueError, TypeError):
            evidence = {}
    if isinstance(evidence, dict):
        tag = evidence.get("ruleitemtag")
        if tag:
            return str(tag)
        field = str(evidence.get("field") or "")
        if ".attachment." in field:
            return field.split(".")[1] if field.count(".") >= 2 else ""
        if field.startswith("sup_rf_common."):
            parts = field.split(".")
            return parts[1] if len(parts) > 1 else ""
    message = str(issue.get("message") or "")
    for token in message.replace("：", " ").split():
        if token.startswith("Sup_RF_") or token.startswith("RF_"):
            return token
    return ""


def scan_audit_files(paths: list[Path]) -> tuple[dict[str, Any], list[str]]:
    """聚合多个审计产物，返回 (统计, 告警行)。"""
    rule_hits: Counter = Counter()
    rule_tag_hits: Counter = Counter()
    rule_tag_orders: dict[tuple[str, str], set] = defaultdict(set)
    rule_tag_stations: dict[tuple[str, str], Counter] = defaultdict(Counter)
    tag_orders_seen: dict[str, set] = defaultdict(set)
    order_total = 0
    warnings: list[str] = []
    # 多窗口聚合去重：同一工单可能在重叠窗口（如月度窗 + 8 周窗）重复出现，
    # 按 (工单, 规则, 表单类型, 消息) 唯一化，避免重复计数放大命中量。
    seen_issue_keys: set[tuple[str, str, str, str]] = set()
    seen_order_codes: set[str] = set()

    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            warnings.append(f"{path.name}: 读取失败 {exc}")
            continue
        records = data.get("records") or []
        for record in records:
            code = record.get("working_order_code") or record.get("WORKINGORDERCODE")
            station = record.get("station_name") or record.get("STATIONID") or "?"
            if code:
                seen_order_codes.add(str(code))
            tags_in_record = set()
            for issue in record.get("issues") or []:
                rule_id = issue.get("rule_id") or ""
                if not rule_id:
                    continue
                tag = _extract_tag(issue)
                dedupe_key = (str(code), rule_id, tag, str(issue.get("message") or "")[:80])
                if dedupe_key in seen_issue_keys:
                    continue
                seen_issue_keys.add(dedupe_key)
                rule_hits[rule_id] += 1
                if not tag:
                    continue
                key = (rule_id, tag)
                rule_tag_hits[key] += 1
                if code:
                    rule_tag_orders[key].add(code)
                rule_tag_stations[key][station] += 1
                tags_in_record.add(tag)
            for tag in tags_in_record:
                if code:
                    tag_orders_seen[tag].add(code)

    rows = []
    for (rule_id, tag), hits in rule_tag_hits.most_common():
        stations = rule_tag_stations[(rule_id, tag)]
        top_station, top_hits = stations.most_common(1)[0] if stations else ("-", 0)
        concentration = top_hits / hits if hits else 0.0
        tag_orders = len(tag_orders_seen.get(tag) or ())
        hit_orders = len(rule_tag_orders[(rule_id, tag)])
        rate = hit_orders / tag_orders if tag_orders else 0.0
        flags = []
        if concentration >= CONCENTRATION_ALERT and hits >= 5:
            flags.append("CONCENTRATED")
        if rate >= TAG_RATE_ALERT and hits >= 5:
            flags.append("HIGH_RATE")
        if hits >= VOLUME_ALERT and rule_id not in KNOWN_LEGIT_HIGH_VOLUME:
            flags.append("HIGH_VOLUME")
        if rule_id == "SUP_ATTACHMENT_ITEM_MATCH" and hits >= 20:
            flags.append("CHECK_NORMALIZATION")
        rows.append({
            "rule_id": rule_id,
            "tag": tag,
            "hits": hits,
            "hit_orders": hit_orders,
            "tag_orders": tag_orders,
            "rate": round(rate, 3),
            "stations": len(stations),
            "top_station": top_station,
            "top_share": round(concentration, 3),
            "flags": flags,
        })
    stats = {
        "audit_files": [str(p) for p in paths],
        "orders": len(seen_order_codes),
        "total_hits": sum(rule_hits.values()),
        "by_rule": dict(rule_hits),
        "rows": rows,
        "warnings": warnings,
    }
    alert_lines = [
        f"[{','.join(r['flags'])}] {r['rule_id']} | {r['tag']}: {r['hits']} 条 "
        f"/ {r['hit_orders']} 单（该 tag 共 {r['tag_orders']} 单，命中率 {r['rate']:.0%}）"
        f"/ {r['stations']} 站，最集中 {r['top_station']} {r['top_share']:.0%}"
        for r in rows if r["flags"]
    ]
    return stats, alert_lines


def render_text(stats: dict[str, Any], alert_lines: list[str]) -> str:
    lines = [
        f"审计产物 {len(stats['audit_files'])} 份 · 工单 {stats['orders']} 单 · 命中 {stats['total_hits']} 条",
        "",
        f"{'规则':34} {'表单类型':36} {'命中':>5} {'单数':>5} {'命中率':>7} {'站点':>4} {'最集中':>16}",
        "-" * 118,
    ]
    for row in stats["rows"][:40]:
        mark = " ! " if row["flags"] else "   "
        lines.append(
            f"{mark}{row['rule_id']:32} {row['tag'][:34]:36} {row['hits']:>5} "
            f"{row['hit_orders']:>5} {row['rate']:>6.0%} {row['stations']:>4} "
            f"{row['top_station'][:10]}{row['top_share']:>6.0%}"
        )
    lines.append("")
    if alert_lines:
        lines.append("== 需人工复核（噪音军规告警）==")
        lines.extend(alert_lines)
    else:
        lines.append("== 无告警：全部规则命中分布正常 ==")
    if stats["warnings"]:
        lines.append("")
        lines.extend(f"WARN {w}" for w in stats["warnings"])
    return "\n".join(lines)


HTML_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>组分站审核规则命中看板</title>
<style>
body{{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;margin:24px;color:#1f2328;background:#fff}}
h1{{font-size:20px;margin:0 0 6px}} .sub{{color:#59636e;font-size:13px;margin-bottom:18px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th{{background:#f6f8fa;text-align:left;padding:8px;border-bottom:2px solid #d1d9e0;font-weight:600}}
td{{padding:7px 8px;border-bottom:1px solid #eaeef2}}
tr.alert td{{background:#fff5f5}} tr.alert td:first-child{{border-left:3px solid #cf222e}}
.k{display:inline-block;padding:1px 6px;border-radius:10px;font-size:11px;margin-right:4px}}
.k-CONCENTRATED{{background:#ffe2e2;color:#a40e26}}
.k-HIGH_RATE{{background:#fff1d6;color:#8a5a00}}
.k-HIGH_VOLUME{{background:#e8f0ff;color:#0b4f9e}}
.k-CHECK_NORMALIZATION{{background:#f3e8ff;color:#6b21a8}}
.mono{{font-family:ui-monospace,Consolas,monospace;font-size:12px}}
.ok{{color:#1a7f37}} .bad{{color:#cf222e;font-weight:600}}
</style></head><body>
<h1>组分站审核规则命中看板</h1>
<div class="sub">审计产物 {n_files} 份 · 工单 {orders} 单 · 命中 {total} 条 · 告警规则 {n_alert} 项</div>
<table><thead><tr><th>规则</th><th>表单类型</th><th>命中</th><th>涉及单</th><th>该 tag 命中率</th><th>站点数</th><th>最集中站点</th><th>标记</th></tr></thead><tbody>
{rows}
</tbody></table>
<p class="sub" style="margin-top:18px">告警口径：CONCENTRATED（单站 ≥60%）· HIGH_RATE（该 tag 工单命中率 ≥50%）· HIGH_VOLUME（≥200 条）· CHECK_NORMALIZATION（附件项目匹配需核归一化）</p>
</body></html>"""


def render_html(stats: dict[str, Any]) -> str:
    rows_html = []
    for row in stats["rows"]:
        cls = ' class="alert"' if row["flags"] else ""
        badges = "".join(f'<span class="k k-{f}">{f}</span>' for f in row["flags"])
        rate_cls = "bad" if row["rate"] >= TAG_RATE_ALERT else "ok"
        rows_html.append(
            f"<tr{cls}><td class='mono'>{row['rule_id']}</td><td class='mono'>{row['tag']}</td>"
            f"<td><b>{row['hits']}</b></td><td>{row['hit_orders']}</td>"
            f"<td class='{rate_cls}'>{row['rate']:.0%}</td><td>{row['stations']}</td>"
            f"<td>{row['top_station']} <span class='sub'>{row['top_share']:.0%}</span></td>"
            f"<td>{badges or '<span class=ok>正常</span>'}</td></tr>"
        )
    return HTML_TEMPLATE.format(
        n_files=len(stats["audit_files"]),
        orders=stats["orders"],
        total=stats["total_hits"],
        n_alert=sum(1 for r in stats["rows"] if r["flags"]),
        rows="\n".join(rows_html),
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    paths: list[Path] = []
    html_out: Path | None = None
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--audit-result" and i + 1 < len(args):
            paths.append(Path(args[i + 1])); i += 2
        elif arg == "--runs-dir" and i + 1 < len(args):
            base = Path(args[i + 1])
            paths.extend(sorted(base.glob("*/latest_finished_work_orders_deterministic_audit.json")))
            i += 2
        elif arg == "--html" and i + 1 < len(args):
            html_out = Path(args[i + 1]); i += 2
        else:
            print(f"未知参数: {arg}", file=sys.stderr)
            return 2
    if not paths:
        print(__doc__)
        return 2
    stats, alerts = scan_audit_files(paths)
    print(render_text(stats, alerts))
    if html_out:
        html_out.parent.mkdir(parents=True, exist_ok=True)
        html_out.write_text(render_html(stats), encoding="utf-8")
        print(f"\nHTML 看板已写入 {html_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
