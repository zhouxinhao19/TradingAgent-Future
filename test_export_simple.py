#!/usr/bin/env python3
"""
简单测试导出功能
"""

print("🧪 测试导出功能...")

# 测试1: 导入检查
print("\n1. 测试导入...")
try:
    import pypandoc
    print("✅ pypandoc导入成功")
except ImportError as e:
    print(f"❌ pypandoc导入失败: {e}")
    exit(1)

# 测试2: 检查pandoc
print("\n2. 检查pandoc...")
try:
    version = pypandoc.get_pandoc_version()
    print(f"✅ pandoc可用，版本: {version}")
    pandoc_available = True
except Exception as e:
    print(f"⚠️ pandoc不可用: {e}")
    pandoc_available = False

# 测试3: 尝试下载pandoc
if not pandoc_available:
    print("\n3. 尝试下载pandoc...")
    try:
        pypandoc.download_pandoc()
        version = pypandoc.get_pandoc_version()
        print(f"✅ pandoc下载成功，版本: {version}")
        pandoc_available = True
    except Exception as e:
        print(f"❌ pandoc下载失败: {e}")

# 测试4: 简单转换
print("\n4. 测试转换功能...")
test_md = "# 测试\n\n这是一个**测试**文档。"

try:
    html = pypandoc.convert_text(test_md, 'html', format='markdown')
    print("✅ Markdown → HTML 转换成功")
    print(f"   输出: {html[:50]}...")
except Exception as e:
    print(f"❌ 转换失败: {e}")

# 测试5: 测试导出器
print("\n5. 测试报告导出器...")
try:
    from web.utils.report_exporter import ReportExporter
    exporter = ReportExporter()
    print(f"✅ 导出器创建成功")
    print(f"   export_available: {exporter.export_available}")
    print(f"   pandoc_available: {exporter.pandoc_available}")
except Exception as e:
    print(f"❌ 导出器测试失败: {e}")

print("\n🎉 测试完成！")
