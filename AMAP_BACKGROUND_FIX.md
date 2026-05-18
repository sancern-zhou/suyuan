# 高德地图背景显示修复说明

## 问题描述
企业分布地图不显示底图背景，只显示标记点。

## 根本原因
高德地图 API 2.0 初始化时缺少 `features` 参数配置，导致地图底图要素（道路、建筑物等）不显示。

## 已修复的文件

### 1. generate_tracing_report/tool.py（已修复）
✅ 已自动修改：添加了 `features: ['bg', 'road', 'building', 'point']` 和 `mapStyle: 'amap://styles/normal'` 参数

### 2. amap_template.html（需手动修复）
由于文件属于 root 用户，需要手动应用修复。

## 修复步骤

### 方法一：使用临时文件（推荐）
```bash
# 复制修复后的文件（覆盖原文件）
sudo cp /tmp/amap_template_fixed.html /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/amap_template.html

# 或者直接修改权限后复制
sudo chown xckj:xckj /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/amap_template.html
cp /tmp/amap_template_fixed.html /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/amap_template.html
```

### 方法二：手动编辑
```bash
sudo nano /home/xckj/suyuan/backend/app/tools/visualization/chart_image_renderer/amap_template.html
```

找到第 54-59 行的地图初始化代码：
```javascript
var map = new AMap.Map('amap-container', {
    center: [center.lng, center.lat],
    zoom: 12,
    viewMode: '2D',
    resizeEnable: true
});
```

修改为：
```javascript
var map = new AMap.Map('amap-container', {
    center: [center.lng, center.lat],
    zoom: 12,
    viewMode: '2D',
    resizeEnable: true,
    features: ['bg', 'road', 'building', 'point'],
    mapStyle: 'amap://styles/normal'
});
```

## 修复效果
- ✅ 地图将正常显示底图（道路、建筑物等）
- ✅ 标记点和标签保持正常显示
- ✅ 适用于 HTML 报告和 PNG 截图

## 验证
修复后重新生成报告，地图应显示完整背景。
