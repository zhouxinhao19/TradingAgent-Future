#!/usr/bin/env python3
"""
直接更新系统设置中的分析模型配置
"""

import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def main():
    """主函数"""
    print("=" * 60)
    print("📊 更新分析模型配置")
    print("=" * 60)
    
    try:
        # 直接连接 MongoDB
        client = AsyncIOMotorClient("mongodb://admin:CHANGE_ME_LOCAL_PASSWORD@localhost:27017/?authSource=admin")
        db = client['tradingagents']
        
        # 获取当前配置
        system_config = await db['system_configs'].find_one({})
        if not system_config:
            print("❌ 未找到 system_configs 文档")
            return
        
        print(f"\n当前配置版本: {system_config.get('version')}")
        
        # 更新系统设置
        system_settings = system_config.get('system_settings', {})
        print(f"\n更新前:")
        print(f"  快速分析模型: {system_settings.get('quick_analysis_model')}")
        print(f"  深度分析模型: {system_settings.get('deep_analysis_model')}")
        
        # 设置新值
        system_settings['quick_analysis_model'] = 'qwen-flash'
        system_settings['deep_analysis_model'] = 'qwen3-max'
        
        # 更新到数据库
        result = await db['system_configs'].update_one(
            {'_id': system_config['_id']},
            {
                '$set': {
                    'system_settings': system_settings,
                    'version': system_config.get('version', 0) + 1
                }
            }
        )
        
        if result.modified_count > 0:
            print(f"\n✅ 更新成功！")
            print(f"  快速分析模型: qwen-flash")
            print(f"  深度分析模型: qwen3-max")
            print(f"  新版本: {system_config.get('version', 0) + 1}")
        else:
            print(f"\n⚠️  没有修改任何文档")
        
        print("\n" + "=" * 60)
        
        client.close()
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())

