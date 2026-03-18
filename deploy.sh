# Docker 快速部署脚本 (Linux/macOS)

#!/bin/bash

set -e

echo "=================================================="
echo "大气污染溯源分析系统 - Docker 部署"
echo "=================================================="

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 检查 Docker 和 Docker Compose
echo -e "${YELLOW}检查环境...${NC}"
if ! command -v docker &> /dev/null; then
    echo -e "${RED}错误: 未安装 Docker${NC}"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}错误: 未安装 Docker Compose${NC}"
    exit 1
fi

# 检查环境配置文件
if [ ! -f "backend/.env.production" ]; then
    echo -e "${YELLOW}警告: 未找到 backend/.env.production${NC}"
    echo -e "${YELLOW}正在从模板创建...${NC}"
    cp backend/.env.production.template backend/.env.production
    echo -e "${RED}请编辑 backend/.env.production 填写必需的 API 密钥后重新运行此脚本${NC}"
    exit 1
fi

# 停止现有容器
echo -e "${YELLOW}停止现有容器...${NC}"
docker-compose down

# 构建镜像
echo -e "${YELLOW}构建 Docker 镜像...${NC}"
docker-compose build --no-cache

# 启动服务
echo -e "${YELLOW}启动服务...${NC}"
docker-compose up -d

# 等待服务健康检查
echo -e "${YELLOW}等待服务启动...${NC}"
sleep 10

# 检查服务状态
echo -e "${YELLOW}检查服务状态...${NC}"
docker-compose ps

# 测试后端健康
echo -e "${YELLOW}测试后端健康状态...${NC}"
if curl -f http://localhost:8000/health &> /dev/null; then
    echo -e "${GREEN}✓ 后端服务运行正常${NC}"
else
    echo -e "${RED}✗ 后端服务启动失败${NC}"
    docker-compose logs backend
    exit 1
fi

# 测试前端
echo -e "${YELLOW}测试前端服务...${NC}"
if curl -f http://localhost/ &> /dev/null; then
    echo -e "${GREEN}✓ 前端服务运行正常${NC}"
else
    echo -e "${RED}✗ 前端服务启动失败${NC}"
    docker-compose logs frontend
    exit 1
fi

echo ""
echo -e "${GREEN}=================================================="
echo "部署成功！"
echo "=================================================="
echo ""
echo "访问地址:"
echo "  前端: http://localhost"
echo "  后端: http://localhost:8000"
echo "  健康检查: http://localhost:8000/health"
echo "  API 文档: http://localhost:8000/docs"
echo ""
echo "常用命令:"
echo "  查看日志: docker-compose logs -f [service_name]"
echo "  重启服务: docker-compose restart [service_name]"
echo "  停止服务: docker-compose down"
echo "  查看状态: docker-compose ps"
echo -e "${NC}"
