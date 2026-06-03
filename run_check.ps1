# 尾盘分析 + 数据落地
# 每日 14:30 后运行
Set-Location D:\code\xlx
$env:Path += ";D:\Program Files\Git\bin"

Write-Host "=== 尾盘分析 $(Get-Date -Format 'HH:mm') ==="

# 启动 MySQL (如未运行)
$mysql = Get-Process mysqld -ErrorAction SilentlyContinue
if (-not $mysql) {
    Start-Process -FilePath "C:\Program Files\MySQL\MySQL Server 5.6\bin\mysqld.exe" `
        -ArgumentList "--datadir=C:\PROGRA~3\MySQL\MYSQLS~1.6\data --port=3306" `
        -WindowStyle Hidden
    Start-Sleep 3
    Write-Host "MySQL started"
}

python _afternoon_check.py 2>&1
