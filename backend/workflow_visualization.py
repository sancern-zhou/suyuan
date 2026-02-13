"""
生成工作流程对比的可视化图表（Mermaid格式）
"""

# 当前流程（串行为主）
current_workflow = """
```mermaid
gantt
    title 当前溯源分析工作流程（总耗时: ~29秒）
    dateFormat  s
    axisFormat %Ss

    section 初始化
    参数提取(LLM)           :a1, 0, 3s
    站点信息(API)           :a2, after a1, 1s

    section 数据获取
    核心数据并行            :b1, after a2, 5s

    section 分析阶段
    上风向企业(API)         :c1, after b1, 2s
    组分分析(API+LLM)       :c2, after c1, 8s
    区域对比(LLM)          :c3, after c2, 3s
    气象分析(LLM)          :c4, after c3, 3s
    综合分析(LLM)          :c5, after c4, 4s
```

# 优化后流程（方案B: 保守优化）
optimized_workflow = """
```mermaid
gantt
    title 优化后工作流程 - 方案B（总耗时: ~21秒，提升28%）
    dateFormat  s
    axisFormat %Ss

    section 初始化
    参数提取(LLM)           :a1, 0, 3s
    站点信息(API)           :a2, after a1, 1s

    section 数据获取
    核心数据并行            :b1, after a2, 5s

    section 第一波并行
    上风向(API)            :c1, after b1, 2s
    组分数据(API)          :c2, after b1, 5s
    多指标图(处理)         :c3, after b1, 1s

    section 第二波并行(LLM)
    组分分析               :d1, after c2, 3s
    区域对比               :d2, after b1, 3s
    气象分析               :d3, after c1, 3s

    section 最终汇总
    综合分析(LLM)          :e1, after d3, 4s
```

# 激进优化（方案A）
aggressive_workflow = """
```mermaid
gantt
    title 优化后工作流程 - 方案A（总耗时: ~18秒，提升38%）
    dateFormat  s
    axisFormat %Ss

    section 初始化
    参数提取(LLM)           :a1, 0, 3s
    站点信息(API)           :a2, after a1, 1s

    section 数据获取(并行优化)
    目标站点数据            :b1, after a2, 3s
    气象数据               :b2, after a2, 3s
    周边站点数据            :b3, after a2, 5s
    组分数据               :b4, after a2, 5s

    section Layer 1 并行
    上风向(API)            :c1, after b2, 2s
    多指标图(处理)         :c2, after b1, 1s

    section Layer 2 并行(LLM)
    组分分析               :d1, after b4, 3s
    区域对比               :d2, after b3, 3s
    气象分析               :d3, after c1, 3s

    section Layer 3
    综合分析(LLM)          :e1, after d3, 4s
```

print("工作流程对比可视化 (Mermaid甘特图)")
print("=" * 80)
print("\n### 当前流程")
print(current_workflow)
print("\n### 方案B: 保守优化")
print(optimized_workflow)
print("\n### 方案A: 激进优化")
print(aggressive_workflow)
