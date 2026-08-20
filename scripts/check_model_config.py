#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""检查数据库中的模型配置"""

from pymongo import MongoClient

# 连接数据库（带认证）
client = MongoClient('mongodb://admin:CHANGE_ME_LOCAL_PASSWORD@localhost:27017/?authSource=admin')
db = client['tradingagents']

print("=" * 80)
print("📊 检查数据库中的模型配置")
print("=" * 80)

# 1. 检查 system_configs 集合
print("\n1️⃣ 检查 system_configs 集合:")
system_config = db.system_configs.find_one({'is_active': True}, sort=[('version', -1)])
if system_config:
    print(f"✅ 找到激活的系统配置 (版本: {system_config.get('version')})")
    system_settings = system_config.get('system_settings', {})
    print(f"\n📋 系统设置:")
    print(f"  - default_provider: {system_settings.get('default_provider')}")
    print(f"  - default_model: {system_settings.get('default_model')}")
    print(f"  - quick_analysis_model: {system_settings.get('quick_analysis_model')}")
    print(f"  - deep_analysis_model: {system_settings.get('deep_analysis_model')}")
else:
    print("❌ 未找到激活的系统配置")

# 2. 检查 configurations 集合
print("\n2️⃣ 检查 configurations 集合:")
llm_config = db.configurations.find_one({'config_type': 'llm', 'config_name': 'default_models'})
if llm_config:
    print(f"✅ 找到 LLM 配置")
    config_value = llm_config.get('config_value', {})
    print(f"\n📋 LLM 配置:")
    print(f"  - default_provider: {config_value.get('default_provider')}")
    print(f"  - models: {config_value.get('models')}")
else:
    print("❌ 未找到 LLM 配置")

# 3. 检查所有 system_configs 文档
print("\n3️⃣ 所有 system_configs 文档:")
all_configs = list(db.system_configs.find().sort('version', -1))
print(f"总共 {len(all_configs)} 个配置文档:")
for i, config in enumerate(all_configs[:3]):  # 只显示最新的3个
    print(f"\n  配置 {i+1}:")
    print(f"    - 版本: {config.get('version')}")
    print(f"    - 激活: {config.get('is_active')}")
    print(f"    - 更新时间: {config.get('updated_at')}")
    system_settings = config.get('system_settings', {})
    print(f"    - quick_analysis_model: {system_settings.get('quick_analysis_model')}")
    print(f"    - deep_analysis_model: {system_settings.get('deep_analysis_model')}")

print("\n" + "=" * 80)

