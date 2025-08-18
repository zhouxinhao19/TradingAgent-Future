"""
TradingAgents-CN Backend Entry Point
支持 python -m app 启动方式
"""

import uvicorn
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import settings
from app.core.dev_config import DEV_CONFIG


def main():
    """主启动函数"""
    print("🚀 Starting TradingAgents-CN Backend...")
    print(f"📍 Host: {settings.HOST}")
    print(f"🔌 Port: {settings.PORT}")
    print(f"🐛 Debug Mode: {settings.DEBUG}")
    print(f"📚 API Docs: http://{settings.HOST}:{settings.PORT}/docs" if settings.DEBUG else "📚 API Docs: Disabled in production")
    print("-" * 50)

    # 获取uvicorn配置
    uvicorn_config = DEV_CONFIG.get_uvicorn_config(settings.DEBUG)

    # 设置简化的日志配置
    print("🔧 正在设置日志配置...")
    DEV_CONFIG.setup_logging(settings.DEBUG)
    print("✅ 日志配置设置完成")

    try:
        uvicorn.run(
            "app.main:app",
            host=settings.HOST,
            port=settings.PORT,
            **uvicorn_config
        )
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
