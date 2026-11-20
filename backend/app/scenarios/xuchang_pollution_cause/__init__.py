"""④污染原因分析：许昌市 PM2.5 日均高于相邻五市均值 30%（轻度污染及以上
为 20%，新标准日均 ≥ 60 μg/m³ 口径）触发的通报推送。

模块组成：
- constants：事件类型与触发口径常量
- （fetcher）app/fetchers/xuchang_pollution_cause_trigger.py：每日评估相邻
  五市对比规则，落触发证据包并发事件
- notification：workflow 处理器——LLM 生成污染原因分析通报 → 微信群 RPA
  队列 + APP 广播（受众组：科长/局长）
"""
