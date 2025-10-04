"""
测试 FastAPI BackgroundTasks 的行为
"""
import asyncio
import time
from fastapi import FastAPI, BackgroundTasks
import uvicorn
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI()

# 模拟进度存储
progress_store = {}


async def long_running_task(task_id: str):
    """模拟长时间运行的任务"""
    try:
        logger.info(f"🚀 [BackgroundTask] 开始执行任务: {task_id}")
        
        for i in range(10):
            await asyncio.sleep(1)
            progress = (i + 1) * 10
            progress_store[task_id] = {
                "progress": progress,
                "message": f"正在处理... {progress}%"
            }
            logger.info(f"📊 [BackgroundTask] 任务 {task_id} 进度: {progress}%")
        
        progress_store[task_id] = {
            "progress": 100,
            "message": "完成！"
        }
        logger.info(f"✅ [BackgroundTask] 任务完成: {task_id}")
        
    except Exception as e:
        logger.error(f"❌ [BackgroundTask] 任务失败: {task_id}, 错误: {e}", exc_info=True)
        progress_store[task_id] = {
            "progress": -1,
            "message": f"失败: {str(e)}"
        }


@app.post("/start-task")
async def start_task(background_tasks: BackgroundTasks):
    """启动后台任务"""
    task_id = f"task_{int(time.time())}"
    
    logger.info(f"🎯 收到任务请求: {task_id}")
    
    # 初始化进度
    progress_store[task_id] = {
        "progress": 0,
        "message": "任务已创建"
    }
    
    # 方法1: 直接添加异步函数
    logger.info(f"📝 [方法1] 使用 background_tasks.add_task(long_running_task)")
    background_tasks.add_task(long_running_task, task_id)
    
    logger.info(f"✅ 任务已在后台启动: {task_id}")
    
    return {
        "success": True,
        "task_id": task_id,
        "message": "任务已在后台启动"
    }


@app.post("/start-task-wrapper")
async def start_task_wrapper(background_tasks: BackgroundTasks):
    """启动后台任务 - 使用包装函数"""
    task_id = f"task_{int(time.time())}"
    
    logger.info(f"🎯 收到任务请求: {task_id}")
    
    # 初始化进度
    progress_store[task_id] = {
        "progress": 0,
        "message": "任务已创建"
    }
    
    # 方法2: 使用包装函数
    async def wrapper():
        """包装函数"""
        try:
            logger.info(f"🚀 [Wrapper] 包装函数开始: {task_id}")
            await long_running_task(task_id)
            logger.info(f"✅ [Wrapper] 包装函数完成: {task_id}")
        except Exception as e:
            logger.error(f"❌ [Wrapper] 包装函数失败: {task_id}, 错误: {e}", exc_info=True)
    
    logger.info(f"📝 [方法2] 使用包装函数")
    background_tasks.add_task(wrapper)
    
    logger.info(f"✅ 任务已在后台启动: {task_id}")
    
    return {
        "success": True,
        "task_id": task_id,
        "message": "任务已在后台启动（使用包装函数）"
    }


@app.get("/task-status/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状态"""
    if task_id not in progress_store:
        return {
            "success": False,
            "message": "任务不存在"
        }
    
    status = progress_store[task_id]
    logger.info(f"🔍 查询任务状态: {task_id} - 进度: {status['progress']}%")
    
    return {
        "success": True,
        "task_id": task_id,
        "progress": status["progress"],
        "message": status["message"]
    }


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "FastAPI BackgroundTasks 测试服务",
        "endpoints": {
            "POST /start-task": "启动后台任务（方法1：直接添加）",
            "POST /start-task-wrapper": "启动后台任务（方法2：使用包装函数）",
            "GET /task-status/{task_id}": "查询任务状态"
        }
    }


if __name__ == "__main__":
    logger.info("🚀 启动测试服务器...")
    logger.info("📍 访问 http://localhost:8001 查看 API 文档")
    logger.info("📍 访问 http://localhost:8001/docs 查看 Swagger UI")
    logger.info("")
    logger.info("测试步骤:")
    logger.info("1. 访问 http://localhost:8001/docs")
    logger.info("2. 调用 POST /start-task 或 POST /start-task-wrapper")
    logger.info("3. 复制返回的 task_id")
    logger.info("4. 调用 GET /task-status/{task_id} 查看进度")
    logger.info("5. 观察控制台日志，查看后台任务是否正常执行")
    logger.info("")
    
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")

