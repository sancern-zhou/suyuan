@echo off
REM Docker 快速部署脚本 (Windows)

echo ==================================================
echo 大气污染溯源分析系统 - Docker 部署
echo ==================================================

REM 检查 Docker
where docker >nul 2>nul
if %errorlevel% neq 0 (
    echo 错误: 未安装 Docker
    exit /b 1
)

REM 检查 Docker Compose
where docker-compose >nul 2>nul
if %errorlevel% neq 0 (
    docker compose version >nul 2>nul
    if %errorlevel% neq 0 (
        echo 错误: 未安装 Docker Compose
        exit /b 1
    )
)

REM 检查环境配置文件
if not exist "backend\.env.production" (
    echo 警告: 未找到 backend\.env.production
    echo 正在从模板创建...
    copy backend\.env.production.template backend\.env.production
    echo 请编辑 backend\.env.production 填写必需的 API 密钥后重新运行此脚本
    exit /b 1
)

REM 停止现有容器
echo 停止现有容器...
docker-compose down

REM 构建镜像
echo 构建 Docker 镜像...
docker-compose build --no-cache

REM 启动服务
echo 启动服务...
docker-compose up -d

REM 等待服务启动
echo 等待服务启动...
timeout /t 10 /nobreak >nul

REM 检查服务状态
echo 检查服务状态...
docker-compose ps

REM 测试后端健康
echo 测试后端健康状态...
curl -f http://localhost:8000/health >nul 2>nul
if %errorlevel% equ 0 (
    echo √ 后端服务运行正常
) else (
    echo × 后端服务启动失败
    docker-compose logs backend
    exit /b 1
)

REM 测试前端
echo 测试前端服务...
curl -f http://localhost/ >nul 2>nul
if %errorlevel% equ 0 (
    echo √ 前端服务运行正常
) else (
    echo × 前端服务启动失败
    docker-compose logs frontend
    exit /b 1
)

echo.
echo ==================================================
echo 部署成功！
echo ==================================================
echo.
echo 访问地址:
echo   前端: http://localhost
echo   后端: http://localhost:8000
echo   健康检查: http://localhost:8000/health
echo   API 文档: http://localhost:8000/docs
echo.
echo 常用命令:
echo   查看日志: docker-compose logs -f [service_name]
echo   重启服务: docker-compose restart [service_name]
echo   停止服务: docker-compose down
echo   查看状态: docker-compose ps
echo.
pause
