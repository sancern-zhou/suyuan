"""
共享经验库辅助函数单元测试
"""
import pytest
import tempfile
import os
from pathlib import Path
from app.social.shared_experience_utils import (
    generate_anonymous_id,
    parse_shared_experiences,
    get_next_experience_id,
    update_experience_stats,
    search_experiences_by_keywords,
    create_experience_markdown
)


class TestAnonymousID:
    """测试匿名ID生成"""

    def test_generate_anonymous_id(self):
        """测试生成匿名ID"""
        id1 = generate_anonymous_id("user123")
        id2 = generate_anonymous_id("user123")
        id3 = generate_anonymous_id("user456")

        # 相同用户ID生成相同匿名ID
        assert id1 == id2
        # 不同用户ID生成不同匿名ID
        assert id1 != id3
        # 长度应该是8位
        assert len(id1) == 8


class TestParseSharedExperiences:
    """测试解析共享经验文件"""

    @pytest.fixture
    def sample_experience_file(self):
        """创建示例经验文件"""
        content = """# Agent共享经验库

最后更新：2026-03-28 14:30:00
总经验数：2
总星数：9

---

## 经验001：VOCs数据PMF源解析最佳实践 ⭐⭐⭐⭐⭐ (5星)

**分类**：analysis
**标签**：VOCs, PMF, 源解析, 广州
**工具**：app.tools.analysis.calculate_pmf
**贡献者**：a1b2c3d4
**创建时间**：2026-03-28
**使用次数**：12

### 问题描述
分析广州2024年VOCs数据，进行PMF源解析时，如何确定最佳因子数？

### 解决方案
1. 先使用 `get_vocs_data` 获取广州2024年VOCs数据
2. 使用 `calculate_pmf` 时建议配置：
   - factor_range: [3, 7]
   - random_seed: 42（保证可重复性）
3. 根据Q值和残差分析，选择5因子方案效果最好

### 结果
5因子解析出的主要源：机动车排放、溶剂使用、工业排放、燃烧源、背景

---

## 经验002：O3污染上风向分析流程 ⭐⭐⭐⭐ (4星)

**分类**：workflow
**标签**：O3, 上风向, 企业排查
**工具**：app.tools.analysis.analyze_upwind
**贡献者**：e5f6g7h8
**创建时间**：2026-03-27
**使用次数**：8

### 问题描述
广州O3污染超标时，如何快速排查上风向潜在污染源？

### 解决流程
1. 获取气象数据：`get_weather_data` 获取风向风速
2. 后向轨迹：使用HYSPLIT模型计算48小时后向向轨迹
3. 上风向企业：`analyze_upwind_enterprises` 筛选上风向20km内的化工企业
4. 优先排查：VOCs排放量大、距离近的企业

### 经验教训
- 风速<2m/s时，本地累积影响更大，上风向分析意义降低
- 关注风向变化时段，排查下风向转换前的上风向企业
"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md', encoding='utf-8') as f:
            f.write(content)
            temp_file = f.name

        yield temp_file

        # 清理
        os.unlink(temp_file)

    def test_parse_experiences(self, sample_experience_file):
        """测试解析经验文件"""
        experiences = parse_shared_experiences(sample_experience_file)

        assert len(experiences) == 2

        # 验证第一条经验
        exp1 = experiences[0]
        assert exp1['id'] == '001'
        assert exp1['stars'] == 5
        assert exp1['usage_count'] == 12
        assert 'VOCs' in exp1['content']

        # 验证第二条经验
        exp2 = experiences[1]
        assert exp2['id'] == '002'
        assert exp2['stars'] == 4
        assert exp2['usage_count'] == 8
        assert 'O3' in exp2['content']

    def test_get_next_experience_id(self, sample_experience_file):
        """测试获取下一个经验ID"""
        next_id = get_next_experience_id(sample_experience_file)
        assert next_id == '003'

    def test_get_next_experience_id_empty_file(self):
        """测试空文件的下一个ID"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md') as f:
            f.write("# Agent共享经验库\n\n---\n")
            temp_file = f.name

        try:
            next_id = get_next_experience_id(temp_file)
            assert next_id == '001'
        finally:
            os.unlink(temp_file)

    def test_update_experience_stats_add_star(self, sample_experience_file):
        """测试为经验加星"""
        updated_content = update_experience_stats(sample_experience_file, '001', add_star=True)

        assert updated_content is not None
        assert '(6星)' in updated_content
        assert '**使用次数**：13' in updated_content

    def test_update_experience_stats_increment_usage(self, sample_experience_file):
        """测试仅增加使用次数"""
        updated_content = update_experience_stats(sample_experience_file, '002', add_star=False)

        assert updated_content is not None
        # 星数应该保持不变
        assert '(4星)' in updated_content
        # 使用次数应该增加
        assert '**使用次数**：9' in updated_content

    def test_update_experience_stats_invalid_id(self, sample_experience_file):
        """测试更新不存在的经验"""
        updated_content = update_experience_stats(sample_experience_file, '999', add_star=True)

        assert updated_content is None


