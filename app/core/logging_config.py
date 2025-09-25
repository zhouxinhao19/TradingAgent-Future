import logging
import logging.config
import sys
from pathlib import Path
import os

from app.core.logging_context import LoggingContextFilter, trace_id_var

try:
    import tomllib as toml_loader  # Python 3.11+
except Exception:
    try:
        import tomli as toml_loader  # Python 3.10 fallback
    except Exception:
        toml_loader = None


def resolve_logging_cfg_path() -> Path:
    """根据环境选择日志配置文件路径（可能不存在）
    优先 docker 配置，其次默认配置。
    """
    profile = os.environ.get("LOGGING_PROFILE", "").lower()
    is_docker_env = os.environ.get("DOCKER", "").lower() in {"1", "true", "yes"} or Path("/.dockerenv").exists()
    cfg_candidate = "config/logging_docker.toml" if profile == "docker" or is_docker_env else "config/logging.toml"
    return Path(cfg_candidate)


class SimpleJsonFormatter(logging.Formatter):
    """Minimal JSON formatter without external deps."""
    def format(self, record: logging.LogRecord) -> str:
        import json
        obj = {
            "time": self.formatTime(record, "%Y-%m-%d %H:%M:%S"),
            "name": record.name,
            "level": record.levelname,
            "trace_id": getattr(record, "trace_id", "-"),
            "message": record.getMessage(),
        }
        return json.dumps(obj, ensure_ascii=False)

