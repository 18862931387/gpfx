# 持久化定时执行脚本
# 在 PowerShell 中运行: powershell.exe -WindowStyle Hidden -File D:\code\xlx\run_daemon.ps1
# 或双击此文件 (会弹出窗口)

$scriptPath = "D:\code\xlx"
$lastCheck = ""
$lastUpdate = ""

Write-Host "xlx 数据定时任务启动"
Write-Host "  run_check.ps1 → 14:30 尾盘分析"
Write-Host "  run_update.ps1 → 16:00 数据更新"
Write-Host "  每5分钟检测一次时间"
Write-Host "按 Ctrl+C 停止"

while ($true) {
    $now = Get-Date
    $today = $now.ToString("yyyy-MM-dd")
    $time = $now.ToString("HH:mm")
    
    # 14:30 跑尾盘分析 (每天一次)
    if ($time -eq "14:30" -and $lastCheck -ne $today) {
        Write-Host "$today 14:30 → 运行尾盘分析"
        Set-Location $scriptPath
        & "$scriptPath\run_check.ps1"
        $lastCheck = $today
    }
    
    # 16:00 跑数据更新 (每天一次)
    if ($time -eq "16:00" -and $lastUpdate -ne $today) {
        Write-Host "$today 16:00 → 运行数据更新"
        Set-Location $scriptPath
        & "$scriptPath\run_update.ps1"
        $lastUpdate = $today
    }
    
    Start-Sleep -Seconds 300  # 5分钟
}
