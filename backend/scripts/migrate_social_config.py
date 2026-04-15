#!/usr/bin/env python3
"""
社交配置迁移脚本

将旧版单账号配置迁移到新版多账号配置格式

使用方法:
    python backend/scripts/migrate_social_config.py [--dry-run]
"""

import argparse
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import yaml


def migrate_config(config_path: str, dry_run: bool = False) -> bool:
    """
    迁移配置文件

    Args:
        config_path: 配置文件路径
        dry_run: 是否只显示迁移内容而不实际修改

    Returns:
        是否成功迁移
    """
    config_file = Path(config_path)

    if not config_file.exists():
        print(f"❌ 配置文件不存在: {config_file}")
        return False

    try:
        # 读取配置
        with open(config_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        if not data:
            print("❌ 配置文件为空")
            return False

        # 检查是否需要迁移
        weixin_data = data.get('weixin', {})

        # 已经是新格式，不需要迁移
        if 'accounts' in weixin_data:
            print("✅ 配置已经是新版格式，无需迁移")
            return True

        # 旧格式：需要迁移
        if 'token' in weixin_data or 'enabled' in weixin_data:
            print("\n📋 检测到旧版配置，准备迁移...")

            # 构建新格式
            old_weixin = weixin_data
            new_weixin = {
                'enabled': old_weixin.get('enabled', False),
                'accounts': [
                    {
                        'id': 'account_1',
                        'name': 'WeChat Account 1',
                        'base_url': old_weixin.get('base_url', 'https://ilinkai.weixin.qq.com'),
                        'token': old_weixin.get('token', ''),
                        'enabled': True,
                        'allow_from': old_weixin.get('allow_from', ['*']),
                        'auto_start': True
                    }
                ]
            }

            data['weixin'] = new_weixin

            print("\n✨ 新配置预览:")
            print(yaml.dump(data['weixin'], allow_unicode=True, default_flow_style=False))

            if dry_run:
                print("\n🔍 [DRY RUN] 不会实际修改配置文件")
                return True

            # 备份旧配置
            backup_path = config_file.with_suffix('.yaml.bak')
            counter = 1
            while backup_path.exists():
                backup_path = config_file.with_suffix(f'.yaml.bak.{counter}')
                counter += 1

            config_file.rename(backup_path)
            print(f"💾 旧配置已备份到: {backup_path}")

            # 保存新配置
            with open(config_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(data, f, allow_unicode=True, default_flow_style=False)

            print(f"✅ 新配置已保存到: {config_file}")
            print("\n🎉 迁移完成！")
            return True

        else:
            print("ℹ️  配置中没有微信相关内容，跳过迁移")
            return True

    except Exception as e:
        print(f"❌ 迁移失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description='迁移社交平台配置文件到新版格式'
    )
    parser.add_argument(
        '--config',
        default='config/social_config.yaml',
        help='配置文件路径 (默认: config/social_config.yaml)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='只显示迁移内容，不实际修改文件'
    )

    args = parser.parse_args()

    print("=" * 60)
    print("社交配置迁移工具")
    print("=" * 60)
    print(f"配置文件: {args.config}")
    print(f"模式: {'预览（不会修改文件）' if args.dry_run else '正式迁移'}")
    print("=" * 60)
    print()

    success = migrate_config(args.config, args.dry_run)

    if success:
        print("\n✅ 迁移成功！")
        return 0
    else:
        print("\n❌ 迁移失败！")
        return 1


if __name__ == '__main__':
    sys.exit(main())
