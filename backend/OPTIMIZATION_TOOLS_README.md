# 知识库性能优化工具集

## 📋 工具列表

### 1. 一键优化脚本（推荐）

**交互式菜单**：
```bash
cd backend && ./optimize-kb.sh
```

提供友好的交互式菜单：
- 检查所有知识库
- 交互式重建
- 强制重建

---

### 2. Python脚本（灵活）

**检查模式**：
```bash
cd backend && python optimize_all_knowledge_bases.py --dry-run
```

**交互式重建**：
```bash
cd backend && python optimize_all_knowledge_bases.py
```

**强制重建**：
```bash
cd backend && python optimize_all_knowledge_bases.py --force
```

---

## 🚀 快速开始

### 第一次使用（推荐流程）

```bash
# 1. 检查哪些知识库需要优化
cd backend && ./optimize-kb.sh
# 选择选项 1（检查模式）

# 2. 如果有需要优化的，执行重建
cd backend && ./optimize-kb.sh
# 选择选项 2（交互式重建）

# 3. 重新上传文档到重建的知识库
# 通过Web界面或API重新上传

# 4. 验证优化效果
# 进行检索测试，应该看到显著提升
```

---

## 📊 预期效果

### 检索速度对比

| 场景 | 优化前 | 优化后 | 提升 |
|------|--------|--------|------|
| 单库检索（155向量） | 12秒 | <0.1秒 | **120倍** |
| 多库并行检索 | 15秒 | <0.5秒 | **30倍** |
| 大型知识库（10万向量） | >100秒 | <1秒 | **100倍+** |

### 优化配置

```python
# 优化前（Qdrant默认）
full_scan_threshold = 10000  # 10000个向量以上才建索引

# 优化后
full_scan_threshold = 100    # 100个向量以上就建索引
```

---

## ⚙️ 工作原理

### 为什么需要重建？

1. **配置锁定**：Qdrant在Collection创建时锁定索引配置
2. **索引时机**：HNSW索引在插入向量时构建
3. **不自动更新**：已存在的Collection不会自动应用新配置

### 重建做什么？

```
1. 删除旧Collection（清除旧配置）
2. 创建新Collection（应用新配置 full_scan_threshold=100）
3. 重置文档统计（清零文档数、分块数）
4. 重新上传文档（向量插入时自动构建索引）
```

---

## 📝 注意事项

### ⚠️ 重要提醒

1. **备份数据**：重建前建议备份重要知识库的文档
2. **重新上传**：重建后必须重新上传文档才能恢复检索功能
3. **分批处理**：如果知识库很多，可以分批重建
4. **测试验证**：重建后建议先测试一个知识库，确认无问题后再批量处理

### ✅ 最佳实践

1. **先检查**：使用 `--dry-run` 模式检查哪些需要优化
2. **确认后执行**：非必要不使用 `--force` 模式
3. **监控日志**：注意观察重建过程中的错误信息
4. **验证效果**：重建后重新上传文档并测试检索速度

---

## 🔧 故障排查

### 常见问题

**Q: 脚本执行失败？**
```bash
# 检查Python环境
python --version

# 检查依赖
pip install qdrant-client sqlalchemy asyncpg

# 检查数据库连接
echo $DATABASE_URL
```

**Q: Collection删除失败？**
```bash
# 检查Qdrant连接
curl http://localhost:6333/collections

# 检查API密钥
curl -H "api-key: YOUR_KEY" http://180.184.30.94:6333/collections
```

**Q: 重建后检索仍慢？**
```bash
# 1. 确认文档已重新上传
# 2. 检查向量数量是否正确
# 3. 验证索引配置
curl -H "api-key: YOUR_KEY" \
  "http://180.184.30.94:6333/collections/kb_xxx" | jq '.result.config.params.hnsw_config'
```

---

## 📚 相关文档

- [详细优化指南](./KB_OPTIMIZATION_GUIDE.md)
- [Qdrant HNSW索引原理](https://qdrant.tech/documentation/concepts/indexing/)
- [性能调优最佳实践](https://qdrant.tech/documentation/guides/performance/)

---

## 🆘 获取帮助

如果遇到问题：

1. 查看日志文件：`backend-uvicorn.log`
2. 运行检查模式：`--dry-run`
3. 查看详细错误信息：脚本会输出完整的错误堆栈

---

## ✨ 总结

**一键优化**：
```bash
cd backend && ./optimize-kb.sh
```

**预期效果**：
- 检索速度提升 **30-120倍**
- 无需修改代码
- 自动检测并优化

**重建后**：
- 记得重新上传文档！
- 验证检索速度是否提升
- 享受闪电般的检索体验 ⚡
