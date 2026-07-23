# 数据源集成 (v0.1.6)

## 概述

TradingAgents 中文增强版集成了多种金融数据源，特别加强了对中国期货市场的支持。为智能体提供全面、准确、实时的市场信息。本文档详细介绍了支持的数据源、API集成方法、数据格式和使用指南。

## 🔄 v0.1.6 重大更新

### 数据源迁移完成
- ✅ **主数据源**: 从通达信完全迁移到Tushare
- ✅ **混合策略**: Tushare(历史数据) + AKShare(实时数据)
- ✅ **统一接口**: 透明的数据源切换，用户无感知
- ✅ **向后兼容**: 保持所有API接口不变
- ✅ **用户界面**: 所有提示信息已更新为正确的数据源标识

## 🎯 v0.1.6 数据源状态

| 数据源 | 市场 | 状态 | 说明 |
|--------|------|------|------|
| 🇨🇳 **Tushare数据接口** | 国内期货 | ✅ 完整支持 | 实时行情、历史数据、技术指标 |
| **FinnHub** | 国际期货 | ✅ 完整支持 | 实时数据、基本面、新闻 |
| **Google News** | 全球 | ✅ 完整支持 | 财经新闻、市场资讯 |
| **Reddit** | 全球 | ✅ 完整支持 | 社交媒体情绪分析 |
| **MongoDB** | 缓存 | ✅ 完整支持 | 数据持久化存储 |
| **Redis** | 缓存 | ✅ 完整支持 | 高速数据缓存 |

## 支持的数据源

### 🇨🇳 1. Tushare数据接口 (新增 v0.1.3)

#### 简介
Tushare数据接口是中国领先的期货数据提供商，为期货市场提供实时行情和历史数据。

#### 数据类型
```python
tdx_data_types = {
    "实时数据": [
        "A股实时行情",
        "成交量",
        "涨跌幅",
        "换手率"
    ],
    "历史数据": [
        "日K线数据",
        "分钟级数据",
        "复权数据",
        "除权除息"
    ],
    "技术指标": [
        "MA移动平均",
        "MACD",
        "RSI",
        "KDJ"
    ],
    "市场数据": [
        "板块分类",
        "概念股",
        "龙虎榜",
        "资金流向"
    ]
}
```

#### 使用示例
```python
from tradingagents.dataflows.tdx_utils import get_stock_data

# 获取期货数据
data = get_stock_data(
    stock_code="000001",  # 平安银行
    start_date="2024-01-01",
    end_date="2024-12-31"
)
```

### 1. FinnHub API

#### 简介
FinnHub 是领先的金融数据提供商，提供实时期货价格、公司基本面数据、新闻和市场指标。

#### 数据类型
```python
finnhub_data_types = {
    "实时数据": [
        "期货价格",
        "交易量",
        "市场深度",
        "实时新闻"
    ],
    "基本面数据": [
        "财务报表",
        "公司概况",
        "分析师评级",
        "盈利预测"
    ],
    "技术指标": [
        "RSI",
        "MACD",
        "布林带",
        "移动平均线"
    ],
    "市场数据": [
        "IPO日历",
        "分红信息",
        "期货品种分割",
        "期权数据"
    ]
}
```

#### API 配置
```python
# finnhub_utils.py
import finnhub

class FinnHubDataProvider:
    """FinnHub 数据提供器"""
    
    def __init__(self, api_key: str):
        self.client = finnhub.Client(api_key=api_key)
        self.rate_limiter = RateLimiter(calls_per_minute=60)  # 免费版限制
    
    def get_stock_price(self, symbol: str) -> Dict:
        """获取期货价格"""
        with self.rate_limiter:
            quote = self.client.quote(symbol)
            return {
                "symbol": symbol,
                "current_price": quote.get("c"),
                "change": quote.get("d"),
                "change_percent": quote.get("dp"),
                "high": quote.get("h"),
                "low": quote.get("l"),
                "open": quote.get("o"),
                "previous_close": quote.get("pc"),
                "timestamp": quote.get("t")
            }
    
    def get_company_profile(self, symbol: str) -> Dict:
        """获取公司概况"""
        with self.rate_limiter:
            profile = self.client.company_profile2(symbol=symbol)
            return {
                "symbol": symbol,
                "name": profile.get("name"),
                "industry": profile.get("finnhubIndustry"),
                "sector": profile.get("gsubind"),
                "market_cap": profile.get("marketCapitalization"),
                "shares_outstanding": profile.get("shareOutstanding"),
                "website": profile.get("weburl"),
                "logo": profile.get("logo"),
                "exchange": profile.get("exchange")
            }
    
    def get_financial_statements(self, symbol: str, statement_type: str = "ic") -> Dict:
        """获取财务报表"""
        with self.rate_limiter:
            financials = self.client.financials(symbol, statement_type, "annual")
            return {
                "symbol": symbol,
                "statement_type": statement_type,
                "data": financials.get("financials", []),
                "currency": financials.get("currency"),
                "last_updated": financials.get("cik")
            }
```

