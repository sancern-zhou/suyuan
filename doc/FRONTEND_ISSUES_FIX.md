# 前端问题修复说明

本文档记录了前端三个问题的诊断和修复方案。

## 问题汇总

### ✅ 问题1：高德地图无法展示

**现象**：地图区域显示空白或显示"AMap Key未配置"

**根本原因**：
- 后端`.env`文件中的`AMAP_PUBLIC_KEY=your_amap_key_here`是占位符，不是真实的API key
- 高德地图SDK无法加载，导致地图无法渲染

**解决方案**：配置真实的高德地图API Key

#### 步骤1：申请高德地图API Key

1. 访问高德开放平台：https://lbs.amap.com/
2. 注册/登录账号
3. 进入"应用管理" → "我的应用"
4. 创建新应用（应用名称：大气污染溯源分析系统）
5. 添加Key：
   - Key名称：Web端Key
   - 服务平台：Web端(JS API)
   - 提交后获得Key（格式如：a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6）

#### 步骤2：配置到后端

编辑`backend/.env`文件：

```env
# 替换此行
AMAP_PUBLIC_KEY=your_amap_key_here

# 改为你的真实Key
AMAP_PUBLIC_KEY=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6
```

#### 步骤3：重启后端服务

```bash
cd backend
# 停止当前服务（Ctrl+C）
# 重新启动
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

#### 验证修复

1. 打开浏览器控制台（F12）
2. 在前端页面刷新
3. 查看控制台日志，应该看到：
   - `✅ 配置加载成功: { amapPublicKey: 'a1b2c3...', ... }`
   - `🗺️ 初始化地图, payload: {...}`
   - `✅ 添加站点标记: ...`

4. 地图应该正常显示，包括：
   - 站点标记（红色）
   - 企业标记（灰色）
   - 上风向路径（绿色线条）

---

### ✅ 问题2：区域对比分析图无法展示

**现象**：区域对比分析模块中，图表区域为空或显示错误

**可能原因**：
1. 后端数据格式问题
2. 前端payload解析问题
3. 无周边站点数据

**诊断方法**：

#### 步骤1：检查浏览器控制台

打开F12开发者工具，查看Console：

```javascript
// 应该看到这样的日志
📊 添加模块结果: regional_analysis {...}
📊 添加可视化: timeseries {...}

// 如果看到错误，记录错误信息
```

#### 步骤2：检查后端日志

查看后端控制台输出：

```bash
# 正常情况应该看到
regional_comparison_data_prepared total_points=... sample_point={...}
regional_comparison_payload_generated x_count=... series_count=...

# 如果data_points为0，说明没有数据
```

#### 步骤3：检查数据获取

在前端Console中检查实际数据：

```javascript
// 查看流式响应的regional_analysis模块数据
// 应该包含visuals数组，其中有timeseries类型的visual
```

**常见问题和解决**：

1. **无周边站点数据**
   - 检查查询的站点是否有周边站点
   - 调整搜索距离参数（默认5km）

2. **时间字段不匹配**
   - 后端已支持多种字段名（timePoint, time, 时间, timestamp）
   - 检查实际API返回的字段名

3. **数据值为null**
   - 检查时间范围内是否有监测数据
   - 尝试调整查询时间范围

**临时验证方法**：

如果怀疑是payload格式问题，可以在`frontend/src/components/ChartsPanel.tsx`添加调试日志：

```typescript
const ChartsPanel: React.FC<Props> = ({ type, payload, meta }) => {
  console.log('📊 ChartsPanel渲染:', { type, payload, meta })
  // ... 其余代码
}
```

---

### ✅ 问题3：AI对话框点击放大后页面无任何展示 **（已修复）**

**现象**：点击对话框右上角的"放大到全屏"按钮后，页面变成空白

**根本原因**：
在`App.tsx`中，点击放大按钮时：
- `viewMode`切换为`'full'`（全屏模式）
- 但全屏模式渲染的是`modules`数组（来自旧的非流式API响应）
- 而对话内容存储在`messages`数组中（来自流式API追加的消息）
- **两个数据源完全不同**，导致全屏模式无内容显示

**修复内容**：

已修改`frontend/src/App.tsx`第277-325行：

**修改前**：
```typescript
{viewMode === 'full' && (
  <>
    <main>
      {/* 渲染modules数组（空的！） */}
      {modules.map((m) => <ModuleCard module={m} />)}
    </main>
  </>
)}
```

**修改后**：
```typescript
{viewMode === 'full' && (
  <>
    <main>
      {/* 渲染messages数组（有内容！） */}
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        {messages.map((m, i) => (
          <div key={i}>
            <ChatMessageRenderer msg={m} amapKey={...} />
          </div>
        ))}
      </div>
    </main>
  </>
)}
```

**效果**：
- 点击"放大到全屏"按钮后，会显示和对话框中一样的内容
- 所有的文本、图表、地图都会在全屏模式下正常展示
- 消息布局优化：用户消息靠右（蓝色），AI消息靠左（灰色）

---

## 测试验证

### 完整测试流程

1. **启动后端**（确保已配置AMAP_PUBLIC_KEY）
   ```bash
   cd backend
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

