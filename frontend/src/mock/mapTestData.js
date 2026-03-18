/**
 * 地图功能测试数据
 * 模拟后端 generate_map 工具返回的数据格式
 */

// 基础地图配置测试数据（佛山高明区域）
export const mockMapConfig = {
  map_center: {
    lng: 112.893,
    lat: 22.900
  },
  station: {
    lng: 112.893,
    lat: 22.900,
    name: "高明孔堂监测站"
  },
  enterprises: [
    {
      lng: 112.910,
      lat: 22.915,
      name: "某精细化工有限公司",
      industry: "化工",
      distance: 2.8,
      score: 92,
      emissions: {
        "VOCs": "156 t/年",
        "PM2.5": "42 t/年",
        "SO2": "28 t/年"
      }
    },
    {
      lng: 112.875,
      lat: 22.890,
      name: "某涂装制造厂",
      industry: "涂装",
      distance: 1.9,
      score: 85,
      emissions: {
        "VOCs": "89 t/年",
        "PM10": "31 t/年"
      }
    },
    {
      lng: 112.920,
      lat: 22.880,
      name: "某热电厂",
      industry: "电力",
      distance: 3.5,
      score: 78,
      emissions: {
        "SO2": "215 t/年",
        "NOx": "180 t/年",
        "PM2.5": "68 t/年"
      }
    },
    {
      lng: 112.860,
      lat: 22.910,
      name: "某印刷包装公司",
      industry: "印刷",
      distance: 3.2,
      score: 73,
      emissions: {
        "VOCs": "64 t/年",
        "PM2.5": "15 t/年"
      }
    },
    {
      lng: 112.905,
      lat: 22.925,
      name: "某汽车制造企业",
      industry: "制造",
      distance: 3.8,
      score: 88,
      emissions: {
        "VOCs": "112 t/年",
        "PM10": "45 t/年",
        "NOx": "38 t/年"
      }
    },
    {
      lng: 112.850,
      lat: 22.895,
      name: "某建材厂",
      industry: "建筑",
      distance: 4.5,
      score: 65,
      emissions: {
        "PM10": "185 t/年",
        "PM2.5": "76 t/年"
      }
    },
    {
      lng: 112.930,
      lat: 22.905,
      name: "某冶金企业",
      industry: "冶金",
      distance: 4.2,
      score: 71,
      emissions: {
        "PM10": "220 t/年",
        "SO2": "95 t/年",
        "CO": "340 t/年"
      }
    },
    {
      lng: 112.888,
      lat: 22.878,
      name: "某小型工厂",
      industry: "其他",
      distance: 2.5,
      score: 58,
      emissions: {
        "VOCs": "32 t/年"
      }
    }
  ]
}

// 带上风向路径的测试数据
export const mockMapConfigWithPath = {
  ...mockMapConfig,
  upwind_paths: [
    {
      coordinates: [
        { lng: 112.850, lat: 22.870 },
        { lng: 112.870, lat: 22.885 },
        { lng: 112.885, lat: 22.895 },
        { lng: 112.893, lat: 22.900 }
      ]
    }
  ]
}

// 带风向扇区的测试数据
export const mockMapConfigWithSector = {
  ...mockMapConfigWithPath,
  sectors: [
    {
      coordinates: [
        { lng: 112.893, lat: 22.900 },  // 中心点（站点位置）
        { lng: 112.915, lat: 22.925 },  // 扇区边界1
        { lng: 112.930, lat: 22.915 },  // 扇区边界2
        { lng: 112.930, lat: 22.890 },  // 扇区边界3
        { lng: 112.915, lat: 22.880 }   // 扇区边界4
      ]
    }
  ]
}

// 完整功能测试数据（包含所有图层）
export const mockMapConfigFull = mockMapConfigWithSector

// 最小数据测试（仅站点和1个企业）
export const mockMapConfigMinimal = {
  map_center: {
    lng: 112.893,
    lat: 22.900
  },
  station: {
    lng: 112.893,
    lat: 22.900,
    name: "测试站点"
  },
  enterprises: [
    {
      lng: 112.910,
      lat: 22.915,
      name: "测试企业",
      industry: "化工",
      distance: 2.5
    }
  ]
}

// 导出默认配置
export default mockMapConfigFull
