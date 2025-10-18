#!/bin/bash

################################################################################
# TradingAgents-CN 一键安装脚本 (Linux)
# 适用于: Ubuntu 20.04+, CentOS 7+, Debian 10+
# 版本: 1.0.0-preview
################################################################################

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_header() {
    echo ""
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# 检查是否为 root 用户
check_root() {
    if [ "$EUID" -eq 0 ]; then 
        print_warning "检测到以 root 用户运行，建议使用普通用户"
        read -p "是否继续? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
}

# 检查 Docker 是否已安装
check_docker() {
    print_info "检查 Docker 安装状态..."
    if command -v docker &> /dev/null; then
        DOCKER_VERSION=$(docker --version | awk '{print $3}' | sed 's/,//')
        print_success "Docker 已安装 (版本: $DOCKER_VERSION)"
        return 0
    else
        print_warning "Docker 未安装"
        return 1
    fi
}

# 安装 Docker
install_docker() {
    print_header "安装 Docker"
    
    # 检测操作系统
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
    else
        print_error "无法检测操作系统类型"
        exit 1
    fi
    
    print_info "检测到操作系统: $OS"
    
    case $OS in
        ubuntu|debian)
            print_info "使用 apt 安装 Docker..."
            sudo apt-get update
            sudo apt-get install -y ca-certificates curl gnupg
            sudo install -m 0755 -d /etc/apt/keyrings
            curl -fsSL https://download.docker.com/linux/$OS/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
            sudo chmod a+r /etc/apt/keyrings/docker.gpg
            echo \
              "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$OS \
              $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
              sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
            sudo apt-get update
            sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            ;;
        centos|rhel|fedora)
            print_info "使用 yum 安装 Docker..."
            sudo yum install -y yum-utils
            sudo yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
            sudo yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
            ;;
        *)
            print_error "不支持的操作系统: $OS"
            print_info "请手动安装 Docker: https://docs.docker.com/engine/install/"
            exit 1
            ;;
    esac
    
    # 启动 Docker 服务
    sudo systemctl start docker
    sudo systemctl enable docker
    
    # 将当前用户添加到 docker 组
    sudo usermod -aG docker $USER
    
    print_success "Docker 安装完成"
    print_warning "请注销并重新登录以使 docker 组权限生效，然后重新运行此脚本"
    exit 0
}

# 检查 Docker Compose
check_docker_compose() {
    print_info "检查 Docker Compose 安装状态..."
    if docker compose version &> /dev/null; then
        COMPOSE_VERSION=$(docker compose version | awk '{print $4}')
        print_success "Docker Compose 已安装 (版本: $COMPOSE_VERSION)"
        return 0
    else
        print_error "Docker Compose 未安装"
        return 1
    fi
}

# 创建项目目录
create_project_dir() {
    print_header "创建项目目录"
    
    # 默认安装目录
    DEFAULT_DIR="$HOME/tradingagents-demo"
    
    read -p "请输入安装目录 [默认: $DEFAULT_DIR]: " INSTALL_DIR
    INSTALL_DIR=${INSTALL_DIR:-$DEFAULT_DIR}
    
    if [ -d "$INSTALL_DIR" ]; then
        print_warning "目录已存在: $INSTALL_DIR"
        read -p "是否删除并重新创建? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            rm -rf "$INSTALL_DIR"
        else
            print_info "使用现有目录"
        fi
    fi
    
    mkdir -p "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    
    print_success "项目目录创建完成: $INSTALL_DIR"
}

# 下载配置文件
download_files() {
    print_header "下载配置文件"
    
    GITHUB_RAW="https://raw.githubusercontent.com/hsliuping/TradingAgents-CN/v1.0.0-preview"
    
    print_info "下载 Docker Compose 配置..."
    curl -fsSL "$GITHUB_RAW/docker-compose.hub.nginx.yml" -o docker-compose.hub.nginx.yml
    
    print_info "下载环境配置文件..."
    curl -fsSL "$GITHUB_RAW/.env.docker" -o .env
    
    print_info "下载 Nginx 配置..."
    mkdir -p nginx
    curl -fsSL "$GITHUB_RAW/nginx/nginx.conf" -o nginx/nginx.conf
    
    print_success "配置文件下载完成"
}

