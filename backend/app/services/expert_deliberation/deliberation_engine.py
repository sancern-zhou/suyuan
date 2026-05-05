"""Deterministic first version of fact-driven expert deliberation."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Awaitable, Callable
from uuid import uuid4

from .expert_registry import get_default_experts
from .expert_agent_runner import LLMExpertAgentRunner
from .fact_ingestor import FactIngestor
from .fact_ledger import FactLedger
from .discussion_ledger import DiscussionLedger
from .schemas import (
    ClaimRecord,
    ConsensusConclusion,
    DeliberationRequest,
    DeliberationResult,
    EvidenceMatrixRow,
    ExpertAnalysis,
    ExpertCard,
    FactRecord,
    TimelineEvent,
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
        ]
        conclusions = self._build_consensus(analyses, facts)
        dissents = self._build_dissents(analyses)
        forbidden_claims = self._build_forbidden_claims(analyses)
        evidence_matrix = self._build_evidence_matrix(analyses)
        timeline_events = self._build_timeline_events(facts, None, evidence_matrix)
        report_markdown = self._render_report(request, facts, analyses, conclusions, dissents, forbidden_claims, evidence_matrix)
        output_files = self._persist(request, facts, experts, analyses, None, evidence_matrix, timeline_events, conclusions, dissents, forbidden_claims, report_markdown)

        return DeliberationResult(
            topic=request.topic,
            region=request.region,
            time_range=request.time_range,
            pollutants=request.pollutants,
            facts=facts,
            experts=experts,
            analyses=analyses,
            evidence_matrix=evidence_matrix,
            timeline_events=timeline_events,
            conclusions=conclusions,
            dissents=dissents,
            forbidden_claims=forbidden_claims,
            report_markdown=report_markdown,
            output_files=output_files,
        )

    async def run_async(
        self,
        request: DeliberationRequest,
        progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> DeliberationResult:
        await self._emit_progress(
            progress_callback,
            "started",
            "会商启动",
            f"开始处理 {len(request.consultation_tables)} 张表、{len(request.data_ids)} 个 data_id。",
        )
        await self._emit_progress(
            progress_callback,
            "fact_ingestion_started",
            "事实入账",
            "正在使用 LLM 抽取会商表格、报告和数据资产事实。",
        )
        ledger = await FactIngestor().build_async(request)
        await self._emit_progress(
            progress_callback,
            "fact_ingestion_completed",
            "事实入账完成",
            f"已入账 {len(ledger.all())} 条事实。",
            facts_count=len(ledger.all()),
            facts=self._fact_snapshots(ledger.all(), limit=10),
        )
        experts = get_default_experts()
        discussion = DiscussionLedger()
        domain_experts = [expert for expert in experts if expert.expert_id != "reviewer_moderator"]
        reviewer_experts = [expert for expert in experts if expert.expert_id == "reviewer_moderator"]

        await self._emit_progress(
            progress_callback,
            "topic_announced",
            "主持人提出会商议题",
            self._build_agenda_message(request, ledger.all()),
            round_index=1,
            facts=self._fact_snapshots(ledger.all(), limit=6),
        )
        await self._emit_progress(progress_callback, "round_started", "第 1 轮初判", "领域专家开始基于事实账本进行初判。", round_index=1)
        await self._build_expert_analyses(
            request=request,
            experts=domain_experts,
            ledger=ledger,
            round_index=1,
            turn_type="initial_opinion",
            discussion=discussion,
            progress_callback=progress_callback,
        )

        pending_targets = discussion.question_targets({expert.expert_id for expert in domain_experts})
        last_tool_fact_count = len([fact for fact in ledger.all() if fact.source_type == "tool_supplement"])
        max_rounds = max(2, request.options.max_discussion_rounds)
        if request.options.enable_supplement_planning:
            for round_index in range(2, max_rounds + 1):
                await self._emit_progress(
                    progress_callback,
                    "round_started",
                    f"第 {round_index} 轮复议",
                    "根据专家提问、补证结果和审查要求继续讨论。",
                    round_index=round_index,
                )
                current_tool_fact_count = len([fact for fact in ledger.all() if fact.source_type == "tool_supplement"])
                if current_tool_fact_count > last_tool_fact_count:
                    pending_targets.update(expert.expert_id for expert in domain_experts)
                cross_experts = [expert for expert in domain_experts if expert.expert_id in pending_targets]
                await self._build_expert_analyses(
                    request=request,
                    experts=cross_experts,
                    ledger=ledger,
                    round_index=round_index,
                    turn_type="cross_review",
                    discussion=discussion,
                    progress_callback=progress_callback,
                )
                await self._build_expert_analyses(
                    request=request,
                    experts=reviewer_experts,
                    ledger=ledger,
                    round_index=round_index,
                    turn_type="review_moderation",
                    discussion=discussion,
                    progress_callback=progress_callback,
                )
                reviewer_analysis = discussion.latest_for("reviewer_moderator")
                if reviewer_analysis is not None and self._reviewer_allows_stop(reviewer_analysis):
                    await self._emit_progress(
                        progress_callback,
                        "reviewer_stopped",
                        "审查员结束讨论",
                        "审查员判断当前证据链可以进入共识输出。",
                        round_index=round_index,
                    )
                    break
                pending_targets = {
                    str(question.get("target_expert"))
                    for question in (reviewer_analysis.questions_to_others if reviewer_analysis is not None else [])
                    if str(question.get("target_expert")) in {expert.expert_id for expert in domain_experts}
                }
                if not pending_targets:
                    pending_targets = discussion.question_targets({expert.expert_id for expert in domain_experts})
                last_tool_fact_count = len([fact for fact in ledger.all() if fact.source_type == "tool_supplement"])
        else:
            await self._build_expert_analyses(
                request=request,
                experts=reviewer_experts,
                ledger=ledger,
                round_index=2,
                turn_type="review_moderation",
                discussion=discussion,
                progress_callback=progress_callback,
            )

        facts = ledger.all()
        analyses = discussion.latest_analyses()
        await self._emit_progress(progress_callback, "consensus_started", "生成共识", "正在构建结论-证据矩阵和会商报告。")
        evidence_matrix = self._build_evidence_matrix(analyses)
        timeline_events = self._build_timeline_events(facts, discussion, evidence_matrix)
        conclusions = self._build_consensus(analyses, facts)
        dissents = self._build_dissents(analyses)
        forbidden_claims = self._build_forbidden_claims(analyses)
        report_markdown = self._render_report(request, facts, analyses, conclusions, dissents, forbidden_claims, evidence_matrix)
        output_files = self._persist(request, facts, experts, analyses, discussion, evidence_matrix, timeline_events, conclusions, dissents, forbidden_claims, report_markdown)

        result = DeliberationResult(
            topic=request.topic,
            region=request.region,
            time_range=request.time_range,
            pollutants=request.pollutants,
            facts=facts,
            experts=experts,
            analyses=analyses,
            discussion_turns=discussion.all(),
            evidence_matrix=evidence_matrix,
            timeline_events=timeline_events,
            conclusions=conclusions,
            dissents=dissents,
            forbidden_claims=forbidden_claims,
            report_markdown=report_markdown,
            output_files=output_files,
        )
        await self._emit_progress(
            progress_callback,
            "completed",
            "会商完成",
            f"完成 {len(facts)} 条事实、{len(analyses)} 条专家意见、{len(conclusions)} 条共识。",
            facts_count=len(facts),
            analyses_count=len(analyses),
            conclusions_count=len(conclusions),
        )
        return result

    async def _build_expert_analyses(
        self,
        request: DeliberationRequest,
        experts: list[ExpertCard],
        ledger: FactLedger,
        round_index: int,
        turn_type: str,
        discussion: DiscussionLedger,
        progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> list[ExpertAnalysis]:
        llm_runner = LLMExpertAgentRunner()
        analyses: list[ExpertAnalysis] = []
        target_experts = set(request.target_experts)
        for expert in experts:
            if target_experts and expert.expert_id not in target_experts and expert.display_name not in target_experts:
                continue
            await self._emit_progress(
                progress_callback,
                "expert_started",
                f"{expert.display_name}开始",
                self._expert_start_message(expert, turn_type, discussion),
                round_index=round_index,
                turn_type=turn_type,
                expert_id=expert.expert_id,
                display_name=expert.display_name,
                pending_questions=self._pending_questions_for_expert(discussion, expert.expert_id),
            )
            facts = ledger.all()
            relevant = facts[: request.options.max_facts_per_expert]
            if not request.options.enable_llm_experts:
                raise RuntimeError("专家会商必须启用 ReAct/LLM 专家，当前请求关闭了 enable_llm_experts")
            analysis, new_facts = await llm_runner.analyze(
                expert=expert,
                request=request,
                facts=facts,
                relevant=relevant,
                round_index=round_index,
                start_fact_index=len(facts) + 1,
                turn_type=turn_type,
                discussion_context=discussion.summary_for_expert(expert.expert_id, turn_type),
            )
            ledger.extend(new_facts)
            discussion.add_analysis(analysis, round_index=round_index, turn_type=turn_type)
            analyses.append(analysis)
            await self._emit_progress(
                progress_callback,
                "expert_completed",
                f"{expert.display_name}发言",
                self._expert_completion_message(analysis, turn_type, new_facts),
                round_index=round_index,
                turn_type=turn_type,
                expert_id=expert.expert_id,
                display_name=expert.display_name,
                position=analysis.position,
                claims=[claim.model_dump(mode="json") for claim in analysis.key_findings],
                used_fact_ids=analysis.used_fact_ids,
                new_fact_ids=[fact.fact_id for fact in new_facts],
                new_facts=self._fact_snapshots(new_facts, limit=8),
                questions_to_others=analysis.questions_to_others,
                tool_call_plan=[plan.model_dump(mode="json") for plan in analysis.tool_call_plan],
                uncertainties=analysis.uncertainties,
            )
        return analyses

    async def _emit_progress(
        self,
        progress_callback: Callable[[dict[str, Any]], Awaitable[None]] | None,
        event_type: str,
        title: str,
        message: str,
        **payload: Any,
    ) -> None:
        if progress_callback is None:
            return
        await progress_callback(
            {
                "type": event_type,
                "title": title,
                "message": message,
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                **payload,
            }
        )

    def _fact_snapshots(self, facts: list[FactRecord], limit: int = 8) -> list[dict[str, Any]]:
        return [
            {
                "fact_id": fact.fact_id,
                "source_type": fact.source_type,
                "city": fact.city,
                "pollutant": fact.pollutant,
                "statement": fact.statement,
                "tags": fact.tags[:5],
            }
            for fact in facts[:limit]
        ]

    def _build_agenda_message(self, request: DeliberationRequest, facts: list[FactRecord]) -> str:
        pollutants = "、".join(request.pollutants) or "主要污染物"
        sources = "、".join(sorted({fact.source_type for fact in facts})) or "事实材料"
        return f"围绕{request.region}{request.time_range.display or ''}的{pollutants}污染特征、气象输送、化学来源和证据可写性开展会商；当前事实来源包括{sources}。"

    def _pending_questions_for_expert(self, discussion: DiscussionLedger, expert_id: str) -> list[dict[str, str]]:
        questions: list[dict[str, str]] = []
        for turn in discussion.all():
            for question in turn.questions_to_others:
                if str(question.get("target_expert") or "") == expert_id:
                    questions.append(
                        {
                            "from_expert": turn.display_name,
                            "question": str(question.get("question") or ""),
                            "reason": str(question.get("reason") or ""),
                        }
                    )
        return questions[-6:]

    def _expert_start_message(self, expert: ExpertCard, turn_type: str, discussion: DiscussionLedger) -> str:
        pending_count = len(self._pending_questions_for_expert(discussion, expert.expert_id))
        if turn_type == "initial_opinion":
            return "阅读事实账本，形成初判并提出需要其他专家交叉验证的问题。"
        if turn_type == "cross_review" and pending_count:
            return f"回应 {pending_count} 个指向本专家的问题，并结合补证事实修正判断。"
        if turn_type == "review_moderation":
            return "审查事实链、专家观点、补证结果和结论可写性，判断是否结束讨论。"
        return f"{self._turn_type_label(turn_type)}：继续补充会商意见。"

    def _expert_completion_message(
        self,
        analysis: ExpertAnalysis,
        turn_type: str,
        new_facts: list[FactRecord],
    ) -> str:
        question_count = len(analysis.questions_to_others)
        claim_count = len(analysis.key_findings)
        used_count = len(analysis.used_fact_ids)
        new_fact_count = len(new_facts)
        if turn_type == "review_moderation":
            return f"审查员形成统稿意见，审查 {used_count} 条事实，提出 {question_count} 个复议问题。"
        if turn_type == "cross_review":
            return f"完成交叉复议，形成 {claim_count} 条判断，引用 {used_count} 条事实，新增 {new_fact_count} 条补证事实。"
        return f"完成初判，形成 {claim_count} 条判断，引用 {used_count} 条事实，提出 {question_count} 个交叉验证问题。"

    def _reviewer_allows_stop(self, analysis: ExpertAnalysis) -> bool:
        if analysis.tool_call_plan:
            return False
        domain_targets = {"monitoring_feature_expert", "weather_transport_expert", "chemistry_source_expert"}
        for question in analysis.questions_to_others:
            if str(question.get("target_expert")) in domain_targets:
                return False
        blocking_words = ["需补证", "继续", "重新判断", "补充", "缺少", "不足", "无法形成"]
        text = " ".join([analysis.position, " ".join(analysis.uncertainties)])
        return not any(word in text for word in blocking_words)

    def _analyze_expert(self, expert: ExpertCard, facts: list[FactRecord], limit: int) -> ExpertAnalysis:
        relevant = self._select_relevant_facts(expert, facts, limit)
        used_ids = [fact.fact_id for fact in relevant]

        if expert.expert_id == "reviewer_moderator":
            return self._reviewer_analysis(expert, facts[:limit])

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

    def _reviewer_analysis(self, expert: ExpertCard, facts: list[FactRecord]) -> ExpertAnalysis:
        used_ids = [fact.fact_id for fact in facts]
        missing = [
            "定量贡献比例必须有模型或计算方法支撑",
            "报告文字结论需要回链到原始表格、data_id或工具输出",
        ]
        claim = ClaimRecord(
            claim_id="claim_reviewer_moderator_001",
            expert_id=expert.expert_id,
            claim="当前会商可形成定性或半定量共识，审查与统稿阶段应禁止无依据的精确贡献比例进入正文。",
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
                    "target_expert": "chemistry_source_expert",
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
            "monitoring_feature_expert": "常规监测、AQI/IAQI、首要污染物和时空变化事实构成污染特征判断主线。",
            "weather_transport_expert": "气象扩散、轨迹传输与上风向源共同影响污染累积和清除过程。",
            "chemistry_source_expert": "组分、前体物和源解析事实提示，需要联合核查二次生成及主要来源贡献。",
        }
        return f"{prefixes.get(expert.expert_id, expert.display_name + '形成候选判断')} 关键依据：{lead_statement}"

    def _missing_facts_for_expert(self, expert: ExpertCard, relevant: list[FactRecord]) -> list[str]:
        text = " ".join(f.statement for f in relevant)
        missing = []
        if expert.expert_id == "monitoring_feature_expert":
            if not any(word in text for word in ["AQI", "IAQI", "首要污染物", "超标", "达标率"]):
                missing.append("AQI、IAQI、首要污染物、超标或达标率事实")
            if not any(word in text for word in ["同比", "环比", "排名", "峰值", "小时"]):
                missing.append("同比、环比、排名、峰值或小时变化事实")
        if expert.expert_id == "weather_transport_expert":
            if not any(word in text for word in ["边界层", "风速", "降水", "静稳"]):
                missing.append("污染过程期间逐小时气象和边界层事实")
            if not any(word in text for word in ["轨迹", "上风向", "传输"]):
                missing.append("轨迹、风场或上风向源事实")
        if expert.expert_id == "chemistry_source_expert":
            if not any(word in text for word in ["组分", "VOCs", "硝酸盐", "硫酸盐", "NOx"]):
                missing.append("组分、VOCs、NOx或二次生成指标")
            if not any(word in text for word in ["PMF", "源解析", "贡献"]):
                missing.append("源解析或贡献比例模型结果")
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
            "monitoring_feature_expert": [
                ("weather_transport_expert", "污染峰值是否与不利扩散或输送时段同步？"),
                ("chemistry_source_expert", "PM2.5/O3协同变化是否有组分或前体物证据？"),
            ],
            "weather_transport_expert": [
                ("monitoring_feature_expert", "传输时段是否对应城市或站点浓度抬升？"),
            ],
            "chemistry_source_expert": [
                ("monitoring_feature_expert", "组分或来源判断是否对应常规污染物变化？"),
            ],
        }
        if expert.expert_id not in mapping:
            return []
        return [
            {"target_expert": target, "question": question, "reason": "用于交叉验证候选结论"}
            for target, question in mapping[expert.expert_id]
        ]

    def _build_consensus(self, analyses: list[ExpertAnalysis], facts: list[FactRecord]) -> list[ConsensusConclusion]:
        domain_analyses = [a for a in analyses if a.expert_id != "reviewer_moderator" and a.used_fact_ids]
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

    def _build_evidence_matrix(self, analyses: list[ExpertAnalysis]) -> list[EvidenceMatrixRow]:
        rows: list[EvidenceMatrixRow] = []
        for index, analysis in enumerate(analyses, start=1):
            for claim in analysis.key_findings:
                evidence_ids = list(dict.fromkeys(claim.supporting_facts or analysis.used_fact_ids))
                missing = list(dict.fromkeys(claim.missing_facts + analysis.uncertainties))
                risk_flags: list[str] = []
                if not evidence_ids:
                    risk_flags.append("缺少事实引用")
                if missing:
                    risk_flags.append("存在补证缺口")
                if any(word in claim.claim for word in ["贡献", "%", "比例"]) and not any(
                    word in " ".join(evidence_ids + missing + [claim.claim]) for word in ["PMF", "模型", "计算"]
                ):
                    risk_flags.append("定量归因依据不足")
                writability = "可写" if evidence_ids and not missing and claim.confidence >= 0.7 else "降级写"
                if not evidence_ids:
                    writability = "需补证"
                if "定量归因依据不足" in risk_flags:
                    writability = "禁写精确比例"
                rows.append(
                    EvidenceMatrixRow(
                        conclusion_id=f"matrix_{index:03d}_{len(rows) + 1:03d}",
                        claim=claim.claim,
                        status=claim.status,
                        supporting_experts=[analysis.display_name],
                        opposing_experts=[],
                        evidence_fact_ids=evidence_ids,
                        contradicting_fact_ids=claim.contradicting_facts,
                        missing_facts=missing,
                        risk_flags=risk_flags,
                        confidence=claim.confidence,
                        writability=writability,
                    )
                )
        return rows

    def _build_timeline_events(
        self,
        facts: list[FactRecord],
        discussion: DiscussionLedger | None,
        evidence_matrix: list[EvidenceMatrixRow],
    ) -> list[TimelineEvent]:
        events = [
            TimelineEvent(
                event_id="timeline_001",
                stage="fact_ingestion",
                title="事实入账",
                description=f"完成 {len(facts)} 条事实入账，其中工具补证 {len([f for f in facts if f.source_type == 'tool_supplement'])} 条。",
                fact_ids=[fact.fact_id for fact in facts[:8]],
            )
        ]
        if discussion is not None:
            for turn in discussion.all():
                events.append(
                    TimelineEvent(
                        event_id=f"timeline_{len(events) + 1:03d}",
                        stage=turn.turn_type,
                        title=f"{turn.display_name}：{self._turn_type_label(turn.turn_type)}",
                        description=turn.position,
                        round_index=turn.round_index,
                        expert_id=turn.expert_id,
                        fact_ids=turn.used_fact_ids[:8] + turn.new_fact_ids[:4],
                        turn_id=turn.turn_id,
                    )
                )
        events.append(
            TimelineEvent(
                event_id=f"timeline_{len(events) + 1:03d}",
                stage="evidence_matrix",
                title="结论-证据矩阵",
                description=f"生成 {len(evidence_matrix)} 条候选结论证据链，其中 {len([r for r in evidence_matrix if r.writability == '可写'])} 条可直接写入。",
            )
        )
        return events

    def _turn_type_label(self, turn_type: str) -> str:
        labels = {
            "initial_opinion": "初判",
            "cross_review": "交叉复议",
            "review_moderation": "审查统稿",
        }
        return labels.get(turn_type, turn_type)

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
        evidence_matrix: list[EvidenceMatrixRow],
    ) -> str:
        # 构建时间范围字符串（避免f-string嵌套）
        time_range_str = request.time_range.display or f'{request.time_range.start or ""} 至 {request.time_range.end or ""}'.strip()

        lines = [
            "# 专家会商结论",
            "",
            f"**会商主题**：{request.topic}",
            f"**区域**：{request.region}",
            f"**时段**：{time_range_str}",
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

        lines.extend(["", "## 结论-证据矩阵", "", "| 结论 | 可写性 | 支持专家 | 关键事实 | 风险 |", "|---|---|---|---|---|"])
        for row in evidence_matrix[:12]:
            lines.append(
                f"| {row.claim} | {row.writability} | {'、'.join(row.supporting_experts) or '暂无'} | {', '.join(row.evidence_fact_ids[:5]) or '暂无'} | {'；'.join(row.risk_flags) or '暂无'} |"
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
        discussion: DiscussionLedger | None,
        evidence_matrix: list[EvidenceMatrixRow],
        timeline_events: list[TimelineEvent],
        conclusions: list[ConsensusConclusion],
        dissents: list[dict[str, str]],
        forbidden_claims: list[dict[str, str]],
        report_markdown: str,
    ) -> dict[str, str]:
        run_id = f"delib_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        run_dir = self.output_root / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        files = {
            "request": run_dir / "request.json",
            "fact_ledger": run_dir / "fact_ledger.jsonl",
            "expert_analyses": run_dir / "expert_analyses.json",
            "discussion_ledger": run_dir / "discussion_ledger.json",
            "evidence_matrix": run_dir / "evidence_matrix.json",
            "timeline_events": run_dir / "timeline_events.json",
            "consensus": run_dir / "consensus.json",
            "forbidden_claims": run_dir / "forbidden_claims.json",
            "report_markdown": run_dir / "expert_deliberation.md",
        }
        files["request"].write_text(json.dumps(request.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
        with files["fact_ledger"].open("w", encoding="utf-8") as f:
            for fact in facts:
                f.write(json.dumps(fact.model_dump(), ensure_ascii=False) + "\n")
        files["expert_analyses"].write_text(json.dumps([a.model_dump() for a in analyses], ensure_ascii=False, indent=2), encoding="utf-8")
        discussion_turns = discussion.all() if discussion is not None else []
        files["discussion_ledger"].write_text(json.dumps([t.model_dump() for t in discussion_turns], ensure_ascii=False, indent=2), encoding="utf-8")
        files["evidence_matrix"].write_text(json.dumps([r.model_dump() for r in evidence_matrix], ensure_ascii=False, indent=2), encoding="utf-8")
        files["timeline_events"].write_text(json.dumps([e.model_dump() for e in timeline_events], ensure_ascii=False, indent=2), encoding="utf-8")
        files["consensus"].write_text(
            json.dumps({"experts": [e.model_dump() for e in experts], "conclusions": [c.model_dump() for c in conclusions], "evidence_matrix": [r.model_dump() for r in evidence_matrix], "dissents": dissents}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        files["forbidden_claims"].write_text(json.dumps(forbidden_claims, ensure_ascii=False, indent=2), encoding="utf-8")
        files["report_markdown"].write_text(report_markdown, encoding="utf-8")
        return {name: str(path) for name, path in files.items()}
