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

try:
    from app.core.config import settings
    from app.core.dev_config import DEV_CONFIG
except Exception as e:
    import traceback
    print(f"❌ 导入配置模块失败: {e}")
    print("\n📋 详细错误信息:")
    print("-" * 50)
    traceback.print_exc()
    print("-" * 50)
    sys.exit(1)


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
    try:
        from app.core.logging_config import setup_logging as app_setup_logging
        app_setup_logging(settings.LOG_LEVEL)
    except Exception:
        # 回退到开发环境简化日志配置
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
        import traceback
        print(f"❌ Failed to start server: {e}")
        print("\n📋 详细错误信息:")
        print("-" * 50)
        traceback.print_exc()
        print("-" * 50)
        sys.exit(1)


if __name__ == "__main__":
    main()
