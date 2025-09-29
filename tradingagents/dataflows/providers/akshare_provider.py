"""
AKShare统一数据提供器
基于AKShare SDK的统一数据同步方案，提供标准化的数据接口
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
import pandas as pd

from .base_provider import BaseStockDataProvider

logger = logging.getLogger(__name__)


class AKShareProvider(BaseStockDataProvider):
    """
    AKShare统一数据提供器
    
    提供标准化的股票数据接口，支持：
    - 股票基础信息获取
    - 历史行情数据
    - 实时行情数据
    - 财务数据
    - 港股数据支持
    """
    
    def __init__(self):
        super().__init__("AKShare")
        self.ak = None
        self.connected = False
        self._initialize_akshare()
    
    def _initialize_akshare(self):
        """初始化AKShare连接"""
        try:
            import akshare as ak
            self.ak = ak
            self.connected = True
            
            # 配置超时和重试
            self._configure_timeout()
            
            logger.info("✅ AKShare连接成功")
        except ImportError as e:
            logger.error(f"❌ AKShare未安装: {e}")
            self.connected = False
        except Exception as e:
            logger.error(f"❌ AKShare初始化失败: {e}")
            self.connected = False
    
    def _configure_timeout(self):
        """配置AKShare的超时设置"""
        try:
            import socket
            socket.setdefaulttimeout(60)  # 60秒超时
            logger.info("🔧 AKShare超时配置完成: 60秒")
        except Exception as e:
            logger.warning(f"⚠️ AKShare超时配置失败: {e}")
    
    async def connect(self) -> bool:
        """连接到AKShare数据源"""
        return await self.test_connection()

    async def test_connection(self) -> bool:
        """测试AKShare连接"""
        if not self.connected:
            return False
        
        try:
            # 测试获取股票列表
            await asyncio.to_thread(self.ak.stock_info_a_code_name)
            logger.info("✅ AKShare连接测试成功")
            return True
        except Exception as e:
            logger.error(f"❌ AKShare连接测试失败: {e}")
            return False
    
    async def get_stock_list(self) -> List[Dict[str, Any]]:
        """
        获取股票列表
        
        Returns:
            股票列表，包含代码和名称
        """
        if not self.connected:
            return []
        
        try:
            logger.info("📋 获取AKShare股票列表...")
            
            # 异步获取股票列表
            stock_df = await asyncio.to_thread(self.ak.stock_info_a_code_name)
            
            if stock_df is None or stock_df.empty:
                logger.warning("⚠️ AKShare股票列表为空")
                return []
            
            # 转换为标准格式
            stock_list = []
            for _, row in stock_df.iterrows():
                stock_list.append({
                    "code": row.get("code", ""),
                    "name": row.get("name", ""),
                    "source": "akshare"
                })
            
            logger.info(f"✅ AKShare股票列表获取成功: {len(stock_list)}只股票")
            return stock_list
            
        except Exception as e:
            logger.error(f"❌ AKShare获取股票列表失败: {e}")
            return []
    
    async def get_stock_basic_info(self, code: str) -> Optional[Dict[str, Any]]:
        """
        获取股票基础信息
        
        Args:
            code: 股票代码
            
        Returns:
            标准化的股票基础信息
        """
        if not self.connected:
            return None
        
        try:
            logger.debug(f"📊 获取{code}基础信息...")
            
            # 获取股票基本信息
            stock_info = await self._get_stock_info_detail(code)
            
            if not stock_info:
                logger.warning(f"⚠️ 未找到{code}的基础信息")
                return None
            
            # 转换为标准化字典
            basic_info = {
                "code": code,
                "name": stock_info.get("name", f"股票{code}"),
                "area": stock_info.get("area", "未知"),
                "industry": stock_info.get("industry", "未知"),
                "market": self._determine_market(code),
                "list_date": stock_info.get("list_date", ""),
                # 扩展字段
                "full_symbol": self._get_full_symbol(code),
                "market_info": self._get_market_info(code),
                "data_source": "akshare",
                "last_sync": datetime.utcnow(),
                "sync_status": "success"
            }
            
            logger.debug(f"✅ {code}基础信息获取成功")
            return basic_info
            
        except Exception as e:
            logger.error(f"❌ 获取{code}基础信息失败: {e}")
            return None
    
    async def _get_stock_info_detail(self, code: str) -> Dict[str, Any]:
        """获取股票详细信息"""
        try:
            # 尝试获取个股信息
            stock_info = await asyncio.to_thread(
                self.ak.stock_individual_info_em, 
                symbol=code
            )
            
            if stock_info is not None and not stock_info.empty:
                # 解析信息
                info = {"code": code}
                
                # 提取股票名称
                name_row = stock_info[stock_info['item'] == '股票简称']
                if not name_row.empty:
                    info['name'] = name_row['value'].iloc[0]
                
                # 提取行业信息
                industry_row = stock_info[stock_info['item'] == '所属行业']
                if not industry_row.empty:
                    info['industry'] = industry_row['value'].iloc[0]
                
                # 提取地区信息（如果有）
                area_row = stock_info[stock_info['item'] == '所属地区']
                if not area_row.empty:
                    info['area'] = area_row['value'].iloc[0]
                
                # 提取上市日期
                list_date_row = stock_info[stock_info['item'] == '上市时间']
                if not list_date_row.empty:
                    info['list_date'] = list_date_row['value'].iloc[0]
                
                return info
            
            # 如果获取不到详细信息，返回基本信息
            return {"code": code, "name": f"股票{code}"}
            
        except Exception as e:
            logger.debug(f"获取{code}详细信息失败: {e}")
            return {"code": code, "name": f"股票{code}"}
    
    def _determine_market(self, code: str) -> str:
        """根据股票代码判断市场"""
        if code.startswith(('60', '68')):
            return "上海证券交易所"
        elif code.startswith(('00', '30')):
            return "深圳证券交易所"
        elif code.startswith('8'):
            return "北京证券交易所"
        else:
            return "未知市场"
    
    def _get_full_symbol(self, code: str) -> str:
        """获取完整股票代码"""
        if code.startswith(('60', '68')):
            return f"{code}.SS"
        elif code.startswith(('00', '30')):
            return f"{code}.SZ"
        elif code.startswith('8'):
            return f"{code}.BJ"
        else:
            return code
    
    def _get_market_info(self, code: str) -> Dict[str, Any]:
        """获取市场信息"""
        if code.startswith(('60', '68')):
            return {
                "market_type": "CN",
                "exchange": "SSE",
                "exchange_name": "上海证券交易所",
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            }
        elif code.startswith(('00', '30')):
            return {
                "market_type": "CN",
                "exchange": "SZSE", 
                "exchange_name": "深圳证券交易所",
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            }
        elif code.startswith('8'):
            return {
                "market_type": "CN",
                "exchange": "BSE",
                "exchange_name": "北京证券交易所", 
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            }
        else:
            return {
                "market_type": "CN",
                "exchange": "UNKNOWN",
                "exchange_name": "未知交易所",
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            }
    
    async def get_stock_quotes(self, code: str) -> Optional[Dict[str, Any]]:
        """
        获取股票实时行情
        
        Args:
            code: 股票代码
            
        Returns:
            标准化的行情数据
        """
        if not self.connected:
            return None
        
        try:
            logger.debug(f"📈 获取{code}实时行情...")
            
            # 获取实时行情数据
            quotes_data = await self._get_realtime_quotes_data(code)
            
            if not quotes_data:
                logger.warning(f"⚠️ 未找到{code}的行情数据")
                return None
            
            # 转换为标准化字典
            quotes = {
                "code": code,
                "name": quotes_data.get("name", f"股票{code}"),
                "price": float(quotes_data.get("price", 0)),
                "change": float(quotes_data.get("change", 0)),
                "change_percent": float(quotes_data.get("change_percent", 0)),
                "volume": int(quotes_data.get("volume", 0)),
                "amount": float(quotes_data.get("amount", 0)),
                "open_price": float(quotes_data.get("open", 0)),
                "high_price": float(quotes_data.get("high", 0)),
                "low_price": float(quotes_data.get("low", 0)),
                "pre_close": float(quotes_data.get("pre_close", 0)),
                # 扩展字段
                "full_symbol": self._get_full_symbol(code),
                "market_info": self._get_market_info(code),
                "data_source": "akshare",
                "last_sync": datetime.utcnow(),
                "sync_status": "success"
            }
            
            logger.debug(f"✅ {code}实时行情获取成功")
            return quotes
            
        except Exception as e:
            logger.error(f"❌ 获取{code}实时行情失败: {e}")
            return None
    
    async def _get_realtime_quotes_data(self, code: str) -> Dict[str, Any]:
        """获取实时行情数据"""
        try:
            # 获取实时行情
            spot_df = await asyncio.to_thread(self.ak.stock_zh_a_spot_em)
            
            if spot_df is None or spot_df.empty:
                return {}
            
            # 查找对应股票
            stock_data = spot_df[spot_df['代码'] == code]
            
            if stock_data.empty:
                return {}
            
            row = stock_data.iloc[0]
            
            # 解析行情数据
            return {
                "name": row.get("名称", f"股票{code}"),
                "price": self._safe_float(row.get("最新价", 0)),
                "change": self._safe_float(row.get("涨跌额", 0)),
                "change_percent": self._safe_float(row.get("涨跌幅", 0)),
                "volume": self._safe_int(row.get("成交量", 0)),
                "amount": self._safe_float(row.get("成交额", 0)),
                "open": self._safe_float(row.get("今开", 0)),
                "high": self._safe_float(row.get("最高", 0)),
                "low": self._safe_float(row.get("最低", 0)),
                "pre_close": self._safe_float(row.get("昨收", 0))
            }
            
        except Exception as e:
            logger.debug(f"获取{code}实时行情数据失败: {e}")
            return {}
    
    def _safe_float(self, value: Any) -> float:
        """安全转换为浮点数"""
        try:
            if pd.isna(value) or value is None:
                return 0.0
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    
    def _safe_int(self, value: Any) -> int:
        """安全转换为整数"""
        try:
            if pd.isna(value) or value is None:
                return 0
            return int(float(value))
        except (ValueError, TypeError):
            return 0
    
    def _safe_str(self, value: Any) -> str:
        """安全转换为字符串"""
        try:
            if pd.isna(value) or value is None:
                return ""
            return str(value)
        except:
            return ""

    async def get_historical_data(
        self,
        code: str,
        start_date: str,
        end_date: str,
        period: str = "daily"
    ) -> Optional[pd.DataFrame]:
        """
        获取历史行情数据

        Args:
            code: 股票代码
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            period: 周期 (daily, weekly, monthly)

        Returns:
            历史行情数据DataFrame
        """
        if not self.connected:
            return None

        try:
            logger.debug(f"📊 获取{code}历史数据: {start_date} 到 {end_date}")

            # 转换周期格式
            period_map = {
                "daily": "daily",
                "weekly": "weekly",
                "monthly": "monthly"
            }
            ak_period = period_map.get(period, "daily")

            # 格式化日期
            start_date_formatted = start_date.replace('-', '')
            end_date_formatted = end_date.replace('-', '')

            # 获取历史数据
            hist_df = await asyncio.to_thread(
                self.ak.stock_zh_a_hist,
                symbol=code,
                period=ak_period,
                start_date=start_date_formatted,
                end_date=end_date_formatted,
                adjust="qfq"  # 前复权
            )

            if hist_df is None or hist_df.empty:
                logger.warning(f"⚠️ {code}历史数据为空")
                return None

            # 标准化列名
            hist_df = self._standardize_historical_columns(hist_df, code)

            logger.debug(f"✅ {code}历史数据获取成功: {len(hist_df)}条记录")
            return hist_df

        except Exception as e:
            logger.error(f"❌ 获取{code}历史数据失败: {e}")
            return None

    def _standardize_historical_columns(self, df: pd.DataFrame, code: str) -> pd.DataFrame:
        """标准化历史数据列名"""
        try:
            # 标准化列名映射
            column_mapping = {
                '日期': 'date',
                '开盘': 'open',
                '收盘': 'close',
                '最高': 'high',
                '最低': 'low',
                '成交量': 'volume',
                '成交额': 'amount',
                '振幅': 'amplitude',
                '涨跌幅': 'change_percent',
                '涨跌额': 'change',
                '换手率': 'turnover'
            }

            # 重命名列
            df = df.rename(columns=column_mapping)

            # 添加标准字段
            df['code'] = code
            df['full_symbol'] = self._get_full_symbol(code)

            # 确保日期格式
            if 'date' in df.columns:
                df['date'] = pd.to_datetime(df['date'])

            # 数据类型转换
            numeric_columns = ['open', 'close', 'high', 'low', 'volume', 'amount']
            for col in numeric_columns:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

            return df

        except Exception as e:
            logger.error(f"标准化{code}历史数据列名失败: {e}")
            return df

    async def get_financial_data(self, code: str) -> Dict[str, Any]:
        """
        获取财务数据

        Args:
            code: 股票代码

        Returns:
            财务数据字典
        """
        if not self.connected:
            return {}

        try:
            logger.debug(f"💰 获取{code}财务数据...")

            financial_data = {}

            # 1. 获取主要财务指标
            try:
                main_indicators = await asyncio.to_thread(
                    self.ak.stock_financial_abstract,
                    symbol=code
                )
                if main_indicators is not None and not main_indicators.empty:
                    financial_data['main_indicators'] = main_indicators
                    logger.debug(f"✅ {code}主要财务指标获取成功")
            except Exception as e:
                logger.debug(f"获取{code}主要财务指标失败: {e}")

            # 2. 获取资产负债表
            try:
                balance_sheet = await asyncio.to_thread(
                    self.ak.stock_balance_sheet_by_report_em,
                    symbol=code
                )
                if balance_sheet is not None and not balance_sheet.empty:
                    financial_data['balance_sheet'] = balance_sheet
                    logger.debug(f"✅ {code}资产负债表获取成功")
            except Exception as e:
                logger.debug(f"获取{code}资产负债表失败: {e}")

            # 3. 获取利润表
            try:
                income_statement = await asyncio.to_thread(
                    self.ak.stock_profit_sheet_by_report_em,
                    symbol=code
                )
                if income_statement is not None and not income_statement.empty:
                    financial_data['income_statement'] = income_statement
                    logger.debug(f"✅ {code}利润表获取成功")
            except Exception as e:
                logger.debug(f"获取{code}利润表失败: {e}")

            # 4. 获取现金流量表
            try:
                cash_flow = await asyncio.to_thread(
                    self.ak.stock_cash_flow_sheet_by_report_em,
                    symbol=code
                )
                if cash_flow is not None and not cash_flow.empty:
                    financial_data['cash_flow'] = cash_flow
                    logger.debug(f"✅ {code}现金流量表获取成功")
            except Exception as e:
                logger.debug(f"获取{code}现金流量表失败: {e}")

            if financial_data:
                logger.debug(f"✅ {code}财务数据获取完成: {len(financial_data)}个数据集")
            else:
                logger.warning(f"⚠️ {code}未获取到任何财务数据")

            return financial_data

        except Exception as e:
            logger.error(f"❌ 获取{code}财务数据失败: {e}")
            return {}

    async def get_market_status(self) -> Dict[str, Any]:
        """
        获取市场状态信息

        Returns:
            市场状态信息
        """
        try:
            # AKShare没有直接的市场状态API，返回基本信息
            now = datetime.now()

            # 简单的交易时间判断
            is_trading_time = (
                now.weekday() < 5 and  # 工作日
                ((9 <= now.hour < 12) or (13 <= now.hour < 15))  # 交易时间
            )

            return {
                "market_status": "open" if is_trading_time else "closed",
                "current_time": now.isoformat(),
                "data_source": "akshare",
                "trading_day": now.weekday() < 5
            }

        except Exception as e:
            logger.error(f"❌ 获取市场状态失败: {e}")
            return {
                "market_status": "unknown",
                "current_time": datetime.now().isoformat(),
                "data_source": "akshare",
                "error": str(e)
            }
