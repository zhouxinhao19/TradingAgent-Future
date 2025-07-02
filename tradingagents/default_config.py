import os

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results"),
    "data_dir": "/Users/yluo/Documents/Code/ScAI/FR1-data",
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": "openai",
    "deep_think_llm": "o4-mini",
    "quick_think_llm": "gpt-4o-mini",
    "backend_url": "https://api.openai.com/v1",
    # Debate and discussion settings
    "max_debate_rounds": 1,
    "max_risk_discuss_rounds": 1,
    "max_recur_limit": 100,
    # Tool settings
    "online_tools": True,

    # Database settings
    "database": {
        "mongodb": {
            "enabled": True,
            "host": os.getenv("MONGODB_HOST", "localhost"),
            "port": int(os.getenv("MONGODB_PORT", "27018")),
            "username": os.getenv("MONGODB_USERNAME", "admin"),
            "password": os.getenv("MONGODB_PASSWORD", "tradingagents123"),
            "database": os.getenv("MONGODB_DATABASE", "tradingagents"),
            "auth_source": os.getenv("MONGODB_AUTH_SOURCE", "admin"),
            "connection_string": os.getenv("MONGODB_CONNECTION_STRING", ""),
            "options": {
                "maxPoolSize": 50,
                "minPoolSize": 5,
                "maxIdleTimeMS": 30000,
                "serverSelectionTimeoutMS": 5000,
                "socketTimeoutMS": 20000,
                "connectTimeoutMS": 10000,
                "retryWrites": True,
                "w": "majority"
            }
        },
        "redis": {
            "enabled": True,
            "host": os.getenv("REDIS_HOST", "localhost"),
            "port": int(os.getenv("REDIS_PORT", "6380")),
            "password": os.getenv("REDIS_PASSWORD", "tradingagents123"),
            "db": int(os.getenv("REDIS_DB", "0")),
            "connection_string": os.getenv("REDIS_CONNECTION_STRING", ""),
            "options": {
                "max_connections": 50,
                "retry_on_timeout": True,
                "socket_timeout": 5,
                "socket_connect_timeout": 5,
                "health_check_interval": 30,
                "decode_responses": True,
                "encoding": "utf-8"
            },
            "cache": {
                "default_ttl": 3600,  # 默认缓存1小时
                "key_prefix": "tradingagents:",
                "compression": False,  # 暂时禁用压缩
                "serializer": "json"  # json, pickle, msgpack
            }
        }
    },

    # Cache settings
    "cache": {
        "enabled": True,
        "backend": "redis",  # redis, memory, file
        "ttl_settings": {
            "us_stock_data": 7200,      # 美股数据2小时
            "china_stock_data": 3600,   # A股数据1小时
            "us_news": 21600,           # 美股新闻6小时
            "china_news": 14400,        # A股新闻4小时
            "us_fundamentals": 86400,   # 美股基本面24小时
            "china_fundamentals": 43200, # A股基本面12小时
            "analysis_results": 1800,   # 分析结果30分钟
            "llm_responses": 3600       # LLM响应1小时
        },
        "max_memory_usage": "500MB",
        "cleanup_interval": 3600,  # 清理间隔1小时
        "compression": True
    }
}
