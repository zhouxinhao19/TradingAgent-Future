"""
统一的Tushare数据提供器
合并app层和tradingagents层的所有优势功能
"""
from typing import Optional, Dict, Any, List, Union
from datetime import datetime, date, timedelta
import pandas as pd
import asyncio
import logging

from .base_provider import BaseStockDataProvider
from ..providers_config import get_provider_config

# 尝试导入tushare
try:
    import tushare as ts
    TUSHARE_AVAILABLE = True
except ImportError:
    TUSHARE_AVAILABLE = False
    ts = None

logger = logging.getLogger(__name__)


class TushareProvider(BaseStockDataProvider):
    """
    统一的Tushare数据提供器
    合并app层和tradingagents层的所有优势功能
    """
    
    def __init__(self):
        super().__init__("Tushare")
        self.api = None
        self.config = get_provider_config("tushare")
        
        if not TUSHARE_AVAILABLE:
            self.logger.error("❌ Tushare库未安装，请运行: pip install tushare")
    
    async def connect(self) -> bool:
        """连接到Tushare"""
        if not TUSHARE_AVAILABLE:
            self.logger.error("❌ Tushare库不可用")
            return False
        
        try:
            token = self.config.get('token')
            if not token:
                self.logger.error("❌ Tushare token未配置，请设置TUSHARE_TOKEN环境变量")
                return False
            
            # 设置token并初始化API
            ts.set_token(token)
            self.api = ts.pro_api()
            
            # 测试连接
            test_data = await asyncio.to_thread(
                self.api.stock_basic, 
                list_status='L', 
                limit=1
            )
            
            if test_data is not None and not test_data.empty:
                self.connected = True
                self.logger.info("✅ Tushare连接成功")
                return True
            else:
                self.logger.error("❌ Tushare连接测试失败")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Tushare连接失败: {e}")
            return False
    
    def is_available(self) -> bool:
        """检查Tushare是否可用"""
        return TUSHARE_AVAILABLE and self.connected and self.api is not None
    
    # ==================== 基础数据接口 ====================
    
    async def get_stock_list(self, market: str = None) -> Optional[List[Dict[str, Any]]]:
        """获取股票列表"""
        if not self.is_available():
            return None
        
        try:
            # 构建查询参数
            params = {
                'list_status': 'L',  # 只获取上市股票
                'fields': 'ts_code,symbol,name,area,industry,market,exchange,list_date,is_hs'
            }
            
            if market:
                # 根据市场筛选
                if market == "CN":
                    params['exchange'] = 'SSE,SZSE'  # 沪深交易所
                elif market == "HK":
                    return None  # Tushare港股需要单独处理
                elif market == "US":
                    return None  # Tushare不支持美股
            
            # 获取数据
            df = await asyncio.to_thread(self.api.stock_basic, **params)
            
            if df is None or df.empty:
                return None
            
            # 转换为标准格式
            stock_list = []
            for _, row in df.iterrows():
                stock_info = self.standardize_basic_info(row.to_dict())
                stock_list.append(stock_info)
            
            self.logger.info(f"✅ 获取股票列表: {len(stock_list)}只")
            return stock_list
            
        except Exception as e:
            self.logger.error(f"❌ 获取股票列表失败: {e}")
            return None
    
    async def get_stock_basic_info(self, symbol: str = None) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        """获取股票基础信息"""
        if not self.is_available():
            return None
        
        try:
            if symbol:
                # 获取单个股票信息
                ts_code = self._normalize_ts_code(symbol)
                df = await asyncio.to_thread(
                    self.api.stock_basic,
                    ts_code=ts_code,
                    fields='ts_code,symbol,name,area,industry,market,exchange,list_date,is_hs,act_name,act_ent_type'
                )
                
                if df is None or df.empty:
                    return None
                
                return self.standardize_basic_info(df.iloc[0].to_dict())
            else:
                # 获取所有股票信息
                return await self.get_stock_list()
                
        except Exception as e:
            self.logger.error(f"❌ 获取股票基础信息失败 symbol={symbol}: {e}")
            return None
    
    async def get_stock_quotes(self, symbol: str) -> Optional[Dict[str, Any]]:
        """获取实时行情"""
        if not self.is_available():
            return None
        
        try:
            ts_code = self._normalize_ts_code(symbol)
            
            # 尝试获取实时行情 (需要高级权限)
            try:
                df = await asyncio.to_thread(self.api.realtime_quote, ts_code=ts_code)
                if df is not None and not df.empty:
                    return self.standardize_quotes(df.iloc[0].to_dict())
            except Exception:
                # 权限不足，使用最新日线数据
                pass
            
            # 回退：使用最新日线数据
            end_date = datetime.now().strftime('%Y%m%d')
            df = await asyncio.to_thread(
                self.api.daily,
                ts_code=ts_code,
                start_date=end_date,
                end_date=end_date
            )
            
            if df is not None and not df.empty:
                # 获取每日指标补充数据
                basic_df = await asyncio.to_thread(
                    self.api.daily_basic,
                    ts_code=ts_code,
                    trade_date=end_date,
                    fields='ts_code,total_mv,circ_mv,pe,pb,turnover_rate'
                )
                
                # 合并数据
                quote_data = df.iloc[0].to_dict()
                if basic_df is not None and not basic_df.empty:
                    quote_data.update(basic_df.iloc[0].to_dict())
                
                return self.standardize_quotes(quote_data)
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ 获取实时行情失败 symbol={symbol}: {e}")
            return None
    
    async def get_historical_data(
        self, 
        symbol: str, 
        start_date: Union[str, date], 
        end_date: Union[str, date] = None
    ) -> Optional[pd.DataFrame]:
        """获取历史数据"""
        if not self.is_available():
            return None
        
        try:
            ts_code = self._normalize_ts_code(symbol)
            
            # 格式化日期
            start_str = self._format_date(start_date)
            end_str = self._format_date(end_date) if end_date else datetime.now().strftime('%Y%m%d')
            
            # 获取日线数据
            df = await asyncio.to_thread(
                self.api.daily,
                ts_code=ts_code,
                start_date=start_str,
                end_date=end_str
            )
            
            if df is None or df.empty:
                return None
            
            # 数据标准化
            df = self._standardize_historical_data(df)
            
            self.logger.info(f"✅ 获取历史数据: {symbol} {len(df)}条记录")
            return df
            
        except Exception as e:
            self.logger.error(f"❌ 获取历史数据失败 symbol={symbol}: {e}")
            return None
    
    # ==================== 扩展接口 ====================
    
    async def get_daily_basic(self, trade_date: str) -> Optional[pd.DataFrame]:
        """获取每日基础财务数据"""
        if not self.is_available():
            return None
        
        try:
            date_str = trade_date.replace('-', '')
            df = await asyncio.to_thread(
                self.api.daily_basic,
                trade_date=date_str,
                fields='ts_code,total_mv,circ_mv,pe,pb,turnover_rate,volume_ratio,pe_ttm,pb_mrq'
            )
            
            if df is not None and not df.empty:
                self.logger.info(f"✅ 获取每日基础数据: {trade_date} {len(df)}条记录")
                return df
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ 获取每日基础数据失败 trade_date={trade_date}: {e}")
            return None
    
    async def find_latest_trade_date(self) -> Optional[str]:
        """查找最新交易日期"""
        if not self.is_available():
            return None
        
        try:
            today = datetime.now()
            for delta in range(0, 10):  # 最多回溯10天
                check_date = (today - timedelta(days=delta)).strftime('%Y%m%d')
                
                try:
                    df = await asyncio.to_thread(
                        self.api.daily_basic,
                        trade_date=check_date,
                        fields='ts_code',
                        limit=1
                    )
                    
                    if df is not None and not df.empty:
                        formatted_date = f"{check_date[:4]}-{check_date[4:6]}-{check_date[6:8]}"
                        self.logger.info(f"✅ 找到最新交易日期: {formatted_date}")
                        return formatted_date
                        
                except Exception:
                    continue
            
            return None
            
        except Exception as e:
            self.logger.error(f"❌ 查找最新交易日期失败: {e}")
            return None
    
    async def get_financial_data(self, symbol: str, report_type: str = "annual") -> Optional[Dict[str, Any]]:
        """获取财务数据"""
        if not self.is_available():
            return None
        
        try:
            ts_code = self._normalize_ts_code(symbol)
            
            # 获取最新财务数据
            financial_data = {}
            
            # 利润表
            income_df = await asyncio.to_thread(
                self.api.income,
                ts_code=ts_code,
                limit=1
            )
            if income_df is not None and not income_df.empty:
                financial_data['income'] = income_df.iloc[0].to_dict()
            
            # 资产负债表
            balance_df = await asyncio.to_thread(
                self.api.balancesheet,
                ts_code=ts_code,
                limit=1
            )
            if balance_df is not None and not balance_df.empty:
                financial_data['balance'] = balance_df.iloc[0].to_dict()
            
            # 现金流量表
            cashflow_df = await asyncio.to_thread(
                self.api.cashflow,
                ts_code=ts_code,
                limit=1
            )
            if cashflow_df is not None and not cashflow_df.empty:
                financial_data['cashflow'] = cashflow_df.iloc[0].to_dict()
            
            if financial_data:
                return self._standardize_financial_data(financial_data)
            
            return None

        except Exception as e:
            self.logger.error(f"❌ 获取财务数据失败 symbol={symbol}: {e}")
            return None

    # ==================== 数据标准化方法 ====================

    def standardize_basic_info(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化股票基础信息"""
        ts_code = raw_data.get('ts_code', '')
        symbol = raw_data.get('symbol', ts_code.split('.')[0] if '.' in ts_code else ts_code)

        return {
            # 基础字段
            "code": symbol,
            "name": raw_data.get('name', ''),
            "symbol": symbol,
            "full_symbol": ts_code,

            # 市场信息
            "market_info": self._determine_market_info_from_ts_code(ts_code),

            # 业务信息
            "area": raw_data.get('area'),
            "industry": raw_data.get('industry'),
            "market": raw_data.get('market'),  # 主板/创业板/科创板
            "list_date": self._format_date_output(raw_data.get('list_date')),

            # 港股通信息
            "is_hs": raw_data.get('is_hs'),

            # 实控人信息
            "act_name": raw_data.get('act_name'),
            "act_ent_type": raw_data.get('act_ent_type'),

            # 元数据
            "data_source": "tushare",
            "data_version": 1,
            "updated_at": datetime.utcnow()
        }

    def standardize_quotes(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化实时行情数据"""
        ts_code = raw_data.get('ts_code', '')
        symbol = ts_code.split('.')[0] if '.' in ts_code else ts_code

        return {
            # 基础字段
            "code": symbol,
            "symbol": symbol,
            "full_symbol": ts_code,
            "market": self._determine_market(ts_code),

            # 价格数据
            "close": self._convert_to_float(raw_data.get('close')),
            "current_price": self._convert_to_float(raw_data.get('close')),
            "open": self._convert_to_float(raw_data.get('open')),
            "high": self._convert_to_float(raw_data.get('high')),
            "low": self._convert_to_float(raw_data.get('low')),
            "pre_close": self._convert_to_float(raw_data.get('pre_close')),

            # 变动数据
            "change": self._convert_to_float(raw_data.get('change')),
            "pct_chg": self._convert_to_float(raw_data.get('pct_chg')),

            # 成交数据
            "volume": self._convert_to_float(raw_data.get('vol')),
            "amount": self._convert_to_float(raw_data.get('amount')),

            # 财务指标
            "total_mv": self._convert_to_float(raw_data.get('total_mv')),
            "circ_mv": self._convert_to_float(raw_data.get('circ_mv')),
            "pe": self._convert_to_float(raw_data.get('pe')),
            "pb": self._convert_to_float(raw_data.get('pb')),
            "turnover_rate": self._convert_to_float(raw_data.get('turnover_rate')),

            # 时间数据
            "trade_date": self._format_date_output(raw_data.get('trade_date')),
            "timestamp": datetime.utcnow(),

            # 元数据
            "data_source": "tushare",
            "data_version": 1,
            "updated_at": datetime.utcnow()
        }

    # ==================== 辅助方法 ====================

    def _normalize_ts_code(self, symbol: str) -> str:
        """标准化为Tushare的ts_code格式"""
        if '.' in symbol:
            return symbol  # 已经是ts_code格式

        # 6位数字代码，需要添加后缀
        if symbol.isdigit() and len(symbol) == 6:
            if symbol.startswith(('60', '68', '90')):
                return f"{symbol}.SH"  # 上交所
            else:
                return f"{symbol}.SZ"  # 深交所

        return symbol

    def _determine_market_info_from_ts_code(self, ts_code: str) -> Dict[str, Any]:
        """根据ts_code确定市场信息"""
        if '.SH' in ts_code:
            return {
                "market": "CN",
                "exchange": "SSE",
                "exchange_name": "上海证券交易所",
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            }
        elif '.SZ' in ts_code:
            return {
                "market": "CN",
                "exchange": "SZSE",
                "exchange_name": "深圳证券交易所",
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            }
        elif '.BJ' in ts_code:
            return {
                "market": "CN",
                "exchange": "BSE",
                "exchange_name": "北京证券交易所",
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            }
        else:
            return {
                "market": "CN",
                "exchange": "UNKNOWN",
                "exchange_name": "未知交易所",
                "currency": "CNY",
                "timezone": "Asia/Shanghai"
            }

    def _determine_market(self, ts_code: str) -> str:
        """确定市场代码"""
        market_info = self._determine_market_info_from_ts_code(ts_code)
        return market_info.get("market", "CN")

    def _format_date(self, date_value: Union[str, date]) -> str:
        """格式化日期为Tushare格式 (YYYYMMDD)"""
        if isinstance(date_value, str):
            return date_value.replace('-', '')
        elif isinstance(date_value, date):
            return date_value.strftime('%Y%m%d')
        else:
            return str(date_value).replace('-', '')

    def _standardize_historical_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """标准化历史数据"""
        # 重命名列
        column_mapping = {
            'trade_date': 'date',
            'vol': 'volume'
        }
        df = df.rename(columns=column_mapping)

        # 格式化日期
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
            df.set_index('date', inplace=True)

        # 按日期排序
        df = df.sort_index()

        return df

    def _standardize_financial_data(self, financial_data: Dict[str, Any]) -> Dict[str, Any]:
        """标准化财务数据"""
        return {
            "symbol": financial_data.get('income', {}).get('ts_code', '').split('.')[0],
            "report_period": financial_data.get('income', {}).get('end_date'),
            "report_type": "quarterly",

            # 利润表数据
            "revenue": self._convert_to_float(financial_data.get('income', {}).get('revenue')),
            "net_income": self._convert_to_float(financial_data.get('income', {}).get('n_income')),
            "gross_profit": self._calculate_gross_profit(
                financial_data.get('income', {}).get('revenue'),
                financial_data.get('income', {}).get('oper_cost')
            ),

            # 资产负债表数据
            "total_assets": self._convert_to_float(financial_data.get('balance', {}).get('total_assets')),
            "total_equity": self._convert_to_float(financial_data.get('balance', {}).get('total_hldr_eqy_exc_min_int')),
            "total_liab": self._convert_to_float(financial_data.get('balance', {}).get('total_liab')),

            # 现金流量表数据
            "cash_flow": self._convert_to_float(financial_data.get('cashflow', {}).get('n_cashflow_act')),
            "operating_cf": self._convert_to_float(financial_data.get('cashflow', {}).get('n_cashflow_act')),

            # 元数据
            "data_source": "tushare",
            "updated_at": datetime.utcnow()
        }

    def _calculate_gross_profit(self, revenue, oper_cost) -> Optional[float]:
        """安全计算毛利润"""
        revenue_float = self._convert_to_float(revenue)
        oper_cost_float = self._convert_to_float(oper_cost)

        if revenue_float is not None and oper_cost_float is not None:
            return revenue_float - oper_cost_float
        return None


# 全局提供器实例
_tushare_provider = None

def get_tushare_provider() -> TushareProvider:
    """获取全局Tushare提供器实例"""
    global _tushare_provider
    if _tushare_provider is None:
        _tushare_provider = TushareProvider()
    return _tushare_provider
