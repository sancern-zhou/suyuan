# Yuncheng Alert Tracing Timeline Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Yuncheng alert tracing report use an asset-time-aware pollution-process timeline as its main business narrative.

**Architecture:** Keep the existing social → assistant → two expert flow and report package export unchanged. Strengthen the three published Skill documents and assistant task prompt so experts expose actual asset times and the main Agent dynamically builds a monitoring-led timeline, then protect the behavior with publication/prompt contract tests.

**Tech Stack:** Markdown Skill documents, Python 3.11, pytest, existing `ListSkillsTool` and `ViewSkillTool`.

---

### Task 1: Lock the main Skill timeline contract with failing tests

**Files:**
- Modify: `backend/tests/tools/test_yuncheng_skill_publication.py`
- Test: `backend/tests/tools/test_yuncheng_skill_publication.py`

- [ ] **Step 1: Add a failing test for the timeline-led report contract**

Append this test:

```python
@pytest.mark.asyncio
async def test_yuncheng_skill_requires_asset_time_aware_business_timeline():
    viewed = await ViewSkillTool().execute(name="yuncheng_alert_tracing_skill")

    assert viewed["success"] is True
    content = viewed["data"]["content"]
    for phrase in (
        "污染过程时间线",
        "目标城市小时数据作为主时间轴",
        "实际有效时次",
        "不强行对齐",
        "告警前背景",
        "告警触发时刻",
        "未来数小时趋势",
        "变化—同期情况—业务意义",
    ):
        assert phrase in content
    assert "关键变化看板" not in content
    assert "## 天气与传输影响" not in content
```

- [ ] **Step 2: Add a failing test for business-language and image-time rules**

Append this test:

```python
@pytest.mark.asyncio
async def test_yuncheng_skill_keeps_timeline_business_facing():
    viewed = await ViewSkillTool().execute(name="yuncheng_alert_tracing_skill")

    content = viewed["data"]["content"]
    for phrase in (
        "图片紧跟其对应的时间节点",
        "有效时次",
        "起报时间",
        "预报时效",
        "执行时段",
        "无法确认有效时次",
    ):
        assert phrase in content
    for forbidden in ("证据强度", "置信度", "假设竞争"):
        assert forbidden not in content
```

- [ ] **Step 3: Run the focused tests and verify they fail**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/test_yuncheng_skill_publication.py -k "asset_time_aware or business_facing"
```

Expected: both new tests fail because the current Skill still uses asset-type chapters and does not define actual-time attachment rules.

- [ ] **Step 4: Commit the red tests**

```bash
git add backend/tests/tools/test_yuncheng_skill_publication.py
git commit -m "test: define yuncheng timeline report contract"
```

### Task 2: Rewrite the main Yuncheng Skill around the process timeline

**Files:**
- Modify: `backend/docs/skills/yuncheng_alert_tracing_skill.md`
- Test: `backend/tests/tools/test_yuncheng_skill_publication.py`

- [ ] **Step 1: Add timeline construction rules after `AQI 口径`**

Add a `## 污染过程时间线生成规则` section containing these normative rules:

```markdown
## 污染过程时间线生成规则

- 以 `target_city_pollutants.json` 中目标城市小时数据作为主时间轴。
- 先读取告警时间、监测数据范围以及所有资产的实际有效时次，再划分本次过程阶段。
- 候选阶段为“告警前背景、污染开始变化、污染加速或持续、告警触发时刻、告警后最新变化、未来数小时趋势”；没有对应数据的阶段不得生成，相邻阶段无法区分时必须合并。
- 每个阶段标题必须写明实际时间点或时间范围，并按“变化—同期情况—业务意义”组织内容。
- 周边城市和气象小时数据优先挂接到相同小时；只有最近有效时次可用时，必须直接说明与主时间轴的时间差，不强行对齐。
- 轨迹按受体时刻挂接，火点按卫星观测时间挂接，图片按图中或元数据中的有效时次挂接，禁止用文件抓取时间替代业务有效时间。
- 预报统一放在未来阶段，并写明起报时间、预报时效和对应未来时间范围，不得与历史实况混写。
- 无法确认有效时次的资产不得推动正文判断，可放入附件，并在“需要补充确认的信息”中说明。
```

- [ ] **Step 2: Replace the current business report structure**

Replace `## 业务版报告结构` with these seven sections:

```markdown
1. 本次告警概览
2. 污染过程时间线
3. 当前情况与未来趋势
4. 可能影响因素
5. 现场行动安排
6. 需要补充确认的信息
7. 附件与数据来源
```

Define `污染过程时间线` as the largest core chapter. State that the old “关键变化看板”和“天气与传输影响” content must be embedded into corresponding time nodes rather than emitted as independent chapters. Require every time node to answer: what changed, what happened concurrently, and what the business team should watch or do next.

- [ ] **Step 3: Replace exhaustive image insertion with time-aware selection**

