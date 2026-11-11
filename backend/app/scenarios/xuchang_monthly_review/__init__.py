"""①月度特征分析：每月 2 号推送局长/科长（APP）的城市月度特征分析通报。

与场景④共用推送底座（受众组 + 微信队列），但通道为 APP 广播；证据包由
xuchang_monthly_review_evidence 抓取器在每月 2 日预计算（当月官方月报通常
中旬才发布，2 号出报告的城市对比用 SsfbCityDay 日值自算，标注实时参考
口径；官方 ProvinceMonthReport 已发布时优先官方口径）。
"""
