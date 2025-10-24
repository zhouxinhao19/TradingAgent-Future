#!/usr/bin/env python3
"""测试新浪接口返回的列名"""

import akshare as ak

print("🔍 测试新浪接口返回的列名...")

# 获取数据
df = ak.stock_zh_a_spot()

print(f"\n✅ 获取到 {len(df)} 条记录")
print(f"\n📋 列名: {list(df.columns)}")

# 查找测试股票
test_codes = ['000001', '600000', '603175']

for code in test_codes:
    stock_data = df[df['代码'] == code]
    if not stock_data.empty:
        print(f"\n✅ 找到 {code}:")
        print(stock_data.iloc[0])
    else:
        print(f"\n❌ 未找到 {code}")

# 显示前3条数据
print(f"\n📊 前3条数据:")
print(df.head(3))

