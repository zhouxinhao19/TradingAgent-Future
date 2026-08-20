#!/usr/bin/env python3
"""
检查数据库中的 provider 值
"""

import os
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

async def main():
    """主函数"""
    print("=" * 60)
    print("📊 检查数据库中的 provider 值")
    print("=" * 60)

    try:
        # 直接连接 MongoDB
        client = AsyncIOMotorClient("mongodb://admin:CHANGE_ME_LOCAL_PASSWORD@localhost:27017/?authSource=admin")
        db = client['tradingagents']

        # 列出所有集合
        collections = await db.list_collection_names()
        print(f"\n📋 数据库中的所有集合: {collections}\n")

        # 检查 llm_configs 集合
        configs = await db['llm_configs'].find({}, {'provider': 1, 'model_name': 1, 'enabled': 1, '_id': 0}).to_list(100)

        print(f"\n📊 llm_configs 集合: 找到 {len(configs)} 个配置")
        if configs:
            for config in configs:
                status = "✅" if config.get('enabled') else "❌"
                print(f"  {status} provider: {config.get('provider')}, model: {config.get('model_name')}")

        # 检查 system_configs 集合
        print(f"\n📊 system_configs 集合:")
        # 查询最新的激活配置
        system_config = await db['system_configs'].find_one(
            {"is_active": True},
            sort=[("version", -1)]
        )
        if system_config:
            llm_configs = system_config.get('llm_configs', [])
            print(f"  找到 {len(llm_configs)} 个 LLM 配置")
            for config in llm_configs[:10]:  # 显示前10个
                status = "✅" if config.get('enabled') else "❌"
                print(f"  {status} provider: {config.get('provider')}, model: {config.get('model_name')}")

            # 检查系统设置
            system_settings = system_config.get('system_settings', {})
            print(f"\n  系统设置 (共 {len(system_settings)} 项):")

            # 打印所有设置
            import json
            print(json.dumps(system_settings, indent=2, ensure_ascii=False))
        else:
            print("  ❌ 未找到 system_config 文档")

        print("\n" + "=" * 60)

        client.close()

    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