class TestSearchExperiences:
    """测试搜索经验"""

    @pytest.fixture
    def sample_experience_file(self):
        """创建示例经验文件"""
        content = """# Agent共享经验库

---

## 经验001：VOCs数据PMF源解析最佳实践 ⭐⭐⭐⭐⭐ (5星)

**分类**：analysis
**标签**：VOCs, PMF, 源解析, 广州
**工具**：app.tools.analysis.calculate_pmf
**贡献者**：a1b2c3d4
**创建时间**：2026-03-28
**使用次数**：12

### 问题描述
分析广州2024年VOCs数据，进行PMF源解析时，如何确定最佳因子数？

### 解决方案
使用 calculate_pmf 工具进行PMF源解析

---

## 经验002：O3污染上风向分析流程 ⭐⭐⭐⭐ (4星)

**分类**：workflow
**标签**：O3, 上风向, 企业排查
**工具**：app.tools.analysis.analyze_upwind
**贡献者**：e5f6g7h8
**创建时间**：2026-03-27
**使用次数**：8

### 问题描述
广州O3污染超标时，如何快速排查上风向潜在污染源？

### 解决流程
使用气象数据和上风向企业分析
"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.md', encoding='utf-8') as f:
            f.write(content)
            temp_file = f.name

        yield temp_file

        os.unlink(temp_file)

    def test_search_by_keywords(self, sample_experience_file):
        """测试关键词搜索"""
        results = search_experiences_by_keywords(sample_experience_file, ['VOCs', 'PMF'])

        assert len(results) > 0
        assert results[0]['id'] == '001'
        assert results[0]['match_score'] == 2

    def test_search_results_sorted_by_relevance(self, sample_experience_file):
        """测试搜索结果按相关性排序"""
        results = search_experiences_by_keywords(sample_experience_file, ['O3', '上风向'])

        # 应该匹配到经验002
        assert len(results) > 0
        assert '002' in [r['id'] for r in results]

    def test_search_no_results(self, sample_experience_file):
        """测试无匹配结果"""
        results = search_experiences_by_keywords(sample_experience_file, ['不存在的关键词'])

        assert len(results) == 0


class TestCreateExperienceMarkdown:
    """测试创建经验Markdown"""

    def test_create_full_experience(self):
        """测试创建完整的经验"""
        markdown = create_experience_markdown(
            title="测试经验",
            category="analysis",
            tags=["测试", "单元测试"],
            tools=["test_tool"],
            contributor_id="test123",
            problem="测试问题描述",
            solution="测试解决方案",
            results="测试结果",
            lessons="测试经验教训"
        )

        assert '## 经验{PLACEHOLDER_ID}：测试经验' in markdown
        assert '**分类**：analysis' in markdown
        assert '**标签**：测试, 单元测试' in markdown
        assert '### 问题描述' in markdown
        assert '测试问题描述' in markdown
        assert '### 结果' in markdown
        assert '### 经验教训' in markdown

    def test_create_minimal_experience(self):
        """测试创建最小经验（仅必填字段）"""
        markdown = create_experience_markdown(
            title="最小经验",
            category="workflow",
            tags=["工作流"],
            tools=["workflow_tool"],
            contributor_id="contributor1",
            problem="问题",
            solution="解决方案"
        )

        assert '## 经验{PLACEHOLDER_ID}：最小经验' in markdown
        assert '### 问题描述' in markdown
        assert '### 结果' not in markdown
        assert '### 经验教训' not in markdown
