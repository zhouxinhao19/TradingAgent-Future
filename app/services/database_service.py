"""
数据库管理服务
"""

import json
import os
import csv
import gzip
import shutil
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from bson import ObjectId
import motor.motor_asyncio
import redis.asyncio as redis
from pymongo.errors import ServerSelectionTimeoutError

from app.core.database import get_mongo_db, get_redis_client, db_manager
from app.core.config import settings

class DatabaseService:
    """数据库管理服务"""
    
    def __init__(self):
        self.backup_dir = os.path.join(settings.TRADINGAGENTS_DATA_DIR, "backups")
        self.export_dir = os.path.join(settings.TRADINGAGENTS_DATA_DIR, "exports")
        
        # 确保目录存在
        os.makedirs(self.backup_dir, exist_ok=True)
        os.makedirs(self.export_dir, exist_ok=True)
    
    async def get_database_status(self) -> Dict[str, Any]:
        """获取数据库连接状态"""
        mongodb_status = await self._get_mongodb_status()
        redis_status = await self._get_redis_status()
        
        return {
            "mongodb": mongodb_status,
            "redis": redis_status
        }
    
    async def _get_mongodb_status(self) -> Dict[str, Any]:
        """获取MongoDB状态"""
        try:
            db = get_mongo_db()

            # 测试连接 - 使用数据库对象的command方法
            await db.command('ping')

            # 获取服务器信息
            server_info = await db.command('buildInfo')
            server_status = await db.command('serverStatus')

            return {
                "connected": True,
                "host": settings.MONGODB_HOST,
                "port": settings.MONGODB_PORT,
                "database": settings.MONGODB_DATABASE,
                "version": server_info.get('version', 'Unknown'),
                "uptime": server_status.get('uptime', 0),
                "connections": server_status.get('connections', {}),
                "memory": server_status.get('mem', {}),
                "connected_at": datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
                "host": settings.MONGODB_HOST,
                "port": settings.MONGODB_PORT,
                "database": settings.MONGODB_DATABASE
            }
    
    async def _get_redis_status(self) -> Dict[str, Any]:
        """获取Redis状态"""
        try:
            redis_client = get_redis_client()
            
            # 测试连接
            await redis_client.ping()
            
            # 获取服务器信息
            info = await redis_client.info()
            
            return {
                "connected": True,
                "host": settings.REDIS_HOST,
                "port": settings.REDIS_PORT,
                "database": settings.REDIS_DB,
                "version": info.get('redis_version', 'Unknown'),
                "uptime": info.get('uptime_in_seconds', 0),
                "memory_used": info.get('used_memory', 0),
                "memory_peak": info.get('used_memory_peak', 0),
                "connected_clients": info.get('connected_clients', 0),
                "total_commands": info.get('total_commands_processed', 0)
            }
        except Exception as e:
            return {
                "connected": False,
                "error": str(e),
                "host": settings.REDIS_HOST,
                "port": settings.REDIS_PORT,
                "database": settings.REDIS_DB
            }
    
    async def get_database_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        try:
            db = get_mongo_db()
            
            # 获取所有集合
            collection_names = await db.list_collection_names()
            
            collections_info = []
            total_documents = 0
            total_size = 0
            
            for collection_name in collection_names:
                collection = db[collection_name]
                
                # 获取集合统计
                stats = await db.command("collStats", collection_name)
                doc_count = await collection.count_documents({})
                
                collection_info = {
                    "name": collection_name,
                    "documents": doc_count,
                    "size": stats.get('size', 0),
                    "storage_size": stats.get('storageSize', 0),
                    "indexes": stats.get('nindexes', 0),
                    "index_size": stats.get('totalIndexSize', 0)
                }
                
                collections_info.append(collection_info)
                total_documents += doc_count
                total_size += stats.get('storageSize', 0)
            
            return {
                "total_collections": len(collection_names),
                "total_documents": total_documents,
                "total_size": total_size,
                "collections": collections_info
            }
        except Exception as e:
            raise Exception(f"获取数据库统计失败: {str(e)}")
    
    async def test_connections(self) -> Dict[str, Any]:
        """测试数据库连接"""
        mongodb_test = await self._test_mongodb_connection()
        redis_test = await self._test_redis_connection()
        
        return {
            "mongodb": mongodb_test,
            "redis": redis_test,
            "overall": mongodb_test["success"] and redis_test["success"]
        }
    
    async def _test_mongodb_connection(self) -> Dict[str, Any]:
        """测试MongoDB连接"""
        try:
            db = get_mongo_db()
            start_time = datetime.utcnow()

            # 执行ping命令
            await db.command('ping')

            end_time = datetime.utcnow()
            response_time = (end_time - start_time).total_seconds() * 1000

            return {
                "success": True,
                "response_time_ms": round(response_time, 2),
                "message": "MongoDB连接正常"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "MongoDB连接失败"
            }
    
    async def _test_redis_connection(self) -> Dict[str, Any]:
        """测试Redis连接"""
        try:
            redis_client = get_redis_client()
            start_time = datetime.utcnow()
            
            # 执行ping命令
            await redis_client.ping()
            
            end_time = datetime.utcnow()
            response_time = (end_time - start_time).total_seconds() * 1000
            
            return {
                "success": True,
                "response_time_ms": round(response_time, 2),
                "message": "Redis连接正常"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Redis连接失败"
            }
    
    async def create_backup(self, name: str, collections: List[str] = None, user_id: str = None) -> Dict[str, Any]:
        """创建数据库备份"""
        try:
            db = get_mongo_db()
            backup_id = str(ObjectId())
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"backup_{name}_{timestamp}.json.gz"
            backup_path = os.path.join(self.backup_dir, backup_filename)
            
            # 如果没有指定集合，备份所有集合
            if not collections:
                collections = await db.list_collection_names()
            
            backup_data = {
                "backup_id": backup_id,
                "name": name,
                "created_at": datetime.utcnow().isoformat(),
                "created_by": user_id,
                "collections": collections,
                "data": {}
            }
            
            # 备份每个集合的数据
            for collection_name in collections:
                collection = db[collection_name]
                documents = []

                async for doc in collection.find():
                    # 转换特殊类型为可序列化格式
                    doc = self._serialize_document(doc)
                    documents.append(doc)

                backup_data["data"][collection_name] = documents
            
            # 压缩并保存备份文件
            with gzip.open(backup_path, 'wt', encoding='utf-8') as f:
                json.dump(backup_data, f, ensure_ascii=False, indent=2)
            
            # 获取文件大小
            file_size = os.path.getsize(backup_path)
            
            # 保存备份元数据到数据库
            backup_meta = {
                "_id": ObjectId(backup_id),
                "name": name,
                "filename": backup_filename,
                "file_path": backup_path,
                "size": file_size,
                "collections": collections,
                "created_at": datetime.utcnow(),
                "created_by": user_id
            }
            
            await db.database_backups.insert_one(backup_meta)
            
            return {
                "id": backup_id,
                "name": name,
                "filename": backup_filename,
                "file_path": backup_path,
                "size": file_size,
                "collections": collections,
                "created_at": backup_meta["created_at"].isoformat()
            }
            
        except Exception as e:
            raise Exception(f"创建备份失败: {str(e)}")
    
    async def list_backups(self) -> List[Dict[str, Any]]:
        """获取备份列表"""
        try:
            db = get_mongo_db()
            backups = []
            
            async for backup in db.database_backups.find().sort("created_at", -1):
                backup_info = {
                    "id": str(backup["_id"]),
                    "name": backup["name"],
                    "filename": backup["filename"],
                    "size": backup["size"],
                    "collections": backup["collections"],
                    "created_at": backup["created_at"].isoformat(),
                    "created_by": backup.get("created_by")
                }
                backups.append(backup_info)
            
            return backups
            
        except Exception as e:
            raise Exception(f"获取备份列表失败: {str(e)}")
    
    async def delete_backup(self, backup_id: str) -> None:
        """删除备份"""
        try:
            db = get_mongo_db()
            
            # 查找备份记录
            backup = await db.database_backups.find_one({"_id": ObjectId(backup_id)})
            if not backup:
                raise Exception("备份不存在")
            
            # 删除备份文件
            if os.path.exists(backup["file_path"]):
                os.remove(backup["file_path"])
            
            # 删除数据库记录
            await db.database_backups.delete_one({"_id": ObjectId(backup_id)})
            
        except Exception as e:
            raise Exception(f"删除备份失败: {str(e)}")
    
    async def cleanup_old_data(self, days: int) -> Dict[str, Any]:
        """清理旧数据"""
        try:
            db = get_mongo_db()
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            deleted_count = 0
            cleaned_collections = []
            
            # 清理分析任务
            result = await db.analysis_tasks.delete_many({
                "created_at": {"$lt": cutoff_date},
                "status": {"$in": ["completed", "failed"]}
            })
            if result.deleted_count > 0:
                deleted_count += result.deleted_count
                cleaned_collections.append(f"analysis_tasks: {result.deleted_count}")
            
            # 清理用户会话
            result = await db.user_sessions.delete_many({
                "created_at": {"$lt": cutoff_date}
            })
            if result.deleted_count > 0:
                deleted_count += result.deleted_count
                cleaned_collections.append(f"user_sessions: {result.deleted_count}")
            
            # 清理登录尝试记录
            result = await db.login_attempts.delete_many({
                "timestamp": {"$lt": cutoff_date}
            })
            if result.deleted_count > 0:
                deleted_count += result.deleted_count
                cleaned_collections.append(f"login_attempts: {result.deleted_count}")
            
            return {
                "deleted_count": deleted_count,
                "cleaned_collections": cleaned_collections,
                "cutoff_date": cutoff_date.isoformat()
            }
            
        except Exception as e:
            raise Exception(f"清理数据失败: {str(e)}")

    async def cleanup_analysis_results(self, days: int) -> Dict[str, Any]:
        """清理过期分析结果"""
        try:
            db = get_mongo_db()
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            deleted_count = 0
            cleaned_collections = []

            # 清理分析任务
            result = await db.analysis_tasks.delete_many({
                "created_at": {"$lt": cutoff_date},
                "status": {"$in": ["completed", "failed"]}
            })
            if result.deleted_count > 0:
                deleted_count += result.deleted_count
                cleaned_collections.append(f"analysis_tasks: {result.deleted_count}")

            # 清理分析结果
            result = await db.analysis_results.delete_many({
                "created_at": {"$lt": cutoff_date}
            })
            if result.deleted_count > 0:
                deleted_count += result.deleted_count
                cleaned_collections.append(f"analysis_results: {result.deleted_count}")

            return {
                "deleted_count": deleted_count,
                "cleaned_collections": cleaned_collections,
                "cutoff_date": cutoff_date.isoformat()
            }

        except Exception as e:
            raise Exception(f"清理分析结果失败: {str(e)}")

    async def cleanup_operation_logs(self, days: int) -> Dict[str, Any]:
        """清理操作日志"""
        try:
            db = get_mongo_db()
            cutoff_date = datetime.utcnow() - timedelta(days=days)

            deleted_count = 0
            cleaned_collections = []

            # 清理用户会话
            result = await db.user_sessions.delete_many({
                "created_at": {"$lt": cutoff_date}
            })
            if result.deleted_count > 0:
                deleted_count += result.deleted_count
                cleaned_collections.append(f"user_sessions: {result.deleted_count}")

            # 清理登录尝试记录
            result = await db.login_attempts.delete_many({
                "timestamp": {"$lt": cutoff_date}
            })
            if result.deleted_count > 0:
                deleted_count += result.deleted_count
                cleaned_collections.append(f"login_attempts: {result.deleted_count}")

            # 清理操作日志
            result = await db.operation_logs.delete_many({
                "timestamp": {"$lt": cutoff_date}
            })
            if result.deleted_count > 0:
                deleted_count += result.deleted_count
                cleaned_collections.append(f"operation_logs: {result.deleted_count}")

            return {
                "deleted_count": deleted_count,
                "cleaned_collections": cleaned_collections,
                "cutoff_date": cutoff_date.isoformat()
            }

        except Exception as e:
            raise Exception(f"清理操作日志失败: {str(e)}")

    async def import_data(self, content: bytes, collection: str, format: str = "json",
                         overwrite: bool = False, filename: str = None) -> Dict[str, Any]:
        """导入数据"""
        try:
            db = get_mongo_db()
            collection_obj = db[collection]

            # 解析数据
            if format.lower() == "json":
                data = json.loads(content.decode('utf-8'))
            else:
                raise Exception(f"不支持的格式: {format}")

            # 确保数据是列表格式
            if not isinstance(data, list):
                data = [data]

            # 如果需要覆盖，先清空集合
            if overwrite:
                await collection_obj.delete_many({})

            # 处理ObjectId
            for doc in data:
                if '_id' in doc and isinstance(doc['_id'], str):
                    try:
                        doc['_id'] = ObjectId(doc['_id'])
                    except:
                        # 如果不是有效的ObjectId，删除_id让MongoDB自动生成
                        del doc['_id']

            # 插入数据
            if data:
                result = await collection_obj.insert_many(data)
                inserted_count = len(result.inserted_ids)
            else:
                inserted_count = 0

            return {
                "collection": collection,
                "inserted_count": inserted_count,
                "filename": filename,
                "format": format,
                "overwrite": overwrite
            }

        except Exception as e:
            raise Exception(f"导入数据失败: {str(e)}")

    async def export_data(self, collections: List[str] = None, format: str = "json") -> str:
        """导出数据"""
        try:
            import pandas as pd

            db = get_mongo_db()
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

            # 如果没有指定集合，导出所有集合
            if not collections:
                collections = await db.list_collection_names()
                # 排除系统集合
                collections = [c for c in collections if not c.startswith('system.')]

            # 收集所有数据
            all_data = {}
            for collection_name in collections:
                collection = db[collection_name]
                documents = []

                async for doc in collection.find():
                    # 转换特殊类型为可序列化格式
                    doc = self._serialize_document(doc)
                    documents.append(doc)

                all_data[collection_name] = documents

            if format.lower() == "json":
                filename = f"export_{timestamp}.json"
                file_path = os.path.join(self.export_dir, filename)

                export_data = {
                    "export_info": {
                        "created_at": datetime.utcnow().isoformat(),
                        "collections": collections,
                        "format": format
                    },
                    "data": all_data
                }

                # 保存文件
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, ensure_ascii=False, indent=2)

                return file_path

            elif format.lower() == "csv":
                filename = f"export_{timestamp}.csv"
                file_path = os.path.join(self.export_dir, filename)

                # 将所有集合的数据合并到一个DataFrame中
                all_rows = []
                for collection_name, documents in all_data.items():
                    for doc in documents:
                        # 添加集合名称列
                        doc['_collection'] = collection_name
                        all_rows.append(doc)

                if all_rows:
                    df = pd.DataFrame(all_rows)
                    df.to_csv(file_path, index=False, encoding='utf-8-sig')
                else:
                    # 创建空的CSV文件
                    pd.DataFrame().to_csv(file_path, index=False, encoding='utf-8-sig')

                return file_path

            elif format.lower() in ["xlsx", "excel"]:
                filename = f"export_{timestamp}.xlsx"
                file_path = os.path.join(self.export_dir, filename)

                # 创建Excel文件，每个集合一个工作表
                with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                    for collection_name, documents in all_data.items():
                        if documents:
                            df = pd.DataFrame(documents)
                        else:
                            df = pd.DataFrame()

                        # 工作表名称不能超过31个字符
                        sheet_name = collection_name[:31] if len(collection_name) > 31 else collection_name
                        df.to_excel(writer, sheet_name=sheet_name, index=False)

                return file_path
            else:
                raise Exception(f"不支持的导出格式: {format}")

        except Exception as e:
            raise Exception(f"导出数据失败: {str(e)}")

    def _serialize_document(self, doc: dict) -> dict:
        """序列化文档，处理特殊类型"""
        from bson import ObjectId
        from datetime import datetime

        serialized = {}
        for key, value in doc.items():
            if isinstance(value, ObjectId):
                # 转换ObjectId为字符串
                serialized[key] = str(value)
            elif isinstance(value, datetime):
                # 转换datetime为ISO格式字符串
                serialized[key] = value.isoformat()
            elif isinstance(value, dict):
                # 递归处理嵌套字典
                serialized[key] = self._serialize_document(value)
            elif isinstance(value, list):
                # 处理列表中的特殊类型
                serialized_list = []
                for item in value:
                    if isinstance(item, dict):
                        serialized_list.append(self._serialize_document(item))
                    elif isinstance(item, ObjectId):
                        serialized_list.append(str(item))
                    elif isinstance(item, datetime):
                        serialized_list.append(item.isoformat())
                    else:
                        serialized_list.append(item)
                serialized[key] = serialized_list
            else:
                # 其他类型直接保留
                serialized[key] = value

        return serialized
