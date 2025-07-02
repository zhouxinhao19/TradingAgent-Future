#!/usr/bin/env python3
"""
数据库管理器
统一管理MongoDB和Redis连接，提供数据存储和缓存功能
"""

import os
import json
import pickle
import gzip
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Union
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    """数据库管理器 - 统一管理MongoDB和Redis"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.mongodb_client = None
        self.mongodb_db = None
        self.redis_client = None
        
        # 初始化数据库连接
        self._init_mongodb()
        self._init_redis()
        
        print("🗄️ 数据库管理器初始化完成")
    
    def _init_mongodb(self):
        """初始化MongoDB连接"""
        if not self.config.get('database', {}).get('mongodb', {}).get('enabled', False):
            print("📊 MongoDB未启用")
            return
        
        try:
            import pymongo
            
            mongo_config = self.config['database']['mongodb']
            
            # 构建连接字符串
            if mongo_config.get('connection_string'):
                connection_string = mongo_config['connection_string']
            else:
                username = mongo_config['username']
                password = mongo_config['password']
                host = mongo_config['host']
                port = mongo_config['port']
                auth_source = mongo_config.get('auth_source', 'admin')
                
                connection_string = f"mongodb://{username}:{password}@{host}:{port}/{auth_source}"
            
            # 创建客户端
            self.mongodb_client = pymongo.MongoClient(
                connection_string,
                **mongo_config.get('options', {})
            )
            
            # 选择数据库
            self.mongodb_db = self.mongodb_client[mongo_config['database']]
            
            # 测试连接
            self.mongodb_client.admin.command('ping')
            print(f"✅ MongoDB连接成功: {mongo_config['host']}:{mongo_config['port']}")
            
        except ImportError:
            print("❌ pymongo未安装，请运行: pip install pymongo")
            self.mongodb_client = None
        except Exception as e:
            print(f"❌ MongoDB连接失败: {e}")
            self.mongodb_client = None
    
    def _init_redis(self):
        """初始化Redis连接"""
        if not self.config.get('database', {}).get('redis', {}).get('enabled', False):
            print("📦 Redis未启用")
            return
        
        try:
            import redis
            
            redis_config = self.config['database']['redis']
            
            # 构建连接参数
            if redis_config.get('connection_string'):
                self.redis_client = redis.from_url(
                    redis_config['connection_string'],
                    **redis_config.get('options', {})
                )
            else:
                self.redis_client = redis.Redis(
                    host=redis_config['host'],
                    port=redis_config['port'],
                    password=redis_config['password'],
                    db=redis_config['db'],
                    **redis_config.get('options', {})
                )
            
            # 测试连接
            self.redis_client.ping()
            print(f"✅ Redis连接成功: {redis_config['host']}:{redis_config['port']}")
            
        except ImportError:
            print("❌ redis未安装，请运行: pip install redis")
            self.redis_client = None
        except Exception as e:
            print(f"❌ Redis连接失败: {e}")
            self.redis_client = None
    
    # MongoDB操作方法
    def save_stock_data(self, symbol: str, data: Dict[str, Any], market_type: str = "us") -> bool:
        """保存股票数据到MongoDB"""
        if not self.mongodb_db:
            return False
        
        try:
            collection = self.mongodb_db.stock_data
            
            document = {
                'symbol': symbol,
                'market_type': market_type,
                'data': data,
                'created_at': datetime.utcnow(),
                'updated_at': datetime.utcnow()
            }
            
            # 使用upsert更新或插入
            result = collection.replace_one(
                {'symbol': symbol, 'market_type': market_type},
                document,
                upsert=True
            )
            
            print(f"💾 股票数据已保存到MongoDB: {symbol} ({market_type})")
            return True
            
        except Exception as e:
            logger.error(f"保存股票数据到MongoDB失败: {e}")
            return False
    
    def get_stock_data(self, symbol: str, market_type: str = "us") -> Optional[Dict[str, Any]]:
        """从MongoDB获取股票数据"""
        if not self.mongodb_db:
            return None
        
        try:
            collection = self.mongodb_db.stock_data
            document = collection.find_one({'symbol': symbol, 'market_type': market_type})
            
            if document:
                print(f"📁 从MongoDB加载股票数据: {symbol} ({market_type})")
                return document['data']
            
            return None
            
        except Exception as e:
            logger.error(f"从MongoDB获取股票数据失败: {e}")
            return None
    
    def save_analysis_result(self, symbol: str, analysis_type: str, result: Dict[str, Any]) -> bool:
        """保存分析结果到MongoDB"""
        if not self.mongodb_db:
            return False
        
        try:
            collection = self.mongodb_db.analysis_results
            
            document = {
                'symbol': symbol,
                'analysis_type': analysis_type,
                'result': result,
                'created_at': datetime.utcnow()
            }
            
            collection.insert_one(document)
            print(f"💾 分析结果已保存到MongoDB: {symbol} - {analysis_type}")
            return True
            
        except Exception as e:
            logger.error(f"保存分析结果到MongoDB失败: {e}")
            return False
    
    def get_analysis_history(self, symbol: str, analysis_type: str = None, limit: int = 10) -> List[Dict[str, Any]]:
        """获取分析历史记录"""
        if not self.mongodb_db:
            return []
        
        try:
            collection = self.mongodb_db.analysis_results
            
            query = {'symbol': symbol}
            if analysis_type:
                query['analysis_type'] = analysis_type
            
            cursor = collection.find(query).sort('created_at', -1).limit(limit)
            results = list(cursor)
            
            print(f"📊 获取分析历史: {symbol} - {len(results)}条记录")
            return results
            
        except Exception as e:
            logger.error(f"获取分析历史失败: {e}")
            return []
    
    # Redis缓存操作方法
    def cache_set(self, key: str, value: Any, ttl: int = None) -> bool:
        """设置Redis缓存"""
        if not self.redis_client:
            return False
        
        try:
            redis_config = self.config.get('database', {}).get('redis', {})
            cache_config = redis_config.get('cache', {})
            
            # 添加键前缀
            prefixed_key = cache_config.get('key_prefix', '') + key
            
            # 序列化数据
            if cache_config.get('serializer') == 'pickle':
                serialized_value = pickle.dumps(value)
            else:
                serialized_value = json.dumps(value, ensure_ascii=False, default=str)
            
            # 压缩数据
            if cache_config.get('compression', False):
                if isinstance(serialized_value, str):
                    serialized_value = gzip.compress(serialized_value.encode('utf-8'))
                else:
                    serialized_value = gzip.compress(serialized_value)
            
            # 设置TTL
            if ttl is None:
                ttl = cache_config.get('default_ttl', 3600)
            
            # 存储到Redis
            self.redis_client.setex(prefixed_key, ttl, serialized_value)
            
            return True
            
        except Exception as e:
            logger.error(f"Redis缓存设置失败: {e}")
            return False
    
    def cache_get(self, key: str) -> Any:
        """获取Redis缓存"""
        if not self.redis_client:
            return None
        
        try:
            redis_config = self.config.get('database', {}).get('redis', {})
            cache_config = redis_config.get('cache', {})
            
            # 添加键前缀
            prefixed_key = cache_config.get('key_prefix', '') + key
            
            # 从Redis获取数据
            cached_data = self.redis_client.get(prefixed_key)
            if not cached_data:
                return None
            
            # 解压缩数据
            if cache_config.get('compression', False):
                try:
                    cached_data = gzip.decompress(cached_data).decode('utf-8')
                except Exception as e:
                    logger.error(f"解压缩失败: {e}")
                    return None
            
            # 反序列化数据
            if cache_config.get('serializer') == 'pickle':
                return pickle.loads(cached_data)
            else:
                if isinstance(cached_data, bytes):
                    cached_data = cached_data.decode('utf-8')
                return json.loads(cached_data)
            
        except Exception as e:
            logger.error(f"Redis缓存获取失败: {e}")
            return None
    
    def cache_delete(self, key: str) -> bool:
        """删除Redis缓存"""
        if not self.redis_client:
            return False
        
        try:
            redis_config = self.config.get('database', {}).get('redis', {})
            cache_config = redis_config.get('cache', {})
            
            # 添加键前缀
            prefixed_key = cache_config.get('key_prefix', '') + key
            
            result = self.redis_client.delete(prefixed_key)
            return result > 0
            
        except Exception as e:
            logger.error(f"Redis缓存删除失败: {e}")
            return False
    
    def cache_clear_pattern(self, pattern: str) -> int:
        """按模式清理Redis缓存"""
        if not self.redis_client:
            return 0
        
        try:
            redis_config = self.config.get('database', {}).get('redis', {})
            cache_config = redis_config.get('cache', {})
            
            # 添加键前缀
            prefixed_pattern = cache_config.get('key_prefix', '') + pattern
            
            keys = self.redis_client.keys(prefixed_pattern)
            if keys:
                deleted = self.redis_client.delete(*keys)
                print(f"🧹 清理Redis缓存: {deleted}个键")
                return deleted
            
            return 0
            
        except Exception as e:
            logger.error(f"Redis缓存清理失败: {e}")
            return 0
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        stats = {
            'mongodb_connected': self.mongodb_client is not None,
            'redis_connected': self.redis_client is not None,
            'mongodb_stats': {},
            'redis_stats': {}
        }
        
        # MongoDB统计
        if self.mongodb_db:
            try:
                stats['mongodb_stats'] = {
                    'stock_data_count': self.mongodb_db.stock_data.count_documents({}),
                    'analysis_results_count': self.mongodb_db.analysis_results.count_documents({}),
                    'database_size': self.mongodb_db.command('dbStats')['dataSize']
                }
            except Exception as e:
                logger.error(f"获取MongoDB统计失败: {e}")
        
        # Redis统计
        if self.redis_client:
            try:
                info = self.redis_client.info()
                stats['redis_stats'] = {
                    'used_memory': info.get('used_memory_human', 'N/A'),
                    'connected_clients': info.get('connected_clients', 0),
                    'total_commands_processed': info.get('total_commands_processed', 0),
                    'keyspace_hits': info.get('keyspace_hits', 0),
                    'keyspace_misses': info.get('keyspace_misses', 0)
                }
            except Exception as e:
                logger.error(f"获取Redis统计失败: {e}")
        
        return stats
    
    def close(self):
        """关闭数据库连接"""
        if self.mongodb_client:
            self.mongodb_client.close()
            print("📊 MongoDB连接已关闭")
        
        if self.redis_client:
            self.redis_client.close()
            print("📦 Redis连接已关闭")


# 全局数据库管理器实例
_database_manager = None

def get_database_manager() -> DatabaseManager:
    """获取全局数据库管理器实例"""
    global _database_manager
    if _database_manager is None:
        from .config import get_config
        config = get_config()
        _database_manager = DatabaseManager(config)
    return _database_manager