#### 使用示例
```python
# 初始化 FinnHub 客户端
finnhub_provider = FinnHubDataProvider(api_key=os.getenv("FINNHUB_API_KEY"))

# 获取期货价格
price_data = finnhub_provider.get_stock_price("AAPL")
print(f"AAPL 当前价格: ${price_data['current_price']}")

# 获取公司信息
company_info = finnhub_provider.get_company_profile("AAPL")
print(f"公司名称: {company_info['name']}")
```

### 2. Yahoo Finance

#### 简介
Yahoo Finance 提供免费的历史期货数据、财务信息和市场指标，是获取历史数据的优秀选择。

#### 数据类型
```python
yahoo_finance_data_types = {
    "历史数据": [
        "期货价格历史",
        "交易量历史",
        "调整后价格",
        "股息历史"
    ],
    "财务数据": [
        "损益表",
        "资产负债表",
        "现金流量表",
        "关键指标"
    ],
    "市场数据": [
        "期权链",
        "分析师建议",
        "机构持股",
        "内部人交易"
    ]
}
```

#### API 集成
```python
# yfin_utils.py
import yfinance as yf
import pandas as pd

class YahooFinanceProvider:
    """Yahoo Finance 数据提供器"""
    
    def __init__(self):
        self.cache = {}
        self.cache_duration = 300  # 5分钟缓存
    
    def get_historical_data(self, symbol: str, period: str = "1y") -> pd.DataFrame:
        """获取历史数据"""
        cache_key = f"{symbol}_{period}"
        
        if self._is_cache_valid(cache_key):
            return self.cache[cache_key]["data"]
        
        ticker = yf.Ticker(symbol)
        hist_data = ticker.history(period=period)
        
        # 缓存数据
        self.cache[cache_key] = {
            "data": hist_data,
            "timestamp": time.time()
        }
        
        return hist_data
    
    def get_financial_info(self, symbol: str) -> Dict:
        """获取财务信息"""
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        return {
            "symbol": symbol,
            "market_cap": info.get("marketCap"),
            "enterprise_value": info.get("enterpriseValue"),
            "pe_ratio": info.get("trailingPE"),
            "pb_ratio": info.get("priceToBook"),
            "debt_to_equity": info.get("debtToEquity"),
            "roe": info.get("returnOnEquity"),
            "revenue_growth": info.get("revenueGrowth"),
            "profit_margins": info.get("profitMargins"),
            "beta": info.get("beta")
        }
    
    def get_technical_indicators(self, symbol: str, period: str = "1y") -> Dict:
        """计算技术指标"""
        hist_data = self.get_historical_data(symbol, period)
        
        # 计算移动平均线
        hist_data["MA_20"] = hist_data["Close"].rolling(window=20).mean()
        hist_data["MA_50"] = hist_data["Close"].rolling(window=50).mean()
        
        # 计算 RSI
        hist_data["RSI"] = self._calculate_rsi(hist_data["Close"])
        
        # 计算 MACD
        macd_data = self._calculate_macd(hist_data["Close"])
        hist_data = pd.concat([hist_data, macd_data], axis=1)
        
        return {
            "symbol": symbol,
            "indicators": hist_data.tail(1).to_dict("records")[0],
            "trend_analysis": self._analyze_trend(hist_data),
            "support_resistance": self._find_support_resistance(hist_data)
        }
```

### 3. Reddit API

#### 简介
Reddit API 提供社交媒体讨论数据，用于分析投资者情绪和市场热点。

#### 数据类型
```python
reddit_data_types = {
    "讨论数据": [
        "热门帖子",
        "评论内容",
        "用户互动",
        "话题趋势"
    ],
    "情感数据": [
        "情感极性",
        "情感强度",
        "情感分布",
        "情感变化"
    ],
    "热度指标": [
        "提及频率",
        "讨论热度",
        "用户参与度",
        "传播速度"
    ]
}
```

