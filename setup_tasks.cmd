@REM A股数据系统 — 定时任务批处理
@REM 用法: 在 Windows 任务计划程序中创建两个任务
@REM
@REM 任务1: 每日14:30 尾盘分析
@REM   启动: powershell.exe
@REM   参数: -File D:\code\xlx\run_check.ps1
@REM
@REM 任务2: 每日16:00 收盘数据更新
@REM   启动: powershell.exe  
@REM   参数: -File D:\code\xlx\run_update.ps1

echo A股数据系统定时任务
echo.
echo 两个任务需要创建:
echo  1. 14:30 - python _afternoon_check.py (尾盘分析)
echo  2. 16:00 - python daily_update.py (数据更新+备份)
echo.
echo 创建命令 (需管理员权限):
echo   schtasks /create /tn "xlx_afternoon" /tr "powershell.exe -File D:\code\xlx\run_check.ps1" /sc daily /st 14:30 /f
echo   schtasks /create /tn "xlx_update" /tr "powershell.exe -File D:\code\xlx\run_update.ps1" /sc daily /st 16:00 /f
