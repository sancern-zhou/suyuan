"""Deterministic first version of fact-driven expert deliberation."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from .expert_registry import get_default_experts
from .fact_ingestor import FactIngestor
from .schemas import (
    ClaimRecord,
    ConsensusConclusion,
    DeliberationRequest,
    DeliberationResult,
    ExpertAnalysis,
    ExpertCard,
    FactRecord,
    ToolCallPlan,
)


class ExpertDeliberationEngine:
    def __init__(self, output_root: str | Path = "data/expert_deliberations") -> None:
        self.output_root = Path(output_root)

    def run(self, request: DeliberationRequest) -> DeliberationResult:
        ledger = FactIngestor().build(request)
        facts = ledger.all()
        experts = get_default_experts()
        analyses = [
            self._analyze_expert(expert, facts, request.options.max_facts_per_expert)
            for expert in experts
            if expert.expert_id not in {"moderator_writer"}
        ]
        conclusions = self._build_consensus(analyses, facts)
        dissents = self._build_dissents(analyses)
        forbidden_claims = self._build_forbidden_claims(analyses)
        report_markdown = self._render_report(request, facts, analyses, conclusions, dissents, forbidden_claims)
        output_files = self._persist(request, facts, experts, analyses, conclusions, dissents, forbidden_claims, report_markdown)

        return DeliberationResult(
            topic=request.topic,
            region=request.region,
            time_range=request.time_range,
            pollutants=request.pollutants,
            facts=facts,
            experts=experts,
            analyses=analyses,
            conclusions=conclusions,
            dissents=dissents,
            forbidden_claims=forbidden_claims,
            report_markdown=report_markdown,
            output_files=output_files,
        )

    def _analyze_expert(self, expert: ExpertCard, facts: list[FactRecord], limit: int) -> ExpertAnalysis:
        relevant = self._select_relevant_facts(expert, facts, limit)
        used_ids = [fact.fact_id for fact in relevant]

        if expert.expert_id == "skeptic_reviewer":
            return self._skeptic_analysis(expert, facts[:limit])

        if relevant:
            lead = relevant[0].statement
            claim_text = self._claim_for_expert(expert, lead)
            confidence = min(0.86, 0.55 + len(relevant) * 0.035)
            claim = ClaimRecord(
                claim_id=f"claim_{expert.expert_id}_001",
                expert_id=expert.expert_id,
                claim=claim_text,
                supporting_facts=used_ids[:5],
                missing_facts=self._missing_facts_for_expert(expert, relevant),
                confidence=round(confidence, 2),
            )
            position = claim_text
        else:
            claim = ClaimRecord(
                claim_id=f"claim_{expert.expert_id}_001",
                expert_id=expert.expert_id,
                claim=f"{expert.display_name}认为当前事实不足，暂不形成实质判断。",
                supporting_facts=[],
                missing_facts=["缺少与该专家领域直接相关的事实"],
                confidence=0.35,
            )
            position = claim.claim

        plans = self._supplement_plans(expert, claim.missing_facts)
        questions = self._questions_for_expert(expert)
        uncertainties = claim.missing_facts or ["当前判断依赖已有事实，后续应随新增数据更新"]

        return ExpertAnalysis(
            expert_id=expert.expert_id,
            display_name=expert.display_name,
            used_fact_ids=used_ids,
            tool_call_plan=plans,
            position=position,
            key_findings=[claim],
            questions_to_others=questions,
            uncertainties=uncertainties,
        )

    def _skeptic_analysis(self, expert: ExpertCard, facts: list[FactRecord]) -> ExpertAnalysis:
        used_ids = [fact.fact_id for fact in facts]
        missing = [
            "定量贡献比例必须有模型或计算方法支撑",
            "报告文字结论需要回链到原始表格、data_id或工具输出",
        ]
        claim = ClaimRecord(
            claim_id="claim_skeptic_reviewer_001",
            expert_id=expert.expert_id,
            claim="当前会商可形成定性或半定量共识，但无依据的精确贡献比例应禁止进入正文。",
            supporting_facts=used_ids[:5],
            missing_facts=missing,
            confidence=0.82,
        )
        return ExpertAnalysis(
            expert_id=expert.expert_id,
            display_name=expert.display_name,
            used_fact_ids=used_ids,
            position=claim.claim,
            key_findings=[claim],
            uncertainties=missing,
            questions_to_others=[
                {
                    "target_expert": "source_apportionment_expert",
                    "question": "是否存在足以支持精确贡献比例的PMF或其他定量归因结果？",
                    "reason": "避免把专家判断写成模型结论。",
                }
            ],
        )

    def _select_relevant_facts(self, expert: ExpertCard, facts: list[FactRecord], limit: int) -> list[FactRecord]:
        if not expert.tags_any:
            return facts[:limit]
        scored = []
        terms = [tag.lower() for tag in expert.tags_any]
        for fact in facts:
            haystack = " ".join([fact.statement, " ".join(fact.tags), fact.pollutant or ""]).lower()
            score = sum(1 for term in terms if term in haystack)
            if score:
                scored.append((score, fact))
        scored.sort(key=lambda item: (-item[0], item[1].fact_id))
        return [fact for _, fact in scored[:limit]]

    def _claim_for_expert(self, expert: ExpertCard, lead_statement: str) -> str:
        prefixes = {
            "monitoring_expert": "监测数据表明，污染过程、城市差异和同比环比变化应作为会商主线。",
            "meteorology_expert": "气象扩散条件可能对污染累积和清除过程产生关键调制作用。",
            "chemistry_expert": "组分和前体物事实提示，需要重点核查二次生成及臭氧/颗粒物协同机制。",
            "source_apportionment_expert": "来源解析应优先区分工业、交通、扬尘、燃烧及二次生成贡献。",
            "transport_expert": "区域传输与本地累积需要结合轨迹、风场和上风向源共同判断。",
        }
        return f"{prefixes.get(expert.expert_id, expert.display_name + '形成候选判断')} 关键依据：{lead_statement}"

    def _missing_facts_for_expert(self, expert: ExpertCard, relevant: list[FactRecord]) -> list[str]:
        text = " ".join(f.statement for f in relevant)
        missing = []
        if expert.expert_id == "meteorology_expert" and not any(word in text for word in ["边界层", "风速", "降水", "静稳"]):
            missing.append("污染过程期间逐小时气象和边界层事实")
        if expert.expert_id == "chemistry_expert" and not any(word in text for word in ["组分", "VOCs", "硝酸盐", "硫酸盐", "NOx"]):
            missing.append("组分、VOCs、NOx或二次生成指标")
        if expert.expert_id == "source_apportionment_expert" and not any(word in text for word in ["PMF", "源解析", "贡献"]):
            missing.append("源解析或贡献比例模型结果")
        if expert.expert_id == "transport_expert" and not any(word in text for word in ["轨迹", "上风向", "传输"]):
            missing.append("轨迹、风场或上风向源事实")
        return missing

    def _supplement_plans(self, expert: ExpertCard, missing_facts: list[str]) -> list[ToolCallPlan]:
        if not missing_facts or not expert.tool_whitelist:
            return []
        preferred = expert.tool_whitelist[0]
        return [
            ToolCallPlan(
                tool_name=preferred,
                purpose=f"补充验证：{missing_facts[0]}",
                expected_fact_type="supplement",
            )
        ]

    def _questions_for_expert(self, expert: ExpertCard) -> list[dict[str, str]]:
        mapping = {
            "meteorology_expert": ("chemistry_expert", "二次生成增强是否与不利气象时段一致？"),
            "chemistry_expert": ("source_apportionment_expert", "组分特征是否支持源解析中的主要来源判断？"),
            "source_apportionment_expert": ("transport_expert", "源解析结论能否区分本地排放与区域传输？"),
            "transport_expert": ("meteorology_expert", "轨迹传输判断是否得到风场和扩散条件支持？"),
            "monitoring_expert": ("meteorology_expert", "污染过程峰值是否与不利气象过程同步？"),
        }
        if expert.expert_id not in mapping:
            return []
        target, question = mapping[expert.expert_id]
        return [{"target_expert": target, "question": question, "reason": "用于交叉验证候选结论"}]

    def _build_consensus(self, analyses: list[ExpertAnalysis], facts: list[FactRecord]) -> list[ConsensusConclusion]:
        domain_analyses = [a for a in analyses if a.expert_id != "skeptic_reviewer" and a.used_fact_ids]
        if not domain_analyses:
            return [
                ConsensusConclusion(
                    claim="当前事实不足，无法形成稳定会商结论。",
                    consensus_level="证据不足",
                    confidence=0.35,
                    report_sentence="本轮会商认为，当前事实不足以支持稳定成因判断，需补充监测、气象、组分或源解析数据。",
                )
            ]

        supporting = [a.display_name for a in domain_analyses]
        evidence_ids = []
        for analysis in domain_analyses:
            evidence_ids.extend(analysis.used_fact_ids[:2])
        evidence_ids = list(dict.fromkeys(evidence_ids))
        confidence = min(0.88, 0.5 + len(supporting) * 0.07 + min(len(evidence_ids), 8) * 0.015)
        level = "高共识" if confidence >= 0.78 else "较高共识" if confidence >= 0.65 else "存在分歧"
        pollutants = "、".join(sorted({f.pollutant for f in facts if f.pollutant})) or "主要污染物"
        claim = f"围绕{pollutants}的会商已形成跨专家候选共识：应以监测事实为主线，联合核查气象扩散、二次生成、源解析和区域传输。"
        return [
            ConsensusConclusion(
                claim=claim,
                consensus_level=level,
                supporting_experts=supporting,
                evidence_fact_ids=evidence_ids,
                confidence=round(confidence, 2),
                report_sentence=claim,
            )
        ]

    def _build_dissents(self, analyses: list[ExpertAnalysis]) -> list[dict[str, str]]:
        dissents = []
        for analysis in analyses:
            if analysis.tool_call_plan:
                dissents.append(
                    {
                        "topic": f"{analysis.display_name}补证需求",
                        "opinion": analysis.uncertainties[0] if analysis.uncertainties else "需要补充事实",
                        "needed_evidence": analysis.tool_call_plan[0].purpose,
                    }
                )
        return dissents

    def _build_forbidden_claims(self, analyses: list[ExpertAnalysis]) -> list[dict[str, str]]:
        return [
            {
                "claim": "气象贡献60%、排放贡献30%、传输贡献10%",
                "reason": "除非有明确归因模型或计算过程，否则不得写入正式报告。",
            },
            {
                "claim": "某单一因素是唯一主因",
                "reason": "空气质量过程通常由监测、气象、排放、化学和传输共同影响，需事实链支持。",
            },
        ]

    def _render_report(
        self,
        request: DeliberationRequest,
        facts: list[FactRecord],
        analyses: list[ExpertAnalysis],
        conclusions: list[ConsensusConclusion],
        dissents: list[dict[str, str]],
        forbidden_claims: list[dict[str, str]],
    ) -> str:
        lines = [
            "# 专家会商结论",
            "",
            f"**会商主题**：{request.topic}",
            f"**区域**：{request.region}",
            f"**时段**：{request.time_range.display or f'{request.time_range.start or ''} 至 {request.time_range.end or ''}'.strip()}",
            f"**事实数量**：{len(facts)}",
            "",
            "## 会商依据",
            "",
            "本次会商基于会商表格、上月污染特征与溯源分析报告、阶段性分析文本和已有数据资产构建事实账本。专家观点必须引用事实编号，证据不足的判断进入补证或禁写清单。",
            "",
            "## 主要共识",
            "",
            "| 结论 | 共识等级 | 置信度 | 关键事实 |",
            "|---|---|---:|---|",
        ]
        for conclusion in conclusions:
            lines.append(
                f"| {conclusion.claim} | {conclusion.consensus_level} | {conclusion.confidence:.2f} | {', '.join(conclusion.evidence_fact_ids[:6]) or '暂无'} |"
            )

        lines.extend(["", "## 专家意见摘要", "", "| 专家 | 观点 | 使用事实 | 补证建议 |", "|---|---|---|---|"])
        for analysis in analyses:
            plan = "；".join(p.purpose for p in analysis.tool_call_plan) or "暂无"
            lines.append(
                f"| {analysis.display_name} | {analysis.position} | {', '.join(analysis.used_fact_ids[:5]) or '暂无'} | {plan} |"
            )

        lines.extend(["", "## 分歧与后续补证", "", "| 分歧/缺口 | 当前意见 | 所需证据 |", "|---|---|---|"])
        if dissents:
            for dissent in dissents:
                lines.append(f"| {dissent['topic']} | {dissent['opinion']} | {dissent['needed_evidence']} |")
        else:
            lines.append("| 暂无明显分歧 | 当前事实可支持初步会商结论 | 持续更新事实账本 |")

        lines.extend(["", "## 禁写结论", "", "| 禁写表述 | 原因 |", "|---|---|"])
        for item in forbidden_claims:
            lines.append(f"| {item['claim']} | {item['reason']} |")

        lines.extend(["", "## 管控建议", "", "1. 以已识别污染过程和重点城市为主线，优先核查高值时段的气象扩散和排放活动。", "2. 对二次生成风险较高过程，联动核查VOCs、NOx、PM2.5组分和O3变化。", "3. 对存在传输疑点的过程，补充轨迹聚类、上风向企业和区域同步浓度对比。"])
        return "\n".join(lines)

    def _persist(
        self,
        request: DeliberationRequest,
        facts: list[FactRecord],
        experts: list[ExpertCard],
        analyses: list[ExpertAnalysis],
        conclusions: list[ConsensusConclusion],
        dissents: list[dict[str, str]],
        forbidden_claims: list[dict[str, str]],
        report_markdown: str,
    ) -> dict[str, str]:
        run_id = f"delib_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        run_dir = self.output_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        files = {
            "fact_ledger": run_dir / "fact_ledger.jsonl",
            "expert_analyses": run_dir / "expert_analyses.json",
            "consensus": run_dir / "consensus.json",
            "forbidden_claims": run_dir / "forbidden_claims.json",
            "report_markdown": run_dir / "expert_deliberation.md",
        }
        with files["fact_ledger"].open("w", encoding="utf-8") as f:
            for fact in facts:
                f.write(json.dumps(fact.model_dump(), ensure_ascii=False) + "\n")
        files["expert_analyses"].write_text(json.dumps([a.model_dump() for a in analyses], ensure_ascii=False, indent=2), encoding="utf-8")
        files["consensus"].write_text(
            json.dumps({"experts": [e.model_dump() for e in experts], "conclusions": [c.model_dump() for c in conclusions], "dissents": dissents}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        files["forbidden_claims"].write_text(json.dumps(forbidden_claims, ensure_ascii=False, indent=2), encoding="utf-8")
        files["report_markdown"].write_text(report_markdown, encoding="utf-8")
        return {name: str(path) for name, path in files.items()}
