from __future__ import annotations

from typing import Optional, List
import pandas as pd

from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')

# BaoStock 按官方库无需显式用户名/密码，bs.login() 走匿名登录


def _to_baostock_code(symbol: str) -> str:
    s = str(symbol).strip().upper()
    # 处理 600519.SH / 000001.SZ / 600519 / 000001
    if s.endswith('.SH') or s.endswith('.SZ'):
        code, exch = s.split('.')
        prefix = 'sh' if exch == 'SH' else 'sz'
        return f"{prefix}.{code}"
    # 6 开头上交所，否则深交所（简化规则）
    if len(s) >= 6 and s[0] == '6':
        return f"sh.{s[:6]}"
    return f"sz.{s[:6]}"


class BaoStockProvider:
    def __init__(self):
        self._ok = None  # 延迟登录

    def _ensure_login(self) -> bool:
        if self._ok is True:
            return True
        try:
            import baostock as bs
            lg = bs.login()  # 匿名登录
            if lg.error_code != '0':
                logger.error(f"❌ BaoStock登录失败: {lg.error_msg}")
                self._ok = False
                return False
            self._ok = True
            return True
        except Exception as e:
            logger.error(f"❌ BaoStock库不可用: {e}")
            self._ok = False
            return False

    def get_stock_data(self, symbol: str, start_date: str, end_date: str,
                        adjustflag: str = '2') -> pd.DataFrame:
        """
        获取日线数据（默认前复权 adjustflag='2'）。
        返回列：date, code, open, high, low, close, volume, amount, pctChg
        """
        if not self._ensure_login():
            return pd.DataFrame()
        try:
            import baostock as bs
            bs_code = _to_baostock_code(symbol)
            fields = (
                'date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,'
                'tradestatus,pctChg,isST'
            )
            rs = bs.query_history_k_data_plus(
                code=bs_code,
                fields=fields,
                start_date=start_date,
                end_date=end_date,
                frequency='d',
                adjustflag=adjustflag,
            )
            if rs.error_code != '0':
                logger.error(f"❌ BaoStock查询失败: {rs.error_msg}")
                return pd.DataFrame()
            data_list: List[List[str]] = []
            while (rs.error_code == '0') & rs.next():
                data_list.append(rs.get_row_data())
            if not data_list:
                return pd.DataFrame()
            df = pd.DataFrame(data_list, columns=rs.fields)
            # 转换类型
            for c in ['open','high','low','close','preclose','volume','amount','pctChg','turn']:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors='coerce')
            # 只保留必需列
            keep = ['date','code','open','high','low','close','volume','amount','pctChg']
            df = df[keep]
            # 统一列名在上层 unified_dataframe 处理，这里保持原始以减少差异
            return df
        except Exception as e:
            logger.error(f"❌ BaoStock获取数据异常: {e}")
            return pd.DataFrame()

    def get_stock_info(self, symbol: str) -> dict:
        """获取基础信息（可选）。"""
        try:
            import baostock as bs
            if not self._ensure_login():
                return {"symbol": symbol}
            bs_code = _to_baostock_code(symbol)
            rs = bs.query_stock_basic(code=bs_code)
            if rs.error_code != '0':
                return {"symbol": symbol}
            rows = []
            while (rs.error_code == '0') & rs.next():
                rows.append(rs.get_row_data())
            if not rows:
                return {"symbol": symbol}
            row = rows[0]
            # 返回字段文档中定义，索引访问
            return {
                "symbol": symbol,
                "name": row[1],  # code_name
                "list_date": row[2],
                "source": "baostock",
            }
        except Exception:
            return {"symbol": symbol}


# 全局实例
_baostock_provider: Optional[BaoStockProvider] = None

def get_baostock_provider() -> BaoStockProvider:
    global _baostock_provider
    if _baostock_provider is None:
        _baostock_provider = BaoStockProvider()
    return _baostock_provider