# 配置 API 密钥
configure_api_keys() {
    print_header "配置 API 密钥"
    
    print_info "系统需要至少一个 AI 模型的 API 密钥才能正常工作"
    echo ""
    echo "支持的 AI 模型:"
    echo "  1. 阿里百炼 (DashScope) - 推荐，国产模型"
    echo "  2. DeepSeek - 推荐，性价比高"
    echo "  3. OpenAI - 需要国外网络"
    echo "  4. 其他 (百度文心、Google Gemini 等)"
    echo ""
    
    read -p "是否现在配置 API 密钥? (y/n) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        # 阿里百炼
        read -p "请输入阿里百炼 API Key (留空跳过): " DASHSCOPE_KEY
        if [ ! -z "$DASHSCOPE_KEY" ]; then
            sed -i "s/DASHSCOPE_API_KEY=.*/DASHSCOPE_API_KEY=$DASHSCOPE_KEY/" .env
            print_success "阿里百炼 API Key 已配置"
        fi
        
        # DeepSeek
        read -p "请输入 DeepSeek API Key (留空跳过): " DEEPSEEK_KEY
        if [ ! -z "$DEEPSEEK_KEY" ]; then
            sed -i "s/DEEPSEEK_API_KEY=.*/DEEPSEEK_API_KEY=$DEEPSEEK_KEY/" .env
            sed -i "s/DEEPSEEK_ENABLED=.*/DEEPSEEK_ENABLED=true/" .env
            print_success "DeepSeek API Key 已配置"
        fi
        
        # Tushare
        read -p "请输入 Tushare Token (留空跳过): " TUSHARE_TOKEN
        if [ ! -z "$TUSHARE_TOKEN" ]; then
            sed -i "s/TUSHARE_TOKEN=.*/TUSHARE_TOKEN=$TUSHARE_TOKEN/" .env
            sed -i "s/TUSHARE_ENABLED=.*/TUSHARE_ENABLED=true/" .env
            print_success "Tushare Token 已配置"
        fi
    else
        print_warning "跳过 API 密钥配置，请稍后手动编辑 .env 文件"
    fi
}

# 启动服务
start_services() {
    print_header "启动服务"
    
    print_info "拉取 Docker 镜像..."
    docker compose -f docker-compose.hub.nginx.yml pull
    
    print_info "启动所有服务..."
    docker compose -f docker-compose.hub.nginx.yml up -d
    
    print_info "等待服务启动 (约 30 秒)..."
    sleep 30
    
    print_success "服务启动完成"
}

# 导入初始配置
import_config() {
    print_header "导入初始配置"
    
    print_info "导入系统配置和创建管理员账号..."
    docker exec -it tradingagents-backend python scripts/import_config_and_create_user.py
    
    print_success "初始配置导入完成"
}

# 显示访问信息
show_access_info() {
    print_header "安装完成"
    
    # 获取服务器 IP
    SERVER_IP=$(hostname -I | awk '{print $1}')
    
    echo ""
    print_success "🎉 TradingAgents-CN 安装成功！"
    echo ""
    echo -e "${GREEN}访问地址:${NC}"
    echo -e "  ${BLUE}http://$SERVER_IP${NC}"
    echo -e "  ${BLUE}http://localhost${NC} (本机访问)"
    echo ""
    echo -e "${GREEN}默认登录信息:${NC}"
    echo -e "  用户名: ${YELLOW}admin${NC}"
    echo -e "  密码: ${YELLOW}admin123${NC}"
    echo ""
    echo -e "${GREEN}常用命令:${NC}"
    echo -e "  查看服务状态: ${BLUE}docker compose -f docker-compose.hub.nginx.yml ps${NC}"
    echo -e "  查看日志: ${BLUE}docker compose -f docker-compose.hub.nginx.yml logs -f${NC}"
    echo -e "  停止服务: ${BLUE}docker compose -f docker-compose.hub.nginx.yml stop${NC}"
    echo -e "  启动服务: ${BLUE}docker compose -f docker-compose.hub.nginx.yml start${NC}"
    echo -e "  重启服务: ${BLUE}docker compose -f docker-compose.hub.nginx.yml restart${NC}"
    echo ""
    print_info "安装目录: $INSTALL_DIR"
    echo ""
}

# 主函数
main() {
    clear
    print_header "TradingAgents-CN 一键安装脚本 (Linux)"
    
    # 检查 root
    check_root
    
    # 检查并安装 Docker
    if ! check_docker; then
        read -p "是否自动安装 Docker? (y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            install_docker
        else
            print_error "Docker 是必需的，请手动安装后重新运行此脚本"
            exit 1
        fi
    fi
    
    # 检查 Docker Compose
    if ! check_docker_compose; then
        print_error "Docker Compose 未安装，请升级 Docker 到最新版本"
        exit 1
    fi
    
    # 创建项目目录
    create_project_dir
    
    # 下载配置文件
    download_files
    
    # 配置 API 密钥
    configure_api_keys
    
    # 启动服务
    start_services
    
    # 导入初始配置
    import_config
    
    # 显示访问信息
    show_access_info
}

# 运行主函数
main

