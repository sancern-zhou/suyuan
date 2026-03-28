"""
共享经验库辅助工具函数

提供解析Markdown格式共享经验文件的辅助函数，方便Agent操作共享经验库。
"""
import re
from typing import Dict, List, Optional
from pathlib import Path
import hashlib


def generate_anonymous_id(user_id: str) -> str:
    """
    SHA256哈希用户ID实现匿名化

    Args:
        user_id: 用户ID或标识符

    Returns:
        8位十六进制匿名ID
    """
    return hashlib.sha256(user_id.encode()).hexdigest()[:8]


def parse_shared_experiences(file_path: str) -> List[Dict]:
    """
    解析共享经验文件，返回结构化数据

    Args:
        file_path: 共享经验文件路径

    Returns:
        经验列表，每个元素包含 id, stars, usage_count, content 等字段
    """
    content = Path(file_path).read_text(encoding='utf-8')
    experiences = content.split('---')[1:]  # 跳过文件头

    parsed = []
    for exp in experiences:
        exp_content = exp.strip()
        if not exp_content:
            continue

        # 提取ID
        id_match = re.search(r'## 经验(\d+)：', exp_content)
        # 提取星数
        star_match = re.search(r'\((\d+)星\)', exp_content)
        # 提取使用次数（支持中文和英文冒号）
        usage_match = re.search(r'\*\*使用次数\*\*\s*[：:]\s*(\d+)', exp_content)
        # 提取标题
        title_match = re.search(r'## 经验\d+：(.+?)\s+⭐', exp_content)

        parsed.append({
            'id': id_match.group(1) if id_match else None,
            'title': title_match.group(1).strip() if title_match else '',
            'stars': int(star_match.group(1)) if star_match else 0,
            'usage_count': int(usage_match.group(1)) if usage_match else 0,
            'content': exp_content
        })
    return parsed


def get_next_experience_id(file_path: str) -> str:
    """
    获取下一个经验ID

    Args:
        file_path: 共享经验文件路径

    Returns:
        下一个经验ID（3位数字，如"016"）
    """
    experiences = parse_shared_experiences(file_path)
    if not experiences:
        return "001"
    max_id = max(int(exp['id']) for exp in experiences if exp['id'])
    return str(max_id + 1).zfill(3)


def update_experience_stats(file_path: str, experience_id: str, add_star: bool = True) -> Optional[str]:
    """
    更新经验统计信息（星数和使用次数）

    Args:
        file_path: 共享经验文件路径
        experience_id: 经验ID（如"001"）
        add_star: 是否添加星星（True）或仅增加使用次数（False）

    Returns:
        更新后的文件内容，如果失败返回None
    """
    content = Path(file_path).read_text(encoding='utf-8')

    # 查找目标经验段落
    # 使用 re.DOTALL 让 . 匹配换行符，找到从经验标题到下一个 --- 或文件末尾的内容
    exp_pattern = rf'(## 经验{experience_id}：.+?)(?=---|\Z)'
    exp_match = re.search(exp_pattern, content, re.DOTALL)

    if not exp_match:
        return None

    exp_content = exp_match.group(1)

    # 更新星数
    star_pattern = r'(## 经验\d+：.+?\s+⭐+?\s+\()(\d+)(星\))'
    star_match = re.search(star_pattern, exp_content)

    if star_match and add_star:
        current_stars = int(star_match.group(2))
        new_stars = current_stars + 1
        new_title = star_match.group(1) + str(new_stars) + star_match.group(3)
        exp_content = re.sub(star_pattern, new_title, exp_content, count=1)

    # 更新使用次数（支持中文和英文冒号）
    usage_pattern = r'(\*\*使用次数\*\*\s*[：:]\s*)(\d+)(\s)'
    usage_match = re.search(usage_pattern, exp_content)

    if usage_match:
        current_usage = int(usage_match.group(2))
        new_usage = current_usage + 1
        new_usage_text = usage_match.group(1) + str(new_usage) + usage_match.group(3)
        exp_content = re.sub(usage_pattern, new_usage_text, exp_content, count=1)

    # 替换原内容
    content = content[:exp_match.start()] + exp_content + content[exp_match.end():]

    return content


def search_experiences_by_keywords(file_path: str, keywords: List[str], limit: int = 10) -> List[Dict]:
    """
    根据关键词搜索经验

    Args:
        file_path: 共享经验文件路径
        keywords: 关键词列表
        limit: 返回结果数量限制

    Returns:
        匹配的经验列表，按星数和使用次数排序
    """
    experiences = parse_shared_experiences(file_path)

    # 计算每个经验的匹配分数
    scored = []
    for exp in experiences:
        score = 0
        content_lower = exp['content'].lower()

        for keyword in keywords:
            if keyword.lower() in content_lower:
                score += 1

        if score > 0:
            scored.append({
                **exp,
                'match_score': score
            })

    # 排序：先按匹配分数，再按星数，最后按使用次数
    scored.sort(key=lambda x: (x['match_score'], x['stars'], x['usage_count']), reverse=True)

    return scored[:limit]


def create_experience_markdown(
    title: str,
    category: str,
    tags: List[str],
    tools: List[str],
    contributor_id: str,
    problem: str,
    solution: str,
    results: str = "",
    lessons: str = ""
) -> str:
    """
    创建新经验的Markdown内容

    Args:
        title: 经验标题
        category: 分类（analysis/workflow/visualization等）
        tags: 标签列表
        tools: 使用的工具列表
        contributor_id: 贡献者匿名ID
        problem: 问题描述
        solution: 解决方案
        results: 结果（可选）
        lessons: 经验教训（可选）

    Returns:
        Markdown格式的经验内容
    """
    from datetime import datetime

    exp_id = "{PLACEHOLDER_ID}"  # 将由调用者替换
    stars = 0  # 新经验默认0星
    usage_count = 0
    created_date = datetime.now().strftime("%Y-%m-%d")

    markdown = f"""## 经验{exp_id}：{title} ⭐⭐⭐⭐⭐ ({stars}星)

**分类**：{category}
**标签**：{', '.join(tags)}
**工具**：{', '.join(tools)}
**贡献者**：{contributor_id}
**创建时间**：{created_date}
**使用次数**：{usage_count}

### 问题描述
{problem}

### 解决方案
{solution}
"""

    if results:
        markdown += f"\n### 结果\n{results}\n"

    if lessons:
        markdown += f"\n### 经验教训\n{lessons}\n"

    return markdown
