#!/usr/bin/env python3
"""
通达信API数据获取工具
支持A股、港股实时数据和历史数据
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

try:
    # 通达信Python接口
    import pytdx
    from pytdx.hq import TdxHq_API
    from pytdx.exhq import TdxExHq_API
    TDX_AVAILABLE = True
except ImportError:
    TDX_AVAILABLE = False
    print("⚠️ pytdx库未安装，无法使用通达信API")
    print("💡 安装命令: pip install pytdx")


class TongDaXinDataProvider:
    """通达信数据提供器"""
    
    def __init__(self):
        self.api = None
        self.exapi = None  # 扩展行情API
        self.connected = False
        
        if not TDX_AVAILABLE:
            raise ImportError("pytdx库未安装，请运行: pip install pytdx")
    
    def connect(self):
        """连接通达信服务器"""
        try:
            # 尝试从配置文件加载可用服务器
            working_servers = self._load_working_servers()

            # 如果没有配置文件，使用默认服务器列表
            if not working_servers:
                working_servers = [
                    {'ip': '115.238.56.198', 'port': 7709},
                    {'ip': '115.238.90.165', 'port': 7709},
                    {'ip': '180.153.18.170', 'port': 7709},
                    {'ip': '119.147.212.81', 'port': 7709},  # 备用
                ]

            # 尝试连接可用服务器
            self.api = TdxHq_API()
            for server in working_servers:
                try:
                    result = self.api.connect(server['ip'], server['port'])
                    if result:
                        print(f"✅ 通达信API连接成功: {server['ip']}:{server['port']}")
                        self.connected = True
                        return True
                except Exception as e:
                    print(f"⚠️ 服务器 {server['ip']}:{server['port']} 连接失败: {e}")
                    continue

            print("❌ 所有通达信服务器连接失败")
            self.connected = False
            return False

        except Exception as e:
            print(f"❌ 通达信API连接失败: {e}")
            self.connected = False
            return False

    def _load_working_servers(self):
        """加载可用服务器配置"""
        try:
            import json
            import os

            config_file = 'tdx_servers_config.json'
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    return config.get('working_servers', [])
        except Exception:
            pass
        return []
    
    def disconnect(self):
        """断开连接"""
        try:
            if self.api:
                self.api.disconnect()
            if self.exapi:
                self.exapi.disconnect()
            self.connected = False
            print("✅ 通达信API连接已断开")
        except:
            pass
    
    def get_stock_realtime_data(self, stock_code: str) -> Dict:
        """
        获取股票实时数据
        Args:
            stock_code: 股票代码，如 '000001' (平安银行)
        Returns:
            Dict: 实时股票数据
        """
        if not self.connected:
            if not self.connect():
                return {}
        
        try:
            # 判断市场
            market = self._get_market_code(stock_code)
            
            # 获取实时数据
            data = self.api.get_security_quotes([(market, stock_code)])
            
            if not data:
                return {}
            
            quote = data[0]
            
            return {
                'code': stock_code,
                'name': quote['name'],
                'price': quote['price'],
                'last_close': quote['last_close'],
                'open': quote['open'],
                'high': quote['high'],
                'low': quote['low'],
                'volume': quote['vol'],
                'amount': quote['amount'],
                'change': quote['price'] - quote['last_close'],
                'change_percent': ((quote['price'] - quote['last_close']) / quote['last_close'] * 100) if quote['last_close'] > 0 else 0,
                'bid_prices': [quote[f'bid{i}'] for i in range(1, 6)],
                'bid_volumes': [quote[f'bid_vol{i}'] for i in range(1, 6)],
                'ask_prices': [quote[f'ask{i}'] for i in range(1, 6)],
                'ask_volumes': [quote[f'ask_vol{i}'] for i in range(1, 6)],
                'update_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
        except Exception as e:
            print(f"获取实时数据失败: {e}")
            return {}
    
    def get_stock_history_data(self, stock_code: str, start_date: str, end_date: str, period: str = 'D') -> pd.DataFrame:
        """
        获取股票历史数据
        Args:
            stock_code: 股票代码
            start_date: 开始日期 'YYYY-MM-DD'
            end_date: 结束日期 'YYYY-MM-DD'
            period: 周期 'D'=日线, 'W'=周线, 'M'=月线
        Returns:
            DataFrame: 历史数据
        """
        if not self.connected:
            if not self.connect():
                return pd.DataFrame()
        
        try:
            market = self._get_market_code(stock_code)
            
            # 计算需要获取的数据量
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            days_diff = (end_dt - start_dt).days
            
            # 根据周期调整数据量
            if period == 'D':
                count = min(days_diff + 10, 800)  # 日线最多800条
            elif period == 'W':
                count = min(days_diff // 7 + 10, 800)
            elif period == 'M':
                count = min(days_diff // 30 + 10, 800)
            else:
                count = 800
            
            # 获取K线数据
            category_map = {'D': 9, 'W': 5, 'M': 6}
            category = category_map.get(period, 9)
            
            data = self.api.get_security_bars(category, market, stock_code, 0, count)
            
            if not data:
                return pd.DataFrame()
            
            # 转换为DataFrame
            df = pd.DataFrame(data)
            
            # 处理数据格式
            df['datetime'] = pd.to_datetime(df['datetime'])
            df = df.set_index('datetime')
            df = df.sort_index()
            
            # 筛选日期范围
            df = df[start_date:end_date]
            
            # 重命名列以匹配Yahoo Finance格式
            df = df.rename(columns={
                'open': 'Open',
                'high': 'High', 
                'low': 'Low',
                'close': 'Close',
                'vol': 'Volume',
                'amount': 'Amount'
            })
            
            # 添加股票代码信息
            df['Symbol'] = stock_code
            
            return df
            
        except Exception as e:
            print(f"获取历史数据失败: {e}")
            return pd.DataFrame()
    
    def get_stock_technical_indicators(self, stock_code: str, period: int = 20) -> Dict:
        """
        计算技术指标
        Args:
            stock_code: 股票代码
            period: 计算周期
        Returns:
            Dict: 技术指标数据
        """
        try:
            # 获取最近的历史数据
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=period*2)).strftime('%Y-%m-%d')
            
            df = self.get_stock_history_data(stock_code, start_date, end_date)
            
            if df.empty:
                return {}
            
            # 计算技术指标
            indicators = {}
            
            # 移动平均线
            indicators['MA5'] = df['Close'].rolling(5).mean().iloc[-1] if len(df) >= 5 else None
            indicators['MA10'] = df['Close'].rolling(10).mean().iloc[-1] if len(df) >= 10 else None
            indicators['MA20'] = df['Close'].rolling(20).mean().iloc[-1] if len(df) >= 20 else None
            
            # RSI
            if len(df) >= 14:
                delta = df['Close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
                rs = gain / loss
                indicators['RSI'] = (100 - (100 / (1 + rs))).iloc[-1]
            
            # MACD
            if len(df) >= 26:
                exp1 = df['Close'].ewm(span=12).mean()
                exp2 = df['Close'].ewm(span=26).mean()
                macd = exp1 - exp2
                signal = macd.ewm(span=9).mean()
                indicators['MACD'] = macd.iloc[-1]
                indicators['MACD_Signal'] = signal.iloc[-1]
                indicators['MACD_Histogram'] = (macd - signal).iloc[-1]
            
            # 布林带
            if len(df) >= 20:
                sma = df['Close'].rolling(20).mean()
                std = df['Close'].rolling(20).std()
                indicators['BB_Upper'] = (sma + 2 * std).iloc[-1]
                indicators['BB_Middle'] = sma.iloc[-1]
                indicators['BB_Lower'] = (sma - 2 * std).iloc[-1]
            
            return indicators
            
        except Exception as e:
            print(f"计算技术指标失败: {e}")
            return {}
    
    def search_stocks(self, keyword: str) -> List[Dict]:
        """
        搜索股票
        Args:
            keyword: 搜索关键词（股票代码或名称）
        Returns:
            List[Dict]: 搜索结果
        """
        if not self.connected:
            if not self.connect():
                return []
        
        try:
            # 通达信没有直接的搜索API，这里提供一个简化的实现
            # 实际使用中可以维护一个股票代码表
            
            # 常见股票代码映射
            stock_mapping = {
                '平安银行': '000001',
                '万科A': '000002', 
                '中国平安': '601318',
                '贵州茅台': '600519',
                '招商银行': '600036',
                '五粮液': '000858',
                '格力电器': '000651',
                '美的集团': '000333',
                '中国石化': '600028',
                '工商银行': '601398'
            }
            
            results = []
            
            # 按关键词搜索
            for name, code in stock_mapping.items():
                if keyword.lower() in name.lower() or keyword in code:
                    # 获取实时数据
                    realtime_data = self.get_stock_realtime_data(code)
                    if realtime_data:
                        results.append({
                            'code': code,
                            'name': name,
                            'price': realtime_data.get('price', 0),
                            'change_percent': realtime_data.get('change_percent', 0)
                        })
            
            return results
            
        except Exception as e:
            print(f"搜索股票失败: {e}")
            return []
    
    def _get_market_code(self, stock_code: str) -> int:
        """
        根据股票代码判断市场
        Args:
            stock_code: 股票代码
        Returns:
            int: 市场代码 (0=深圳, 1=上海)
        """
        if stock_code.startswith(('000', '002', '003', '300')):
            return 0  # 深圳
        elif stock_code.startswith(('600', '601', '603', '605', '688')):
            return 1  # 上海
        else:
            return 0  # 默认深圳
    
    def get_market_overview(self) -> Dict:
        """获取市场概览"""
        if not self.connected:
            if not self.connect():
                return {}
        
        try:
            # 获取主要指数数据
            indices = {
                '上证指数': ('1', '000001'),
                '深证成指': ('0', '399001'),
                '创业板指': ('0', '399006'),
                '科创50': ('1', '000688')
            }
            
            market_data = {}
            
            for name, (market, code) in indices.items():
                try:
                    data = self.api.get_security_quotes([(int(market), code)])
                    if data:
                        quote = data[0]
                        market_data[name] = {
                            'price': quote['price'],
                            'change': quote['price'] - quote['last_close'],
                            'change_percent': ((quote['price'] - quote['last_close']) / quote['last_close'] * 100) if quote['last_close'] > 0 else 0,
                            'volume': quote['vol']
                        }
                except:
                    continue
            
            return market_data
            
        except Exception as e:
            print(f"获取市场概览失败: {e}")
            return {}


# 全局实例
_tdx_provider = None

def get_tdx_provider() -> TongDaXinDataProvider:
    """获取通达信数据提供器实例"""
    global _tdx_provider
    if _tdx_provider is None:
        _tdx_provider = TongDaXinDataProvider()
    return _tdx_provider


def get_china_stock_data(stock_code: str, start_date: str, end_date: str) -> str:
    """
    获取中国股票数据的主要接口函数
    Args:
        stock_code: 股票代码 (如 '000001')
        start_date: 开始日期 'YYYY-MM-DD'
        end_date: 结束日期 'YYYY-MM-DD'
    Returns:
        str: 格式化的股票数据
    """
    try:
        provider = get_tdx_provider()
        
        # 获取历史数据
        df = provider.get_stock_history_data(stock_code, start_date, end_date)
        
        if df.empty:
            return f"未能获取股票 {stock_code} 的数据"
        
        # 获取实时数据
        realtime_data = provider.get_stock_realtime_data(stock_code)
        
        # 获取技术指标
        indicators = provider.get_stock_technical_indicators(stock_code)
        
        # 格式化输出
        result = f"""
