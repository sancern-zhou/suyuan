"""
清空现有全局记忆

所有用户从空白记忆开始
"""

from pathlib import Path
import shutil
from datetime import datetime


def clear_global_memory():
    """清空全局记忆目录"""
    global_memory_dir = Path("backend_data_registry/social/memory")

    if not global_memory_dir.exists():
        print("全局记忆目录不存在，无需清理")
        return

    # 备份
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_dir = Path(f"backend_data_registry/social/memory_backup_{timestamp}")

    try:
        shutil.copytree(global_memory_dir, backup_dir)
        print(f"已备份到: {backup_dir}")
    except Exception as e:
        print(f"备份失败: {e}")
        return

    # 清空
    try:
        shutil.rmtree(global_memory_dir)
        global_memory_dir.mkdir(parents=True, exist_ok=True)

        # 创建 .gitkeep
        (global_memory_dir / ".gitkeep").write_text("")

        print("全局记忆已清空，所有用户将从空白记忆开始")
    except Exception as e:
        print(f"清空失败: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("警告：此操作将清空所有用户的全局记忆")
    print("备份将自动创建")
    print("=" * 60)

    confirm = input("确认继续？(yes/no): ")

    if confirm.lower() == "yes":
        clear_global_memory()
    else:
        print("操作已取消")
