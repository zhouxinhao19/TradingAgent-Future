#!/usr/bin/env python3
"""
数据库依赖包兼容性检查工具
检查Python版本和依赖包是否兼容
"""

import sys
import subprocess
import importlib.util
from packaging import version


def check_python_version():
    """检查Python版本"""
    print("🐍 检查Python版本...")
    
    current_version = sys.version_info
    required_version = (3, 10)
    
    print(f"  当前Python版本: {current_version.major}.{current_version.minor}.{current_version.micro}")
    print(f"  要求Python版本: {required_version[0]}.{required_version[1]}+")
    
    if current_version >= required_version:
        print("  ✅ Python版本符合要求")
        return True
    else:
        print("  ❌ Python版本过低，请升级到3.10+")
        return False


def check_package_availability(package_name, min_version=None, max_version=None):
    """检查包是否可用及版本"""
    try:
        # 检查包是否已安装
        spec = importlib.util.find_spec(package_name)
        if spec is None:
            return False, "未安装", None
        
        # 获取包版本
        try:
            module = importlib.import_module(package_name)
            pkg_version = getattr(module, '__version__', 'unknown')
        except:
            pkg_version = 'unknown'
        
        # 检查版本要求
        if pkg_version != 'unknown' and min_version:
            try:
                if version.parse(pkg_version) < version.parse(min_version):
                    return False, f"版本过低 ({pkg_version} < {min_version})", pkg_version
                if max_version and version.parse(pkg_version) >= version.parse(max_version):
                    return False, f"版本过高 ({pkg_version} >= {max_version})", pkg_version
            except:
                pass
        
        return True, "已安装", pkg_version
        
    except Exception as e:
        return False, f"检查失败: {e}", None


def check_db_requirements():
    """检查数据库依赖包"""
    print("\n📦 检查数据库依赖包...")
    
    requirements = [
        ("pymongo", "4.3.0", None, "MongoDB驱动"),
        ("motor", "3.1.0", None, "异步MongoDB驱动"),
        ("redis", "4.5.0", None, "Redis驱动"),
        ("hiredis", "2.0.0", None, "Redis性能优化"),
        ("pandas", "1.5.0", None, "数据处理"),
        ("numpy", "1.21.0", None, "数值计算"),
    ]
    
    all_good = True
    installed_packages = []
    missing_packages = []
    
    for pkg_name, min_ver, max_ver, description in requirements:
        available, status, current_ver = check_package_availability(pkg_name, min_ver, max_ver)
        
        if available:
            print(f"  ✅ {pkg_name}: {status} ({current_ver}) - {description}")
            installed_packages.append(pkg_name)
        else:
            print(f"  ❌ {pkg_name}: {status} - {description}")
            missing_packages.append((pkg_name, min_ver, max_ver))
            all_good = False
    
    return all_good, installed_packages, missing_packages


def check_pickle_compatibility():
    """检查pickle兼容性"""
    print("\n🥒 检查pickle兼容性...")
    
    try:
        import pickle
        
        # 检查是否支持协议5
        max_protocol = pickle.HIGHEST_PROTOCOL
        print(f"  当前pickle最高协议: {max_protocol}")
        
        if max_protocol >= 5:
            print("  ✅ 支持pickle协议5，无需安装pickle5包")
            
            # 检查是否错误安装了pickle5
            try:
                import pickle5
                print("  ⚠️ 检测到pickle5包，建议卸载：pip uninstall pickle5")
                return True, True  # 兼容但有警告
            except ImportError:
                print("  ✅ 未安装pickle5包，配置正确")
                return True, False
        else:
            print("  ❌ 不支持pickle协议5，请升级Python版本")
            return False, False
            
    except Exception as e:
        print(f"  ❌ pickle检查失败: {e}")
        return False, False


def generate_install_commands(missing_packages):
    """生成安装命令"""
    if not missing_packages:
        return []
    
    print("\n📋 建议的安装命令:")
    commands = []
    
    # 生成pip install命令
    pip_packages = []
    for pkg_name, min_ver, max_ver in missing_packages:
        if max_ver:
            pip_packages.append(f"{pkg_name}>={min_ver},<{max_ver}")
        else:
            pip_packages.append(f"{pkg_name}>={min_ver}")
    
    if pip_packages:
        cmd = f"pip install {' '.join(pip_packages)}"
        commands.append(cmd)
        print(f"  {cmd}")
    
    # 或者使用requirements文件
    print(f"  或者使用: pip install -r requirements_db.txt")
    commands.append("pip install -r requirements_db.txt")
    
    return commands


def main():
    """主函数"""
    print("🔧 TradingAgents 数据库依赖包兼容性检查")
    print("=" * 60)
    
    # 检查Python版本
    python_ok = check_python_version()
    
    # 检查数据库依赖包
    packages_ok, installed, missing = check_db_requirements()
    
    # 检查pickle兼容性
    pickle_ok, has_pickle5 = check_pickle_compatibility()
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 检查结果总结:")
    
    if python_ok:
        print("✅ Python版本: 符合要求")
    else:
        print("❌ Python版本: 需要升级")
    
    if packages_ok:
        print("✅ 数据库依赖包: 全部满足")
    else:
        print(f"❌ 数据库依赖包: {len(missing)}个包需要安装/升级")
    
    if pickle_ok:
        if has_pickle5:
            print("⚠️ pickle兼容性: 兼容但建议卸载pickle5")
        else:
            print("✅ pickle兼容性: 完全兼容")
    else:
        print("❌ pickle兼容性: 不兼容")
    
    # 提供解决方案
    if not python_ok:
        print("\n🔧 Python版本解决方案:")
        print("  1. 下载并安装Python 3.10+: https://www.python.org/downloads/")
        print("  2. 或使用conda: conda install python=3.10")
        print("  3. 或使用pyenv管理多版本Python")
    
    if not packages_ok:
        print("\n🔧 依赖包解决方案:")
        generate_install_commands(missing)
    
    if has_pickle5:
        print("\n🔧 pickle5卸载:")
        print("  pip uninstall pickle5")
        print("  (Python 3.10+已内置pickle协议5支持)")
    
    # 最终状态
    all_ok = python_ok and packages_ok and pickle_ok and not has_pickle5
    
    if all_ok:
        print("\n🎉 所有检查通过！数据库功能可以正常使用。")
        return 0
    else:
        print("\n⚠️ 存在兼容性问题，请按照上述建议进行修复。")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n⏹️ 检查被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 检查过程中出现错误: {e}")
        sys.exit(1)
