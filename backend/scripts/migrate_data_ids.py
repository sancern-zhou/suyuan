#!/usr/bin/env python3
"""
ID迁移脚本：将短格式ID (data_N) 迁移为长格式ID (schema:v1:hash)

方案A：统一长格式ID
- 扫描所有session目录
- 识别短格式ID文件 (data_1.json, data_2.json等)
- 从文件内容推断schema
- 重命名为长格式ID
- 更新相关引用

用法:
    python scripts/migrate_data_ids.py --session-dir /tmp/agent_session_xxx
    python scripts/migrate_data_ids.py --all  # 迁移所有session
"""

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Optional, Tuple
import structlog

logger = structlog.get_logger()


def infer_schema_from_data(data) -> str:
    """
    从数据内容推断schema

    Args:
        data: 原始数据（dict或list）

    Returns:
        推断的schema名称
    """
    if isinstance(data, dict):
        # 检查PMF结果
        if "sources" in data and "timeseries" in data:
            return "pmf_result"

        # 检查OBM/OFP结果
        if "species_ofp" in data or "category_summary" in data:
            return "obm_ofp_result"

        # 检查VOCs统一数据
        if "species_data" in data:
            return "vocs_unified"

        # 检查图表配置
        if "type" in data and "data" in data and "meta" in data:
            return "chart_config"

        # 默认返回data
        return "data"

    elif isinstance(data, list) and data:
        first_item = data[0]
        if isinstance(first_item, dict):
            # 检查VOCs样本
            if "species_data" in first_item:
                return "vocs"

            # 检查颗粒物样本
            if any(key in first_item for key in ["pm25", "pm10", "so2", "no2"]):
                return "particulate"

        return "data"

    return "data"


def migrate_short_to_long_format(file_path: Path) -> Tuple[str, str]:
    """
    将单个短格式ID文件迁移为长格式

    Args:
        file_path: 短格式ID文件路径 (如 data_1.json)

    Returns:
        (old_id, new_id): 迁移前后的ID
    """
    # 读取数据
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 推断schema
    schema = infer_schema_from_data(data)

    # 生成新的长格式ID
    from uuid import uuid4
    new_id = f"{schema}:v1:{uuid4().hex}"

    # 计算新文件路径
    # 替换文件名中的:为_
    safe_filename = new_id.replace(":", "_")
    new_path = file_path.parent / f"{safe_filename}.json"

    # 移动文件
    file_path.rename(new_path)

    old_short_id = file_path.stem
    logger.info(
        "migrated_data_id",
        old_id=old_short_id,
        new_id=new_id,
        schema=schema,
        old_path=str(file_path),
        new_path=str(new_path)
    )

    return old_short_id, new_id


def update_session_references(session_dir: Path, id_mapping: Dict[str, str]):
    """
    更新session中其他文件对旧ID的引用

    Args:
        session_dir: session目录
        id_mapping: ID映射表 {old_id: new_id}
    """
    # 需要更新的文件类型
    update_patterns = [
        "*.json",
        "*.md",
        "*.txt"
    ]

    for pattern in update_patterns:
        for file_path in session_dir.rglob(pattern):
            # 跳过已迁移的数据文件
            if "data_" in file_path.stem and file_path.suffix == ".json":
                continue

            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                updated = False
                for old_id, new_id in id_mapping.items():
                    # 替换文件名中的引用
                    if old_id in content:
                        content = content.replace(old_id, new_id)
                        updated = True

                if updated:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(content)
                    logger.info(
                        "updated_file_references",
                        file=str(file_path),
                        updated_ids=list(id_mapping.keys())
                    )

            except Exception as e:
                logger.warning(
                    "failed_to_update_file",
                    file=str(file_path),
                    error=str(e)
                )


def migrate_session(session_dir: Path) -> Dict[str, str]:
    """
    迁移单个session的所有短格式ID

    Args:
        session_dir: session目录路径

    Returns:
        ID映射表 {old_id: new_id}
    """
    id_mapping = {}

    # 查找所有短格式ID文件
    data_files = list(session_dir.glob("data_*.json"))

    if not data_files:
        logger.info("no_data_files_found", session=str(session_dir))
        return id_mapping

    logger.info(
        "start_migrating_session",
        session=str(session_dir),
        data_file_count=len(data_files)
    )

    # 迁移每个文件
    for file_path in data_files:
        old_id, new_id = migrate_short_to_long_format(file_path)
        id_mapping[old_id] = new_id

    # 更新其他文件中的引用
    if id_mapping:
        update_session_references(session_dir, id_mapping)

    logger.info(
        "completed_migrating_session",
        session=str(session_dir),
        migrated_count=len(id_mapping)
    )

    return id_mapping


def find_all_sessions(base_dir: Path) -> list[Path]:
    """查找所有session目录"""
    sessions = []
    for item in base_dir.iterdir():
        if item.is_dir() and item.name.startswith("agent_session_"):
            sessions.append(item)
    return sessions


def main():
    parser = argparse.ArgumentParser(
        description="迁移短格式ID (data_N) 到长格式ID (schema:v1:hash)"
    )
    parser.add_argument(
        "--session-dir",
        type=str,
        help="单个session目录路径"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="迁移所有session"
    )
    parser.add_argument(
        "--base-dir",
        type=str,
        default="/tmp",
        help="基础目录 (默认: /tmp)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式，不实际执行迁移"
    )

    args = parser.parse_args()

    if not args.session_dir and not args.all:
        parser.error("必须指定 --session-dir 或 --all")

    base_path = Path(args.base_dir)

    if args.dry_run:
        logger.info("DRY RUN MODE - No files will be modified")

    total_migrated = 0
    total_sessions = 0

    try:
        if args.session_dir:
            # 迁移单个session
            session_path = Path(args.session_dir)
            if not session_path.exists():
                logger.error("session_dir_not_found", path=str(session_path))
                return 1

            if not args.dry_run:
                id_mapping = migrate_session(session_path)
                total_migrated += len(id_mapping)
                total_sessions += 1
            else:
                # 预览模式
                data_files = list(session_path.glob("data_*.json"))
                logger.info(
                    "dry_run_migration_preview",
                    session=str(session_path),
                    data_file_count=len(data_files)
                )

        elif args.all:
            # 迁移所有session
            sessions = find_all_sessions(base_path)
            logger.info(
                "found_sessions",
                count=len(sessions),
                base_dir=str(base_path)
            )

            for session_path in sessions:
                if not args.dry_run:
                    id_mapping = migrate_session(session_path)
                    total_migrated += len(id_mapping)
                    total_sessions += 1
                else:
                    # 预览模式
                    data_files = list(session_path.glob("data_*.json"))
                    logger.info(
                        "dry_run_session_preview",
                        session=str(session_path.name),
                        data_file_count=len(data_files)
                    )

        # 输出统计
        if args.dry_run:
            print("\n" + "="*80)
            print("预览模式 - 以下文件将被迁移:")
            print("="*80)
        else:
            print("\n" + "="*80)
            print("迁移完成!")
            print("="*80)

        print(f"处理session数: {total_sessions}")
        print(f"迁移文件数: {total_migrated}")
        print("="*80 + "\n")

        if not args.dry_run:
            logger.info(
                "migration_completed",
                total_sessions=total_sessions,
                total_migrated=total_migrated
            )

        return 0

    except Exception as e:
        logger.error(
            "migration_failed",
            error=str(e),
            exc_info=True
        )
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