Update `QMD 输出要求` and expert asset instructions so that:

```markdown
- 图片紧跟其对应的时间节点，不集中陈列。
- 正文只选取能解释节点变化或支持下一步行动的图片，不以覆盖全部资产为目标。
- 图注必须说明实际有效时次、图上主要情况以及对现场关注的意义。
- 无法确认有效时次或与本次过程无直接关系的图片不进入正文。
```

Preserve the requirement that an available, relevant, time-confirmed image is included. Remove clauses that require every existing image to enter the report.

- [ ] **Step 4: Remove technical evidence-rating language**

Search the document and replace technical phrases such as `证据强弱如何` with business questions such as `这些情况对当前关注方向有什么影响`. Ensure the literal strings `证据强度`, `置信度`, and `假设竞争` do not appear anywhere in the published Skill.

- [ ] **Step 5: Run all Yuncheng publication tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/test_yuncheng_skill_publication.py
```

Expected: PASS. If an older assertion conflicts with the approved timeline structure, update that assertion only when it checks the removed chapter organization rather than an unchanged business boundary.

- [ ] **Step 6: Commit the main Skill change**

```bash
git add backend/docs/skills/yuncheng_alert_tracing_skill.md backend/tests/tools/test_yuncheng_skill_publication.py
git commit -m "feat: make yuncheng tracing reports timeline led"
```

### Task 3: Make both expert drafts time-addressable

**Files:**
- Modify: `backend/docs/skills/weather_analysis_expert.md`
- Modify: `backend/docs/skills/routine_monitoring_analysis_expert.md`
- Modify: `backend/tests/tools/test_yuncheng_skill_publication.py`

- [ ] **Step 1: Add failing expert timeline tests**

Append this test:

```python
@pytest.mark.asyncio
async def test_yuncheng_experts_return_time_ordered_business_drafts():
    weather = await ViewSkillTool().execute(name="weather_analysis_expert")
    routine = await ViewSkillTool().execute(name="routine_monitoring_analysis_expert")

    for viewed in (weather, routine):
        content = viewed["data"]["content"]
        assert "按实际时间顺序" in content
        assert "实际有效时次" in content
        assert "建议挂接的时间节点" in content

    assert "轨迹受体时刻" in weather["data"]["content"]
    assert "起报时间和预报时效" in weather["data"]["content"]
    assert "目标城市小时数据作为主时间轴" in routine["data"]["content"]
    assert "污染变化、周边情况和业务关注点" in routine["data"]["content"]
```

- [ ] **Step 2: Run the expert test and verify it fails**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/test_yuncheng_skill_publication.py::test_yuncheng_experts_return_time_ordered_business_drafts
```

Expected: FAIL because neither expert Skill currently requires a time-addressable draft.

- [ ] **Step 3: Update the weather expert Skill**

In `运城告警溯源场景资产要求`, add:

```markdown
草稿必须按实际时间顺序组织气象实况、轨迹和预报信息。每项使用的 JSON 记录或图片必须写明实际有效时次和建议挂接的时间节点；轨迹写明轨迹受体时刻，预报写明起报时间和预报时效。无法确认时次的图片只列入已阅读资产，不建议进入正文。
```

Change `建议插入图片` requirements to include `文件名、实际有效时次、建议挂接的时间节点和业务化图注`. Rename `不确定性和补证建议` to `需要补充确认的信息` for the Yuncheng scenario.

- [ ] **Step 4: Update the routine expert Skill**

In `运城告警溯源场景资产要求`, add:

```markdown
以目标城市小时数据作为主时间轴，按实际时间顺序划分污染过程。每个阶段必须写明时间点或时间范围，并包含“污染变化、周边情况和业务关注点”。周边城市、火点和预报只能按各自实际有效时次挂接；时间不一致时直接说明，不强行对齐。
```

Change image suggestions to include `实际有效时次` and `建议挂接的时间节点`. Rename the Yuncheng scenario’s missing-data language to `需要补充确认的信息`.

- [ ] **Step 5: Run the full publication test file**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q backend/tests/tools/test_yuncheng_skill_publication.py
```

Expected: PASS.

- [ ] **Step 6: Commit expert Skill changes**

```bash
git add backend/docs/skills/weather_analysis_expert.md backend/docs/skills/routine_monitoring_analysis_expert.md backend/tests/tools/test_yuncheng_skill_publication.py
git commit -m "feat: align yuncheng expert drafts by asset time"
```

### Task 4: Enforce timeline integration in the assistant task prompt

**Files:**
- Modify: `backend/config/task_lists/yuncheng_alert_tracing_assistant_prompt.md`
- Modify: `backend/tests/tools/test_yuncheng_skill_publication.py`

- [ ] **Step 1: Add a failing prompt contract test**

Append this synchronous test:

```python
def test_yuncheng_task_prompt_requires_timeline_integration():
    prompt = (
        __import__("pathlib")
        .Path("config/task_lists/yuncheng_alert_tracing_assistant_prompt.md")
        .read_text(encoding="utf-8")
    )

    for phrase in (
        "目标城市小时数据作为主时间轴",
        "读取所有资产的实际有效时次",
        "不强行对齐",
        "污染过程时间线",
        "变化—同期情况—业务意义",
        "图片紧跟其对应的时间节点",
    ):
        assert phrase in prompt
