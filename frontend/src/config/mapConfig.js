/**
 * 高德地图配置
 * 包含地图样式、标记图标、行业配色等
 */

// 地图基础配置
export const MAP_CONFIG = {
  zoom: 12,                          // 默认缩放级别
  pitch: 0,                          // 俯仰角度（0为正视）
  viewMode: '2D',                    // 视图模式（2D/3D）
  // 使用标准样式确保底图显示
  mapStyle: 'amap://styles/normal',
  features: ['bg', 'road', 'building'], // 地图要素
  showIndoorMap: false,              // 不显示室内地图
  resizeEnable: true,                // 允许地图自适应容器大小
  dragEnable: true,                  // 允许拖拽
  zoomEnable: true,                  // 允许缩放
  doubleClickZoom: true,             // 双击缩放
  scrollWheel: true                  // 鼠标滚轮缩放
}

// 标记图标配置（使用高德内置图标）
export const MARKER_ICONS = {
  station: {
    // 站点标记 - 使用高德内置红色标记
    size: [36, 36],
    offset: [-18, -36],
    content: `
      <div style="position:relative;width:36px;height:36px;">
        <div style="position:absolute;bottom:0;left:50%;transform:translateX(-50%);width:24px;height:24px;background:#1976d2;border-radius:50% 50% 50% 0;transform:rotate(-45deg) translateX(-50%);border:3px solid white;box-shadow:0 2px 8px rgba(0,0,0,0.3);"></div>
        <div style="position:absolute;bottom:8px;left:50%;transform:translateX(-50%);width:8px;height:8px;background:white;border-radius:50%;"></div>
      </div>
    `
  },
  enterprise: {
    // 企业标记 - 使用自定义橙色标记
    size: [28, 28],
    offset: [-14, -28],
    content: `
      <div style="position:relative;width:28px;height:28px;">
        <div style="position:absolute;bottom:0;left:50%;transform:translateX(-50%);width:18px;height:18px;background:#FFA500;border-radius:50% 50% 50% 0;transform:rotate(-45deg) translateX(-50%);border:2px solid white;box-shadow:0 1px 6px rgba(0,0,0,0.3);"></div>
        <div style="position:absolute;bottom:6px;left:50%;transform:translateX(-50%);width:6px;height:6px;background:white;border-radius:50%;"></div>
      </div>
    `
  }
}

// 行业配色方案
export const INDUSTRY_COLORS = {
  '化工': '#FF6B6B',
  '制造': '#FFA500',
  '电力': '#FFD700',
  '交通': '#4169E1',
  '建筑': '#8B4513',
  '冶金': '#9370DB',
  '印刷': '#FF69B4',
  '涂装': '#32CD32',
  '其他': '#999999'
}

// 路径样式配置
export const PATH_STYLES = {
  upwind: {
    strokeColor: '#FF4444',        // 更鲜艳的红色
    strokeWeight: 5,                // 增加线宽（原3px→5px）
    strokeOpacity: 1.0,             // 完全不透明（原0.8→1.0）
    strokeStyle: 'dashed',
    zIndex: 50
  }
}

// 扇区样式配置
export const SECTOR_STYLES = {
  default: {
    fillColor: '#4ECDC4',
    fillOpacity: 0.3,               // 增加填充透明度（原0.2→0.3）
    strokeColor: '#2BA89F',          // 更深的边框颜色
    strokeWeight: 3,                 // 增加边框宽度（原2→3）
    strokeOpacity: 0.8,              // 提高边框透明度（原0.6→0.8）
    zIndex: 10
  }
}

// 信息窗口样式（CSS 字符串，将通过 style 标签注入）
export const INFO_WINDOW_STYLES = `
  .enterprise-popup {
    padding: 16px;
    min-width: 220px;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }

  .enterprise-popup h3 {
    margin: 0 0 12px 0;
    font-size: 15px;
    font-weight: 600;
    color: #333;
    border-bottom: 2px solid #1976d2;
    padding-bottom: 8px;
  }

  .enterprise-popup .info-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
    font-size: 13px;
    line-height: 1.5;
  }

  .enterprise-popup .info-row .label {
    color: #666;
    font-weight: 500;
    min-width: 60px;
  }

  .enterprise-popup .info-row .value {
    font-weight: 600;
    color: #333;
    text-align: right;
    flex: 1;
  }

  .enterprise-popup .info-section {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid #f0f0f0;
  }

  .enterprise-popup .info-section h4 {
    margin: 0 0 8px 0;
    font-size: 13px;
    font-weight: 600;
    color: #666;
  }

  .enterprise-popup .emissions-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
    font-size: 12px;
  }

  .enterprise-popup .emission-item {
    background: #f8f8f8;
    padding: 6px 8px;
    border-radius: 4px;
  }

  .enterprise-popup .emission-item .em-label {
    color: #888;
    font-size: 11px;
  }

  .enterprise-popup .emission-item .em-value {
    color: #333;
    font-weight: 600;
    margin-top: 2px;
  }
`
