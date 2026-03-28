#!/usr/bin/env python3
"""
清理 HEARTBEAT.md 文件的 Python 脚本
使用 subprocess 执行 sudo 命令
"""

import subprocess
import sys
from pathlib import Path

# 文件路径
HEARTBEAT_DIR = Path("backend_data_registry/social/heartbeat")
BACKUP_FILE = HEARTBEAT_DIR / "HEARTBEAT.md.bak"
NEW_FILE = HEARTBEAT_DIR / "HEARTBEAT.md.new"
TARGET_FILE = HEARTBEAT_DIR / "HEARTBEAT.md"

# 清洁版本内容
CLEAN_CONTENT = """# 心跳任务列表

此文件包含Agent需要定期检查和执行的任务。

## 任务格式

```yaml
- name: 任务名称
  schedule: "cron表达式"
  description: 任务描述
  enabled: true
  channels: ["weixin", "qq"]
```

## 示例任务

- name: 每日空气质量报告
  schedule: "0 9 * * *"  # 每天早上9点
  description: 每天早上9点生成并发送当月广东省空气质量AQI日历图到微信
  enabled: false
  channels: ['weixin']

- name: PM2.5超标监控
  schedule: "*/30 * * * *"  # 每30分钟
  description: 检查PM2.5是否超过75μg/m³
  enabled: false
  channels: ['weixin', 'qq']
"""


def run_sudo_command(command: list) -> bool:
    """执行 sudo 命令"""
    try:
        result = subprocess.run(
            ["sudo"] + command,
            check=True,
            capture_output=True,
            text=True
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"命令执行失败: {' '.join(command)}")
        print(f"错误: {e.stderr}")
        return False
    except FileNotFoundError:
        print("sudo 命令未找到")
        return False


def main():
    print("正在清理 HEARTBEAT.md 文件...\n")

    # 1. 备份原文件
    print("1. 备份原文件...")
    if not run_sudo_command(["cp", str(TARGET_FILE), str(BACKUP_FILE)]):
        print("   备份失败")
        return 1
    print("   备份成功")

    # 2. 创建临时文件
    print("2. 创建清洁版本...")
    temp_file = Path("/tmp/heartbeat_clean.md")
    temp_file.write_text(CLEAN_CONTENT, encoding="utf-8")
    print("   临时文件已创建")

    # 3. 替换原文件
    print("3. 替换原文件...")
    if not run_sudo_command(["cp", str(temp_file), str(TARGET_FILE)]):
        print("   替换失败")
        return 1
    print("   替换成功")

    # 4. 设置权限
    print("4. 设置文件权限...")
    run_sudo_command(["chmod", "644", str(TARGET_FILE)])
    run_sudo_command(["chown", "root:root", str(TARGET_FILE)])
    print("   权限设置完成")

    # 5. 清理临时文件
    temp_file.unlink()

    # 6. 显示结果
    print("\n清理完成！\n")
    print("=" * 50)
    print("新文件内容：")
    print("=" * 50)
    print(TARGET_FILE.read_text(encoding="utf-8"))
    print("=" * 50)

    # 统计信息
    backup_lines = len(BACKUP_FILE.read_text(encoding="utf-8").splitlines())
    new_lines = len(TARGET_FILE.read_text(encoding="utf-8").splitlines())

    print(f"\n统计信息：")
    print(f"- 原文件行数: {backup_lines}")
    print(f"- 新文件行数: {new_lines}")
    print(f"- 清理任务数: {backup_lines - new_lines}")
    print(f"- 备份文件: {BACKUP_FILE}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