2. **启动前端**
   ```bash
   cd frontend
   npm run dev
   ```

3. **测试查询**
   - 输入："分析广州从化天湖站2025年8月9日的O3污染情况"
   - 观察对话框中的流式输出

4. **检查地图**
   - 在"气象条件分析"模块中应该看到地图
   - 包含站点标记和周边企业

5. **检查图表**
   - 在"区域对比分析"模块中应该看到时序对比图
   - 多条线代表不同站点的浓度变化

6. **测试全屏模式**
   - 点击对话框右上角"放大"按钮
   - 页面应该显示完整的对话内容
   - 所有图表和地图都应该正常显示

---

## 故障排查清单

### 地图问题
- [ ] 检查`.env`中的AMAP_PUBLIC_KEY是否为真实key
- [ ] 检查浏览器控制台是否有AMap加载错误
- [ ] 检查是否有网络访问限制（防火墙、代理）
- [ ] 验证高德地图key的配额是否用完

### 图表问题
- [ ] 检查后端日志中是否有数据获取成功
- [ ] 检查`payload`格式是否符合预期
- [ ] 检查前端Console是否有ECharts错误
- [ ] 验证时间范围内是否有监测数据

### 全屏模式问题
- [ ] 已修复，如果仍有问题，检查Git是否有未提交的本地修改
- [ ] 清除浏览器缓存后重试
- [ ] 检查`viewMode`状态是否正确切换

---

## 附录：浏览器调试技巧

### 查看流式响应

在浏览器Console中监控：

```javascript
// 监听流式事件
// 在前端代码中，所有流式事件都会打印到console
// 关键日志：
// 🚀 开始流式分析
// 📝 步骤事件: {...}
// 📊 模块结果: {...}
// ✅ 分析完成
```

### 检查API响应

在Network标签中：

1. 找到`/api/analyze`请求
2. 查看Response（流式数据，每行以`data:`开头）
3. 检查每个模块的payload结构

### 检查地图加载

在Console中：

```javascript
// 检查AMap对象是否存在
console.log(window.AMap)

// 如果undefined，说明SDK未加载
// 如果是对象，说明加载成功
```

---

## 总结

| 问题 | 状态 | 需要用户操作 |
|------|------|------------|
| 高德地图无法展示 | 需配置 | ✅ 配置AMAP_PUBLIC_KEY |
| 区域对比分析图无法展示 | 待验证 | 提供具体错误信息 |
| AI对话框放大后无内容 | ✅ 已修复 | 无需操作 |

**下一步**：
1. 请按照说明配置高德地图API Key
2. 重启后端服务
3. 测试所有功能
4. 如果区域对比分析图仍有问题，请提供：
   - 浏览器Console截图
   - 后端日志截图
   - 使用的查询语句
