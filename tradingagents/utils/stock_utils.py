"""
stock_utils.py - 股票工具占位模块
"""
import logging
logger = logging.getLogger("default")

class StockUtils:
    @staticmethod
    def get_market_info(ticker: str) -> dict:
        ticker_upper = str(ticker).upper()
        if any(s in ticker_upper for s in (".SHF", ".DCE", ".CZCE", ".INE", ".GFEX", ".CFFEX", ".SGE")):
            return {'is_china': False, 'is_hk': False, 'is_us': False, 'market_name': '大宗商品期货', 'currency_name': 'CNY', 'currency_symbol': '¥'}
        if ticker_upper.endswith(".SH") or ticker_upper.endswith(".SZ") or ticker_upper.endswith(".BJ"):
            return {'is_china': True, 'is_hk': False, 'is_us': False, 'market_name': '中国A股', 'currency_name': 'CNY', 'currency_symbol': '¥'}
        if ticker_upper.endswith(".HK"):
            return {'is_china': False, 'is_hk': True, 'is_us': False, 'market_name': '港股', 'currency_name': 'HKD', 'currency_symbol': 'HK$'}
        us = {"AAPL", "TSLA", "NVDA", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NFLX"}
        if ticker_upper in us or not any(c.isdigit() for c in ticker_upper):
            return {'is_china': False, 'is_hk': False, 'is_us': True, 'market_name': '美股', 'currency_name': 'USD', 'currency_symbol': '$'}
        return {'is_china': False, 'is_hk': False, 'is_us': False, 'market_name': '未知', 'currency_name': 'CNY', 'currency_symbol': '¥'}
