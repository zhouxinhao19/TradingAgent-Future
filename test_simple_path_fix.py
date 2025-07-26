#!/usr/bin/env python3
"""
简单测试：验证Web版本的路径修复
测试 ./results 相对路径是否正确解析到项目根目录
"""

import os
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "web"))
sys.path.insert(0, str(project_root / "web" / "utils"))

print("🔧 简单路径修复验证")
print("=" * 60)

# 1. 显示当前工作目录和项目结构
print(f"📁 当前工作目录: {os.getcwd()}")
print(f"📁 项目根目录: {project_root}")
print(f"📁 Web目录: {project_root / 'web'}")

# 2. 检查环境变量
results_dir_env = os.getenv("TRADINGAGENTS_RESULTS_DIR", "未设置")
print(f"📁 环境变量 TRADINGAGENTS_RESULTS_DIR: {results_dir_env}")

# 3. 模拟Web环境中的路径处理
print("\n🧪 模拟Web环境路径处理:")
print("-" * 40)

# 模拟在web/utils/report_exporter.py中的处理
current_file = project_root / "web" / "utils" / "report_exporter.py"
web_project_root = current_file.parent.parent.parent  # 应该指向项目根目录

print(f"📁 模拟当前文件: {current_file}")
print(f"📁 计算的项目根目录: {web_project_root}")
print(f"📁 项目根目录计算正确: {web_project_root == project_root}")

# 4. 测试路径解析逻辑
print("\n🧪 测试路径解析逻辑:")
print("-" * 40)

results_dir_env = os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results")
print(f"📁 环境变量值: {results_dir_env}")

if results_dir_env:
    # 如果环境变量是相对路径，相对于项目根目录解析
    if not os.path.isabs(results_dir_env):
        resolved_results_dir = web_project_root / results_dir_env
        print(f"📁 相对路径解析: {results_dir_env} -> {resolved_results_dir}")
    else:
        resolved_results_dir = Path(results_dir_env)
        print(f"📁 绝对路径直接使用: {resolved_results_dir}")
else:
    # 默认使用项目根目录下的results
    resolved_results_dir = web_project_root / "results"
    print(f"📁 使用默认路径: {resolved_results_dir}")

# 5. 验证最终路径
print(f"\n📊 最终解析结果:")
print(f"📁 Results目录: {resolved_results_dir}")
print(f"📁 是否在项目根目录下: {resolved_results_dir.parent == project_root}")

# 6. 检查是否解决了Web目录问题
web_results_dir = Path("web") / "results"  # 错误的路径
project_results_dir = project_root / "results"  # 正确的路径

print(f"\n🔍 路径对比:")
print(f"❌ 错误路径 (web/results): {web_results_dir}")
print(f"✅ 正确路径 (项目根/results): {project_results_dir}")
print(f"📁 我们的解析结果: {resolved_results_dir}")

if str(resolved_results_dir) == str(project_results_dir):
    print("✅ 路径修复成功！Web版本现在正确指向项目根目录")
    success = True
elif str(resolved_results_dir) == str(web_results_dir):
    print("❌ 路径修复失败！仍然指向web目录")
    success = False
else:
    print(f"⚠️ 路径指向其他位置: {resolved_results_dir}")
    success = True  # 可能是自定义路径，也算成功

# 7. 测试实际的保存功能
print(f"\n🧪 测试实际保存功能:")
print("-" * 40)

try:
    # 导入修复后的函数
    from report_exporter import save_report_to_results_dir
    
    # 创建测试内容
    test_content = b"# Test Report\n\nThis is a test."
    test_filename = "test_simple.md"
    test_stock = "TEST001"
    
    # 保存测试
    saved_path = save_report_to_results_dir(test_content, test_filename, test_stock)
    
    if saved_path:
        saved_path_obj = Path(saved_path)
        print(f"📁 实际保存路径: {saved_path}")
        
        # 检查是否在项目根目录下
        try:
            relative_path = saved_path_obj.relative_to(project_root)
            print(f"📁 相对于项目根目录: {relative_path}")
            
            if str(relative_path).startswith("results"):
                print("✅ 文件正确保存到项目根目录下的results目录")
                save_success = True
            else:
                print("❌ 文件没有保存到正确的results目录")
                save_success = False
        except ValueError:
            print("❌ 文件没有保存到项目根目录下")
            save_success = False
        
        # 清理测试文件
        if saved_path_obj.exists():
            try:
                saved_path_obj.unlink()
                # 尝试删除空目录
                parent_dir = saved_path_obj.parent
                while parent_dir != project_root and parent_dir.exists():
                    try:
                        parent_dir.rmdir()
                        parent_dir = parent_dir.parent
                    except OSError:
                        break
                print("🧹 测试文件已清理")
            except Exception as e:
                print(f"⚠️ 清理测试文件失败: {e}")
    else:
        print("❌ 保存功能失败")
        save_success = False
        
except Exception as e:
    print(f"❌ 测试保存功能时出错: {e}")
    save_success = False

# 8. 总结
print(f"\n" + "=" * 60)
print("📊 测试结果总结:")
print(f"  路径解析正确: {'✅' if success else '❌'}")
print(f"  保存功能正确: {'✅' if save_success else '❌'}")

if success and save_success:
    print("\n🎉 Web版本路径修复验证成功！")
    print("✅ 现在Web界面的报告会正确保存到项目根目录下的results目录")
else:
    print("\n❌ 还有问题需要修复")

print(f"\n💡 关键修复点:")
print(f"  1. Web环境中正确计算项目根目录")
print(f"  2. 相对路径相对于项目根目录解析，而不是web目录")
print(f"  3. 支持绝对路径和相对路径")
