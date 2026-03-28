# 清理 HEARTBEAT.md 文件

## 方法一：使用清理脚本（推荐）

```bash
cd /home/xckj/suyuan
sudo ./clean_heartbeat.sh
```

## 方法二：手动执行命令

```bash
cd /home/xckj/suyuan

# 1. 备份原文件
sudo cp backend_data_registry/social/heartbeat/HEARTBEAT.md \
        backend_data_registry/social/heartbeat/HEARTBEAT.md.bak

# 2. 替换为清洁版本
sudo cp backend_data_registry/social/heartbeat/HEARTBEAT.md.new \
        backend_data_registry/social/heartbeat/HEARTBEAT.md

# 3. 验证结果
echo "=== 备份文件行数 ==="
wc -l backend_data_registry/social/heartbeat/HEARTBEAT.md.bak

echo "=== 新文件行数 ==="
wc -l backend_data_registry/social/heartbeat/HEARTBEAT.md

echo "=== 新文件内容 ==="
cat backend_data_registry/social/heartbeat/HEARTBEAT.md
```

## 清理前对比

- **原文件**: 1248 行，176 个重复任务
- **新文件**: 约 30 行，2 个示例任务

## 清理后的内容

```markdown
# 心跳任务列表

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
```

## 注意事项

- 原文件已备份为 `HEARTBEAT.md.bak`
- 示例任务默认为 `enabled: false`
- 如需启用任务，将 `enabled` 改为 `true`