# {stock_code} 股票数据分析

## 📊 实时行情
- 股票名称: {realtime_data.get('name', 'N/A')}
- 当前价格: ¥{realtime_data.get('price', 0):.2f}
- 涨跌幅: {realtime_data.get('change_percent', 0):.2f}%
- 成交量: {realtime_data.get('volume', 0):,}手
- 更新时间: {realtime_data.get('update_time', 'N/A')}

## 📈 历史数据概览
- 数据期间: {start_date} 至 {end_date}
- 数据条数: {len(df)}条
- 期间最高: ¥{df['High'].max():.2f}
- 期间最低: ¥{df['Low'].min():.2f}
- 期间涨幅: {((df['Close'].iloc[-1] - df['Close'].iloc[0]) / df['Close'].iloc[0] * 100):.2f}%

## 🔍 技术指标
- MA5: ¥{indicators.get('MA5', 0):.2f}
- MA10: ¥{indicators.get('MA10', 0):.2f}
- MA20: ¥{indicators.get('MA20', 0):.2f}
- RSI: {indicators.get('RSI', 0):.2f}
- MACD: {indicators.get('MACD', 0):.4f}

## 📋 最近5日数据
{df.tail().to_string()}

数据来源: 通达信API (实时数据)
"""
        
        return result
        
    except Exception as e:
        return f"""
中国股票数据获取失败 - {stock_code}
错误信息: {str(e)}

💡 解决建议:
1. 检查pytdx库是否已安装: pip install pytdx
2. 确认股票代码格式正确 (如: 000001, 600519)
3. 检查网络连接是否正常
4. 尝试重新连接通达信服务器

注: 通达信API需要网络连接到通达信服务器
"""


def get_china_market_overview() -> str:
    """获取中国股市概览"""
    try:
        provider = get_tdx_provider()
        market_data = provider.get_market_overview()
        
        if not market_data:
            return "无法获取市场概览数据"
        
        result = "# 中国股市概览\n\n"
        
        for name, data in market_data.items():
            change_symbol = "📈" if data['change'] >= 0 else "📉"
            result += f"## {change_symbol} {name}\n"
            result += f"- 当前点位: {data['price']:.2f}\n"
            result += f"- 涨跌点数: {data['change']:+.2f}\n"
            result += f"- 涨跌幅: {data['change_percent']:+.2f}%\n"
            result += f"- 成交量: {data['volume']:,}\n\n"
        
        result += f"更新时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        result += "数据来源: 通达信API\n"
        
        return result
        
    except Exception as e:
        return f"获取市场概览失败: {str(e)}"
