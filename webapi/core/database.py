import logging
from motor.motor_asyncio import AsyncIOMotorClient
from redis.asyncio import Redis
from .config import settings

mongo_client: AsyncIOMotorClient | None = None
redis_client: Redis | None = None

def get_mongo_client() -> AsyncIOMotorClient:
    assert mongo_client is not None, "Mongo client not initialized"
    return mongo_client

def get_redis_client() -> Redis:
    assert redis_client is not None, "Redis client not initialized"
    return redis_client

async def init_db():
    global mongo_client, redis_client
    logging.info("Initializing database connections...")
    mongo_client = AsyncIOMotorClient(settings.MONGO_URI)
    redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    logging.info("Database connections initialized")

async def close_db():
    global mongo_client, redis_client
    logging.info("Closing database connections...")
    if mongo_client:
        mongo_client.close()
        mongo_client = None
    if redis_client:
        await redis_client.close()
        redis_client = None
    logging.info("Database connections closed")