#### API 集成
```python
# reddit_utils.py
import praw
from textblob import TextBlob

class RedditDataProvider:
    """Reddit 数据提供器"""
    
    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        self.reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=user_agent
        )
        self.sentiment_analyzer = SentimentAnalyzer()
    
    def get_stock_discussions(self, symbol: str, subreddit: str = "stocks", limit: int = 100) -> List[Dict]:
        """获取期货品种讨论"""
        discussions = []
        
        # 搜索相关帖子
        for submission in self.reddit.subreddit(subreddit).search(symbol, limit=limit):
            # 分析情感
            sentiment = self.sentiment_analyzer.analyze(submission.title + " " + submission.selftext)
            
            discussions.append({
                "id": submission.id,
                "title": submission.title,
                "content": submission.selftext,
                "score": submission.score,
                "num_comments": submission.num_comments,
                "created_utc": submission.created_utc,
                "author": str(submission.author),
                "url": submission.url,
                "sentiment": sentiment
            })
        
        return discussions
    
    def analyze_sentiment_trends(self, discussions: List[Dict]) -> Dict:
        """分析情感趋势"""
        if not discussions:
            return {"error": "No discussions found"}
        
        # 计算整体情感
        sentiments = [d["sentiment"]["polarity"] for d in discussions]
        avg_sentiment = sum(sentiments) / len(sentiments)
        
        # 时间序列分析
        time_series = self._create_sentiment_time_series(discussions)
        
        # 热度分析
        engagement_metrics = self._calculate_engagement_metrics(discussions)
        
        return {
            "overall_sentiment": avg_sentiment,
            "sentiment_distribution": self._calculate_sentiment_distribution(sentiments),
            "time_series": time_series,
            "engagement_metrics": engagement_metrics,
            "trending_topics": self._extract_trending_topics(discussions)
        }
```

### 4. Google News

#### 简介
Google News API 提供实时新闻数据，用于分析市场事件和新闻对股价的影响。

#### 数据类型
```python
google_news_data_types = {
    "新闻内容": [
        "新闻标题",
        "新闻正文",
        "发布时间",
        "新闻来源"
    ],
    "影响分析": [
        "新闻情感",
        "影响程度",
        "相关性评分",
        "时效性分析"
    ],
    "事件追踪": [
        "事件时间线",
        "关联事件",
        "影响范围",
        "后续发展"
    ]
}
```

#### API 集成
```python
# googlenews_utils.py
from GoogleNews import GoogleNews
import requests
from bs4 import BeautifulSoup

class GoogleNewsProvider:
    """Google News 数据提供器"""
    
    def __init__(self):
        self.googlenews = GoogleNews()
        self.sentiment_analyzer = SentimentAnalyzer()
    
    def get_stock_news(self, symbol: str, days: int = 7) -> List[Dict]:
        """获取期货品种相关新闻"""
        # 设置搜索参数
        self.googlenews.clear()
        self.googlenews.set_time_range(f"{days}d")
        self.googlenews.set_lang("en")
        
        # 搜索新闻
        search_terms = [symbol, f"{symbol} stock", f"{symbol} earnings"]
        all_news = []
        
        for term in search_terms:
            self.googlenews.search(term)
            news_results = self.googlenews.results()
            
            for news in news_results:
                # 获取新闻详情
                news_detail = self._get_news_detail(news)
                if news_detail:
                    all_news.append(news_detail)
        
        # 去重和排序
        unique_news = self._deduplicate_news(all_news)
        return sorted(unique_news, key=lambda x: x["published_date"], reverse=True)
    
    def _get_news_detail(self, news_item: Dict) -> Dict:
        """获取新闻详情"""
        try:
            # 分析新闻情感
            sentiment = self.sentiment_analyzer.analyze(news_item.get("title", ""))
            
            # 评估新闻重要性
            importance = self._assess_news_importance(news_item)
            
            return {
                "title": news_item.get("title"),
                "link": news_item.get("link"),
                "published_date": news_item.get("date"),
                "source": news_item.get("media"),
                "sentiment": sentiment,
                "importance": importance,
                "relevance_score": self._calculate_relevance_score(news_item)
            }
        except Exception as e:
            print(f"Error processing news item: {e}")
            return None
    
    def analyze_news_impact(self, news_list: List[Dict], symbol: str) -> Dict:
        """分析新闻影响"""
        if not news_list:
            return {"error": "No news found"}
        
        # 情感分析
        sentiment_analysis = self._analyze_news_sentiment(news_list)
        
        # 影响评估
        impact_assessment = self._assess_news_impact(news_list, symbol)
        
        # 时间线分析
        timeline_analysis = self._create_news_timeline(news_list)
        
        return {
            "sentiment_analysis": sentiment_analysis,
            "impact_assessment": impact_assessment,
            "timeline_analysis": timeline_analysis,
            "key_events": self._identify_key_events(news_list),
            "market_implications": self._analyze_market_implications(news_list, symbol)
        }
```

## 数据集成接口