def setup_logging(log_level: str = "INFO"):
    """
    设置应用日志配置：
    1) 优先尝试从 config/logging.toml 读取并转化为 dictConfig
    2) 失败或不存在时，回退到内置默认配置
    """
    # 1) 若存在 TOML 配置且可解析，则优先使用
    try:
        cfg_path = resolve_logging_cfg_path()
        if cfg_path.exists() and toml_loader is not None:
            with cfg_path.open("rb") as f:
                toml_data = toml_loader.load(f)

            # 读取基础字段
            logging_root = toml_data.get("logging", {})
            level = logging_root.get("level", log_level)
            fmt_cfg = logging_root.get("format", {})
            fmt_console = fmt_cfg.get(
                "console", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            fmt_file = fmt_cfg.get(
                "file", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            # 确保文本格式包含 trace_id（若未显式包含）
            if "%(trace_id)" not in str(fmt_console):
                fmt_console = str(fmt_console) + " trace=%(trace_id)s"
            if "%(trace_id)" not in str(fmt_file):
                fmt_file = str(fmt_file) + " trace=%(trace_id)s"

            handlers_cfg = logging_root.get("handlers", {})
            file_handler_cfg = handlers_cfg.get("file", {})
            file_dir = file_handler_cfg.get("directory", "./logs")
            file_level = file_handler_cfg.get("level", "DEBUG")
            max_bytes = file_handler_cfg.get("max_size", "10MB")
            # 支持 "10MB" 形式
            if isinstance(max_bytes, str) and max_bytes.upper().endswith("MB"):
                try:
                    max_bytes = int(float(max_bytes[:-2]) * 1024 * 1024)
                except Exception:
                    max_bytes = 10 * 1024 * 1024
            elif not isinstance(max_bytes, int):
                max_bytes = 10 * 1024 * 1024
            backup_count = int(file_handler_cfg.get("backup_count", 5))

            Path(file_dir).mkdir(parents=True, exist_ok=True)
            webapi_log = str(Path(file_dir) / "webapi.log")
            worker_log = str(Path(file_dir) / "worker.log")

            # JSON 开关：保持向后兼容（json/mode 仅控制台）；新增 file_json/file_mode 控制文件 handler
            use_json_console = bool(fmt_cfg.get("json", False)) or str(fmt_cfg.get("mode", "")).lower() == "json"
            use_json_file = (
                bool(fmt_cfg.get("file_json", False))
                or bool(fmt_cfg.get("json_file", False))
                or str(fmt_cfg.get("file_mode", "")).lower() == "json"
            )

            logging_config = {
                "version": 1,
                "disable_existing_loggers": False,
                "filters": {
                    "request_context": {"()": "app.core.logging_context.LoggingContextFilter"}
                },
                "formatters": {
                    "console_fmt": {
                        "format": fmt_console,
                        "datefmt": "%Y-%m-%d %H:%M:%S",
                    },
                    "file_fmt": {
                        "format": fmt_file,
                        "datefmt": "%Y-%m-%d %H:%M:%S",
                    },
                    "json_console_fmt": {
                        "()": "app.core.logging_config.SimpleJsonFormatter"
                    },
                    "json_file_fmt": {
                        "()": "app.core.logging_config.SimpleJsonFormatter"
                    },
                },
                "handlers": {
                    "console": {
                        "class": "logging.StreamHandler",
                        "formatter": "json_console_fmt" if use_json_console else "console_fmt",
                        "level": level,
                        "filters": ["request_context"],
                        "stream": sys.stdout,
                    },
                    "file": {
                        "class": "logging.handlers.RotatingFileHandler",
                        "formatter": "json_file_fmt" if use_json_file else "file_fmt",
                        "level": file_level,
                        "filename": webapi_log,
                        "maxBytes": max_bytes,
                        "backupCount": backup_count,
                        "encoding": "utf-8",
                        "filters": ["request_context"],
                    },
                    "worker_file": {
                        "class": "logging.handlers.RotatingFileHandler",
                        "formatter": "json_file_fmt" if use_json_file else "file_fmt",
                        "level": file_level,
                        "filename": worker_log,
                        "maxBytes": max_bytes,
                        "backupCount": backup_count,
                        "encoding": "utf-8",
                        "filters": ["request_context"],
                    },
                },
                "loggers": {
                    "webapi": {"level": "INFO", "handlers": ["console", "file"], "propagate": True},
                    "worker": {"level": "DEBUG", "handlers": ["console", "worker_file"], "propagate": False},
                    "uvicorn": {"level": "INFO", "handlers": ["console", "file"], "propagate": False},
                    "fastapi": {"level": "INFO", "handlers": ["console", "file"], "propagate": False},
                },
                "root": {"level": level, "handlers": ["console"]},
            }
            logging.config.dictConfig(logging_config)
            logging.getLogger("webapi").info(f"Logging configured from {cfg_path}")
            return
    except Exception as e:
        # TOML 存在但加载失败，回退到默认配置
        logging.getLogger("webapi").warning(f"Failed to load logging.toml, fallback to defaults: {e}")

    # 2) 默认内置配置（与原先一致）
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {"request_context": {"()": "app.core.logging_context.LoggingContextFilter"}},
        "formatters": {
            "default": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s trace=%(trace_id)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(pathname)s:%(lineno)d - %(message)s trace=%(trace_id)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "level": log_level,
                "filters": ["request_context"],
                "stream": sys.stdout,
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "detailed",
                "level": "DEBUG",
                "filters": ["request_context"],
                "filename": "logs/webapi.log",
                "maxBytes": 10485760,
                "backupCount": 5,
                "encoding": "utf-8",
            },
            "worker_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "formatter": "detailed",
                "level": "DEBUG",
                "filters": ["request_context"],
                "filename": "logs/worker.log",
                "maxBytes": 10485760,
                "backupCount": 5,
                "encoding": "utf-8",
            },
        },
        "loggers": {
            "webapi": {"level": "INFO", "handlers": ["console", "file"], "propagate": True},
            "worker": {"level": "DEBUG", "handlers": ["console", "worker_file"], "propagate": False},
            "uvicorn": {"level": "INFO", "handlers": ["console", "file"], "propagate": False},
            "fastapi": {"level": "INFO", "handlers": ["console", "file"], "propagate": False},
        },
        "root": {"level": log_level, "handlers": ["console"]},
    }

    logging.config.dictConfig(logging_config)
    logging.getLogger("webapi").info("Logging configured successfully (built-in)")