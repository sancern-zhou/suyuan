$start = Get-Date

$body = @{
    question = "查询揭阳市2025-11-16到2025-12-15期间的小时粒度的用于溯源分析的VOCs挥发性有机化合物组分数据（小时粒度），包括苯系物、烷烃、烯烃、酯类等具体物种浓度"
} | ConvertTo-Json -Encoding UTF8

$resp = Invoke-WebRequest `
    -Uri "http://180.184.91.74:9092/api/uqp/query" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body `
    -TimeoutSec 120

$elapsed = (Get-Date) - $start

Write-Output ("ELAPSED:{0:n2}s" -f $elapsed.TotalSeconds)
Write-Output ("HTTP_STATUS:{0}" -f $resp.StatusCode)
Write-Output ("CONTENT_LENGTH:{0}" -f $resp.RawContentLength)