### 统一数据接口
```python
# interface.py
class DataInterface:
    """统一数据接口"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.providers = self._initialize_providers()
        self.cache_manager = CacheManager()
        
    def _initialize_providers(self) -> Dict:
        """初始化数据提供器"""
        providers = {}
        
        # FinnHub
        if self.config.get("finnhub_api_key"):
            providers["finnhub"] = FinnHubDataProvider(self.config["finnhub_api_key"])
        
        # Yahoo Finance
        providers["yahoo"] = YahooFinanceProvider()
        
        # Reddit
        if self.config.get("reddit_credentials"):
            providers["reddit"] = RedditDataProvider(**self.config["reddit_credentials"])
        
        # Google News
        providers["google_news"] = GoogleNewsProvider()
        
        return providers
    
    def get_comprehensive_data(self, symbol: str, date: str = None) -> Dict:
        """获取综合数据"""
        data = {}
        
        # 并行获取数据
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(self._get_price_data, symbol): "price_data",
                executor.submit(self._get_fundamental_data, symbol): "fundamental_data",
                executor.submit(self._get_news_data, symbol): "news_data",
                executor.submit(self._get_social_data, symbol): "social_data"
            }
            
            for future in as_completed(futures):
                data_type = futures[future]
                try:
                    data[data_type] = future.result()
                except Exception as e:
                    print(f"Error fetching {data_type}: {e}")
                    data[data_type] = {}
        
        return data
    
    def _get_price_data(self, symbol: str) -> Dict:
        """获取价格数据"""
        # 优先使用 FinnHub，备用 Yahoo Finance
        if "finnhub" in self.providers:
            try:
                return self.providers["finnhub"].get_stock_price(symbol)
            except Exception:
                pass
        
        if "yahoo" in self.providers:
            hist_data = self.providers["yahoo"].get_historical_data(symbol, "5d")
            latest = hist_data.iloc[-1]
            return {
                "symbol": symbol,
                "current_price": latest["Close"],
                "change": latest["Close"] - latest["Open"],
                "high": latest["High"],
                "low": latest["Low"],
                "volume": latest["Volume"]
            }
        
        return {}
```

## 数据质量控制

### 数据验证
```python
class DataValidator:
    """数据验证器"""
    
    def validate_data(self, data: Dict, data_type: str) -> Tuple[bool, List[str]]:
        """验证数据质量"""
        errors = []
        
        # 基本完整性检查
        if not data:
            errors.append("Data is empty")
            return False, errors
        
        # 特定类型验证
        if data_type == "price_data":
            errors.extend(self._validate_price_data(data))
        elif data_type == "fundamental_data":
            errors.extend(self._validate_fundamental_data(data))
        elif data_type == "news_data":
            errors.extend(self._validate_news_data(data))
        elif data_type == "social_data":
            errors.extend(self._validate_social_data(data))
        
        return len(errors) == 0, errors
    
    def _validate_price_data(self, data: Dict) -> List[str]:
        """验证价格数据"""
        errors = []
        
        required_fields = ["symbol", "current_price"]
        for field in required_fields:
            if field not in data:
                errors.append(f"Missing required field: {field}")
        
        # 价格合理性检查
        if "current_price" in data:
            price = data["current_price"]
            if not isinstance(price, (int, float)) or price <= 0:
                errors.append("Invalid price value")
        
        return errors
```

## 使用最佳实践

### 1. API 限制管理
```python
class RateLimiter:
    """API 限制管理器"""
    
    def __init__(self, calls_per_minute: int):
        self.calls_per_minute = calls_per_minute
        self.calls = []
    
    def __enter__(self):
        current_time = time.time()
        
        # 清理过期的调用记录
        self.calls = [call_time for call_time in self.calls if current_time - call_time < 60]
        
        # 检查是否超过限制
        if len(self.calls) >= self.calls_per_minute:
            sleep_time = 60 - (current_time - self.calls[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        self.calls.append(current_time)
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
```

### 2. 错误处理和重试
```python
def with_retry(max_retries: int = 3, delay: float = 1.0):
    """重试装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    time.sleep(delay * (2 ** attempt))  # 指数退避
            return None
        return wrapper
    return decorator
```

### 3. 数据缓存策略
```python
class CacheManager:
    """缓存管理器"""
    
    def __init__(self):
        self.cache = {}
        self.cache_ttl = {
            "price_data": 60,      # 1分钟
            "fundamental_data": 3600,  # 1小时
            "news_data": 1800,     # 30分钟
            "social_data": 900     # 15分钟
        }
    
    def get(self, key: str, data_type: str) -> Optional[Dict]:
        """获取缓存数据"""
        if key in self.cache:
            cached_item = self.cache[key]
            ttl = self.cache_ttl.get(data_type, 3600)
            
            if time.time() - cached_item["timestamp"] < ttl:
                return cached_item["data"]
            else:
                del self.cache[key]
        
        return None
    
    def set(self, key: str, data: Dict, data_type: str):
        """设置缓存数据"""
        self.cache[key] = {
            "data": data,
            "timestamp": time.time(),
            "type": data_type
        }
```

通过这些数据源的集成，TradingAgents 能够获得全面、实时、高质量的市场数据，为智能体的分析和决策提供坚实的数据基础。