```

- [ ] **Step 2: Run the prompt test and verify it fails**

Run from `backend/`, matching the existing relative-path test convention:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/tools/test_yuncheng_skill_publication.py::test_yuncheng_task_prompt_requires_timeline_integration
```

Expected: FAIL because the current prompt only says to use the generic business report structure.

- [ ] **Step 3: Add explicit expert prompt requirements**

Expand steps 5 and 6 so every `call_sub_agent` prompt provides the actual asset paths and requires actual times. The weather expert request must ask for `实际有效时次、轨迹受体时刻、起报时间、预报时效、建议挂接的时间节点`; the routine expert request must ask for a target-city-led ordered process with `污染变化、周边情况和业务关注点`.

- [ ] **Step 4: Replace the integration instruction**

Replace step 9 with:

```markdown
9. 以目标城市小时数据作为主时间轴，读取所有资产的实际有效时次，动态划分污染阶段。将两个专家草稿按实际时间挂接；时间不同必须说明时间差，不强行对齐。按“变化—同期情况—业务意义”生成以“污染过程时间线”为核心的 `report.qmd`，图片紧跟其对应的时间节点。实况、轨迹和预报必须分别标明实际时次、受体时刻、起报时间或预报时效。
```

Keep steps 10–13 (report package export, Word validation, summary, social return) unchanged.

- [ ] **Step 5: Run prompt and publication tests**

Run:

```bash
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/tools/test_yuncheng_skill_publication.py
```

Expected: PASS.

- [ ] **Step 6: Commit the assistant prompt contract**

```bash
git add config/task_lists/yuncheng_alert_tracing_assistant_prompt.md tests/tools/test_yuncheng_skill_publication.py
git commit -m "feat: require timeline integration for yuncheng reports"
```

### Task 5: Verify the end-to-end document contract

**Files:**
- Verify: `backend/docs/skills/yuncheng_alert_tracing_skill.md`
- Verify: `backend/docs/skills/weather_analysis_expert.md`
- Verify: `backend/docs/skills/routine_monitoring_analysis_expert.md`
- Verify: `backend/config/task_lists/yuncheng_alert_tracing_assistant_prompt.md`
- Test: `backend/tests/tools/test_yuncheng_skill_publication.py`

- [ ] **Step 1: Run the focused Yuncheng tests in the configured environment**

```bash
cd /home/xckj/suyuan/backend
conda run -p /root/miniconda3/envs/backend_py311 pytest -q tests/tools/test_yuncheng_skill_publication.py
```

Expected: all tests pass.

- [ ] **Step 2: Check the published documents for forbidden technical language**

```bash
rg -n "证据强度|置信度|假设竞争" \
  docs/skills/yuncheng_alert_tracing_skill.md \
  docs/skills/weather_analysis_expert.md \
  docs/skills/routine_monitoring_analysis_expert.md \
  config/task_lists/yuncheng_alert_tracing_assistant_prompt.md
```

Expected: no output. If a generic expert document legitimately uses one of these words outside the Yuncheng output contract, rewrite it into plain business language because these documents directly guide the report drafts.

- [ ] **Step 3: Check timeline requirements are present across all four documents**

```bash
rg -n "实际有效时次|时间节点|污染过程时间线|主时间轴" \
  docs/skills/yuncheng_alert_tracing_skill.md \
  docs/skills/weather_analysis_expert.md \
  docs/skills/routine_monitoring_analysis_expert.md \
  config/task_lists/yuncheng_alert_tracing_assistant_prompt.md
```

Expected: every file has matching timeline requirements relevant to its responsibility.

- [ ] **Step 4: Review the final diff for scope and existing user changes**

```bash
git diff --check
git status --short
```

Expected: no whitespace errors; unrelated pre-existing modified files remain untouched. The implementation commits contain only the four documents and `backend/tests/tools/test_yuncheng_skill_publication.py`.

- [ ] **Step 5: Commit any verification-only corrections**

If verification required wording corrections:

```bash
git add docs/skills/yuncheng_alert_tracing_skill.md docs/skills/weather_analysis_expert.md docs/skills/routine_monitoring_analysis_expert.md config/task_lists/yuncheng_alert_tracing_assistant_prompt.md tests/tools/test_yuncheng_skill_publication.py
git commit -m "test: verify yuncheng timeline report workflow"
```

If no correction was needed, do not create an empty commit.
