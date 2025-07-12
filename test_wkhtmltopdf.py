#!/usr/bin/env python3
"""
简单测试wkhtmltopdf安装状态
"""

import subprocess
import sys
import os

def test_wkhtmltopdf():
    """测试wkhtmltopdf是否可用"""
    print("🔍 检查wkhtmltopdf安装状态...")
    
    # 测试1: 检查命令是否存在
    try:
        result = subprocess.run(['wkhtmltopdf', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ wkhtmltopdf已安装")
            print(f"版本信息: {result.stdout.strip()}")
            return True
        else:
            print(f"❌ wkhtmltopdf命令执行失败: {result.stderr}")
            return False
    except FileNotFoundError:
        print("❌ wkhtmltopdf命令未找到")
        return False
    except subprocess.TimeoutExpired:
        print("❌ wkhtmltopdf命令超时")
        return False
    except Exception as e:
        print(f"❌ 检查wkhtmltopdf时出错: {e}")
        return False

def test_chocolatey():
    """测试Chocolatey是否可用"""
    print("\n🔍 检查Chocolatey...")
    try:
        result = subprocess.run(['choco', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ Chocolatey可用")
            print(f"版本: {result.stdout.strip()}")
            return True
        else:
            print("❌ Chocolatey不可用")
            return False
    except FileNotFoundError:
        print("❌ Chocolatey未安装")
        return False
    except Exception as e:
        print(f"❌ 检查Chocolatey时出错: {e}")
        return False

def test_winget():
    """测试winget是否可用"""
    print("\n🔍 检查winget...")
    try:
        result = subprocess.run(['winget', '--version'], 
                              capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print("✅ winget可用")
            print(f"版本: {result.stdout.strip()}")
            return True
        else:
            print("❌ winget不可用")
            return False
    except FileNotFoundError:
        print("❌ winget未安装")
        return False
    except Exception as e:
        print(f"❌ 检查winget时出错: {e}")
        return False

def test_pypandoc():
    """测试pypandoc和pandoc"""
    print("\n🔍 检查pypandoc和pandoc...")
    try:
        import pypandoc
        print("✅ pypandoc已安装")
        
        try:
            version = pypandoc.get_pandoc_version()
            print(f"✅ pandoc可用，版本: {version}")
            return True
        except Exception as e:
            print(f"❌ pandoc不可用: {e}")
            return False
    except ImportError:
        print("❌ pypandoc未安装")
        return False

def suggest_installation():
    """提供安装建议"""
    print("\n💡 安装建议:")
    print("=" * 50)
    
    # 检查可用的包管理器
    choco_available = test_chocolatey()
    winget_available = test_winget()
    
    if choco_available:
        print("\n🎯 推荐方案1: 使用Chocolatey安装")
        print("choco install wkhtmltopdf")
    
    if winget_available:
        print("\n🎯 推荐方案2: 使用winget安装")
        print("winget install wkhtmltopdf.wkhtmltopdf")
    
    if not choco_available and not winget_available:
        print("\n🎯 推荐方案: 手动下载安装")
        print("1. 访问: https://wkhtmltopdf.org/downloads.html")
        print("2. 下载Windows版本安装包")
        print("3. 运行安装程序")
        print("4. 确保添加到系统PATH")
    
    print("\n🔄 安装后重新运行此脚本验证")

def main():
    """主函数"""
    print("🧪 wkhtmltopdf安装状态测试")
    print("=" * 50)
    
    # 测试各个组件
    wkhtmltopdf_ok = test_wkhtmltopdf()
    pypandoc_ok = test_pypandoc()
    
    print("\n📊 测试结果:")
    print("=" * 30)
    print(f"wkhtmltopdf: {'✅ 可用' if wkhtmltopdf_ok else '❌ 不可用'}")
    print(f"pypandoc:    {'✅ 可用' if pypandoc_ok else '❌ 不可用'}")
    
    if wkhtmltopdf_ok and pypandoc_ok:
        print("\n🎉 PDF导出功能完全可用！")
        
        # 简单测试PDF生成
        print("\n🧪 测试PDF生成...")
        try:
            import pypandoc
            import tempfile
            
            test_html = "<h1>测试</h1><p>这是一个测试文档</p>"
            
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                output_file = tmp.name
            
            pypandoc.convert_text(
                test_html,
                'pdf',
                format='html',
                outputfile=output_file,
                extra_args=['--pdf-engine=wkhtmltopdf']
            )
            
            if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
                print("✅ PDF生成测试成功！")
                os.unlink(output_file)  # 清理测试文件
            else:
                print("❌ PDF生成测试失败")
                
        except Exception as e:
            print(f"❌ PDF生成测试失败: {e}")
    
    elif pypandoc_ok and not wkhtmltopdf_ok:
        print("\n⚠️ 只有Markdown和Word导出可用")
        print("需要安装wkhtmltopdf才能使用PDF导出")
        suggest_installation()
    
    elif not pypandoc_ok:
        print("\n❌ 导出功能不可用")
        print("请先安装: pip install pypandoc markdown")
        if not wkhtmltopdf_ok:
            suggest_installation()
    
    return wkhtmltopdf_ok and pypandoc_ok

if __name__ == "__main__":
    success = main()
    print(f"\n{'='*50}")
    print(f"测试结果: {'通过' if success else '失败'}")
    sys.exit(0 if success else 1)
