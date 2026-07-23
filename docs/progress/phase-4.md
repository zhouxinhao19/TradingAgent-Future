# Phase 4 — 大宗商品模拟交易(设计文档)

> **创建日期**:2026-07-14
> **状态**:🟡 设计稿(等待用户签字后开工)
> **前置**:Phase 3b 已完成(7 commits,174 测试 0 失败,HEAD=57392d43,CIO 决策链输出可用)
> **兄弟参考**:`TradingAgents_for_Futures-main/期货TradingAgents系统_交易员.py`(借鉴 Kelly 仓位 / 风控 / 执行计划 schema,**没有完整撮合系统**)

---

## 〇、为什么 Phase 4 是全新的设计

参考项目 `TradingAgents_for_Futures-main/` 止步于"输出 TradingDecision",**没有模拟撮合、没有账户体系、没有 PnL 跟踪、没有强平逻辑**。我们的 Phase 4 必须从零搭建一套完整的"决策 → 下单 → 撮合 → 持仓 → 盯市 → 风控"闭环,这是参考项目完全没做过的事。

可借鉴的部分:
- `期货TradingAgents系统_交易员.py:633-700` 的 Kelly / Vol / RiskParity 仓位算法
- `RiskParameters.stop_loss / take_profit` 风控字段定义
- `ExecutionPlan.order_type / execution_method` 订单类型枚举
- 合约规格字段(品种 → multiplier / margin_rate 映射)

不可借鉴、必须自建的部分:
- 账户 / 订单 / 持仓 / 成交四类持久化对象
- 撮合引擎(市价 / 限价 / 止损 / 条件单)
- 盯市 / 浮动盈亏 / 已实现盈亏
- 保证金追缴 / 强平
- 多用户隔离 / SSE 实时推送

---

## 一、目标与验收

### 1.1 一句话目标

把 Phase 3b 的 CIO 决策**自动转成模拟订单**,让用户在浏览器里"看到自己的虚拟账户跟着 AI 决策下单、持仓变化、净值起伏"。

### 1.2 验收标准

| # | 标准 | 验证方式 |
|---|---|---|
| 1 | `POST /api/commodity/paper/accounts` 新建账户成功 | `curl` 200 + MongoDB `paper_accounts` 有 1 条 |
| 2 | `POST /api/commodity/paper/orders` 下单 → 撮合 → 持仓落库 | 看 SSE 推送 + `GET /paper/positions` 出现 |
| 3 | 止损触发自动平仓 | mock 价格到止损位 → 持仓消失 + fill 出现 |
| 4 | 保证金不足拒单 | 满仓后下单返回 422 |
| 5 | Phase 3b `from_decision` 联动 | `POST /paper/from-decision` → 订单来源 = `agent_decision` |
| 6 | Vue 页面 `PaperTrading.vue` 实时刷新 | 浏览器开 2 tab,A 下单 B 看到 |
| 7 | PnL 折线图 30 天可查 | `GET /paper/snapshots?days=30` 返回日终快照数组 |
| 8 | 60+ 单测全过 | `pytest tests/test_commodity_paper.py` 0 失败 |

---

## 二、模块结构

```
tradingagents/paper/                            ⭐ 新建(纯规则引擎,零 LLM)
├── __init__.py
├── spec.py                                     合约规格(multiplier/margin_rate/limit/commission)
├── matcher.py                                  撮合引擎(market/limit/stop/next-bar)
├── pnl.py                                      盯市 + 浮动 / 已实现 PnL
├── account.py                                  账户聚合(余额/可用/占用/净值/风险度)
├── risk.py                                     风控(止损止盈/保证金追缴/强平/限额)
└── repo.py                                     MongoDB 读写封装(4 集合)

app/routers/commodity/paper_rules.py            15 HTTP 端点
app/services/commodity/paper_trading_service.py 业务编排 + from_decision
app/models/commodity_paper.py                   MongoDB ODM(Pydantic v2)

frontend/src/views/Commodity/PaperTrading.vue   账户卡片 + 持仓表 + 订单表 + PnL 折线图
frontend/src/stores/commodity_paper.ts          Pinia store
frontend/src/api/commodity.ts                   追加 15 paper_* 方法

tests/test_commodity_paper.py                   60-80 单元测试
```

---

## 三、数据模型(MongoDB 4 集合)

### 3.1 `paper_accounts` — 账户主表

```python
class PaperAccount(BaseModel):
    id: str = Field(default_factory=uuid4)
    user_id: str                                # 关联 app/models/user.py
    name: str = "默认账户"
    initial_capital: float = 1_000_000.0        # 初始资金
    balance: float                              # 账户余额(扣手续费/已实现盈亏)
    available: float                            # 可用资金 = balance - margin_used - frozen
    margin_used: float = 0.0                    # 占用保证金
    frozen: float = 0.0                         # 冻结(挂单未成交)
    equity: float                               # 净值 = balance + 浮动盈亏
    realized_pnl: float = 0.0                   # 累计已实现盈亏
    unrealized_pnl: float = 0.0                 # 当前浮动盈亏
    risk_ratio: float = 0.0                     # 风险度 = margin_used / equity
    status: Literal["active", "closed"] = "active"
    created_at: datetime
    updated_at: datetime
```

### 3.2 `paper_orders` — 订单表

```python
class PaperOrder(BaseModel):
    id: str
    account_id: str
    full_symbol: str                            # "CU2501.SHF"
    direction: Literal["long", "short"]         # 持仓方向
    offset: Literal["open", "close", "close_today", "close_yesterday"]
    order_type: Literal["market", "limit", "stop", "stop_limit"]
    lots: int                                   # 委托手数
    price: Optional[float]                      # 限价(限价单才有)
    stop_price: Optional[float]                 # 触发价(stop 类才有)
    stop_loss: Optional[float] = None           # 附带止损
    take_profit: Optional[float] = None         # 附带止盈
    status: Literal[
        "pending", "filled", "partial", "cancelled", "rejected"
    ] = "pending"
    filled_lots: int = 0
    filled_avg_price: float = 0.0
    commission: float = 0.0                     # 累计手续费
    slippage: float = 0.0                       # 累计滑点
    reject_reason: Optional[str] = None         # 拒单原因(资金/涨跌停/限额)
    source: Literal["manual", "agent_decision"] = "manual"
    decision_id: Optional[str] = None           # 来自 Phase 3b CIO 输出
    created_at: datetime
    filled_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
```

### 3.3 `paper_positions` — 持仓表(净持仓)

```python
class PaperPosition(BaseModel):
    id: str
    account_id: str
    full_symbol: str
    direction: Literal["long", "short"]
    lots: int
    avg_cost: float                             # 加权平均成本(含手续费)
    current_price: float                        # 最新价(每分钟更新)
    floating_pnl: float = 0.0                   # (current - avg_cost) × lots × multiplier
    margin_used: float = 0.0
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    opened_at: datetime
    updated_at: datetime
```

### 3.4 `paper_fills` — 成交明细(append-only)

```python
class PaperFill(BaseModel):
    id: str
    order_id: str
    account_id: str
    full_symbol: str
    direction: Literal["long", "short"]
    offset: Literal["open", "close", ...]
    lots: int
    price: float                                # 实际成交价(含滑点)
    commission: float
    slippage: float
    matched_at: datetime                        # 撮合时间
```

### 3.5 `paper_daily_snapshots` — 日终快照(供 PnL 折线图)

```python
class PaperDailySnapshot(BaseModel):
    id: str
    account_id: str
    date: date                                  # YYYY-MM-DD
    equity: float                               # 当日收盘后净值
    balance: float
    realized_pnl: float
    unrealized_pnl: float
    positions_count: int
    trades_count: int                           # 当日成交笔数
    snapshot_at: datetime                       # 收盘后 15:30 落库
```

---

## 四、合约规格(`tradingagents/paper/spec.py`)

### 4.1 字段扩展

需要在 `tradingagents/dataflows/providers/commodity/commodity_metadata.py` 的品种字典里**新增 4 个字段**(`contract_size / tick_size` 已存在,补 `multiplier / margin_rate / commission_rate / limit_up_down_pct`):

```python
# _SHFE_VARIETIES 等列表每行扩展为 13 元组
("CU", "CU", "铜", "shfe", "metal", "吨", 5, 10, "1999-06-18",
 5, 0.07, 0.0001, 0.07),       # ← 新增 multiplier / margin_rate / commission_rate / limit_up_down
#              contract_size=5(1 手 = 5 吨)即 multiplier
#              含义 = "一手多少吨" = 多头 1 手持仓的标的价值倍数
```

> 注:参考项目 `期货TradingAgents系统_交易员.py:188` 的 `multiplier` 实际就是 `contract_size`(一手对应的实物数量)。我们直接复用 `contract_size` 不另起字段,只补 `margin_rate / commission_rate / limit_up_down_pct`。

### 4.2 `ContractSpec` 抽象

```python
@dataclass(frozen=True)
class ContractSpec:
    symbol: str                                  # "CU"
    name_cn: str                                 # "铜"
    exchange: str                                # "SHFE"
    contract_size: int                           # 1 手 = ? 吨
    tick_size: float                             # 最小变动价位
    margin_rate: float                           # 保证金率(0~1)
    commission_rate: float                       # 手续费率(双边)
    limit_up_down: float                         # 涨跌停板(0.07 = 7%)
    unit: str                                    # "吨"
    trading_hours: tuple[tuple[int, int], ...]   # [(9,0), (10,15), (13,30), (15,0), ...]

    @classmethod
    def from_variety(cls, variety_code: str) -> "ContractSpec":
        return _SPEC_INDEX[variety_code]

def calc_margin(lots: int, price: float, spec: ContractSpec) -> float:
    """占用保证金 = lots × price × contract_size × margin_rate"""
    return lots * price * spec.contract_size * spec.margin_rate

def calc_commission(lots: int, price: float, spec: ContractSpec) -> float:
    """手续费 = lots × price × contract_size × commission_rate(双边按比例)"""
    return lots * price * spec.contract_size * spec.commission_rate

def check_price_limit(price: float, prev_settlement: float, spec: ContractSpec) -> bool:
    """涨跌停预检:True 表示价格在涨跌停内可成交"""
    upper = prev_settlement * (1 + spec.limit_up_down)
    lower = prev_settlement * (1 - spec.limit_up_down)
    return lower <= price <= upper
```

### 4.3 保证金率参考值(待补)

参考项目给的 8 个品种:`RB 8% / CU 7% / AU 6% / AG 8% / I 8% / J 8% / M 6% / Y 6%`。
其余品种按"交易所保证金 + 3%"(期货公司默认)估算,后续接入真实数据时再校准。

---

## 五、撮合引擎(`tradingagents/paper/matcher.py`)

### 5.1 撮合模式(配置项 `PAPER_MATCHING_MODE`)

| 模式 | 适用场景 | 算法 |
|---|---|---|
| `current_price` | 演示模式(默认) | 立即按当前市价成交(对用户最直观) |
| `next_bar_open` | 回测友好 | 下一根 K 线开盘价成交 |
| `vwap` | 大单 | 当日 VWAP(简化:取最近 5 分钟均值) |

### 5.2 撮合流程

```python
async def submit_order(account_id: str, req: SubmitOrderRequest) -> PaperOrder:
    # 1. 资金/涨跌停/限额预检
    spec = ContractSpec.from_variety(parse_variety(req.full_symbol))
    prev_settlement = await get_prev_settlement(req.full_symbol)
    if req.order_type == "limit" and not check_price_limit(req.price, prev_settlement, spec):
        return await _reject_order(req, "price_exceeds_limit")
    if req.offset == "open":
        required = calc_margin(req.lots, req.price or prev_settlement, spec)
        if required > account.available:
            return await _reject_order(req, "insufficient_margin")
    # 2. 写 paper_orders(status=pending)
    order = await repo.insert_order(...)
    await sse.publish(user_id, "paper.order.pending", order.dict())
    # 3. 异步撮合(后台 task)
    asyncio.create_task(_match_order(order, spec))
    return order

async def _match_order(order: PaperOrder, spec: ContractSpec):
    if order.order_type == "market" or PAPER_MATCHING_MODE == "current_price":
        fill_price = await get_realtime_quote(order.full_symbol)
    elif order.order_type == "limit":
        fill_price = await _poll_until_fill(order, spec)  # 轮询价格 ≤ 限价
    elif order.order_type == "stop":
        fill_price = await _poll_until_trigger(order, spec)
    # 4. 应用滑点(不利方向滑动)
    slippage = fill_price * PAPER_SLIPPAGE_BPS * (1 if order.direction == "long" else -1)
    fill_price += slippage
    # 5. 更新 paper_orders(status=filled)
    # 6. 更新/创建 paper_positions
    # 7. 计算手续费 + 写 paper_fills
    # 8. 更新 paper_accounts(balance/available/margin_used)
    # 9. 推送 SSE "paper.order.filled"
    # 10. 触发风控巡检
    await risk_engine.check_after_fill(account_id)
```

### 5.3 滑点 / 手续费 / 涨跌停预检

```python
PAPER_SLIPPAGE_BPS = float(os.getenv("PAPER_SLIPPAGE_BPS", "1"))    # 1bp = 0.01%
PAPER_MATCHING_MODE = os.getenv("PAPER_MATCHING_MODE", "current_price")
PAPER_MAX_LOTS_PER_ORDER = int(os.getenv("PAPER_MAX_LOTS_PER_ORDER", "10"))
PAPER_MAX_POSITION_PER_SYMBOL = int(os.getenv("PAPER_MAX_POSITION_PER_SYMBOL", "50"))
```

---

## 六、PnL & 账户(`pnl.py` + `account.py`)

```python
# pnl.py
def calc_floating_pnl(pos: PaperPosition, current_price: float, spec: ContractSpec) -> float:
    sign = 1 if pos.direction == "long" else -1
    return (current_price - pos.avg_cost) * pos.lots * spec.contract_size * sign

def calc_realized_pnl(open_avg: float, close_price: float,
                      lots: int, direction: str, spec: ContractSpec) -> float:
    sign = 1 if direction == "long" else -1
    return (close_price - open_avg) * lots * spec.contract_size * sign

# account.py
def recalculate_account(account: PaperAccount, positions: list[PaperPosition]) -> PaperAccount:
    """重算账户:equity / risk_ratio / margin_used / floating_pnl"""
    account.unrealized_pnl = sum(p.floating_pnl for p in positions)
    account.margin_used = sum(p.margin_used for p in positions)
    account.equity = account.balance + account.unrealized_pnl
    account.available = account.equity - account.margin_used - account.frozen
    account.risk_ratio = account.margin_used / account.equity if account.equity > 0 else 999
    return account
```

---

## 七、风控(`risk.py`)

```python
async def check_after_fill(account_id: str):
    """成交后风控巡检:止损止盈 / 保证金追缴 / 强平"""
    account = await repo.get_account(account_id)
    positions = await repo.get_positions(account_id)
    # 1. 更新所有持仓的最新价 + 浮盈
    for pos in positions:
        spec = ContractSpec.from_variety(parse_variety(pos.full_symbol))
        pos.current_price = await get_realtime_quote(pos.full_symbol)
        pos.floating_pnl = calc_floating_pnl(pos, pos.current_price, spec)
    # 2. 止损止盈触发
    for pos in positions:
        if pos.stop_loss and _is_triggered(pos, pos.stop_loss):
            await _auto_close(pos, reason="stop_loss")
        if pos.take_profit and _is_triggered(pos, pos.take_profit):
            await _auto_close(pos, reason="take_profit")
    # 3. 重新计算账户指标
    account = recalculate_account(account, positions)
    await repo.save_account(account)
    # 4. 风险度 > 100% → 强平
    if account.risk_ratio > 1.0:
        await _force_close_all(account, reason="margin_call")
        await sse.publish(user_id, "paper.risk.alert",
                          {"type": "margin_call", "ratio": account.risk_ratio})

def _is_triggered(pos: PaperPosition, trigger_price: float) -> bool:
    """多仓:最新价 ≤ trigger;空仓:最新价 ≥ trigger"""
    if pos.direction == "long":
        return pos.current_price <= trigger_price
    return pos.current_price >= trigger_price
```

---

## 八、HTTP 路由(`app/routers/commodity/paper_rules.py`)

15 个端点:

```
# 账户
POST   /api/commodity/paper/accounts                  新建
GET    /api/commodity/paper/accounts                  列表(当前 user)
GET    /api/commodity/paper/accounts/{id}             详情
DELETE /api/commodity/paper/accounts/{id}             注销(软删,保留审计)
POST   /api/commodity/paper/accounts/{id}/reset       重置(回到 initial_capital)
GET    /api/commodity/paper/accounts/{id}/equity      当前净值 + 风险度

# 订单
POST   /api/commodity/paper/orders                    提交订单
GET    /api/commodity/paper/orders                    列表(支持 ?status=&symbol=)
GET    /api/commodity/paper/orders/{id}               详情
DELETE /api/commodity/paper/orders/{id}               撤单(仅 pending)

# 持仓 + 资金
GET    /api/commodity/paper/positions                 当前持仓
GET    /api/commodity/paper/fills                     成交明细(分页)
GET    /api/commodity/paper/snapshots                 净值历史(供图表)

# 联动
POST   /api/commodity/paper/from-decision             ⭐ 接 Phase 3b CIO 输出
```

### 8.1 Feature Flag 注册

```python
# .env(Phase 4 完成后翻 true)
FEATURE_COMMODITY_PAPER=true

# app/main.py(在 FEATURE_COMMODITY_ANALYSIS 注册段之后)
if settings.FEATURE_COMMODITY_PAPER:
    from app.routers.commodity import paper_router
    app.include_router(paper_router, prefix="/api")
    logger.info("✅ 大宗商品模拟交易路由已注册")
```

---

## 九、联动 Phase 3b(`from_decision`)

```python
# app/services/commodity/paper_trading_service.py

async def from_decision(decision_id: str, account_id: str) -> dict:
    """接 Phase 3b CIO 决策 → 自动转模拟订单"""
    decision = await repo.get_decision(decision_id)              # MongoDB 决策存档
    account = await repo.get_account(account_id)
    spec = ContractSpec.from_variety(parse_variety(decision.full_symbol))

    # 1. neutral → 不下单
    if decision.direction == "neutral":
        return {"status": "no_action", "reason": "neutral 决策不下单"}

    # 2. 计算手数(参考 trader 仓位算法)
    if decision.position_sizing.method == "kelly_criterion":
        lots = _calc_lots_kelly(account, decision, spec)
    else:  # fixed / volatility / risk_parity
        lots = _calc_lots_fixed(account, decision.position_sizing.percentage, spec)

    # 3. 限价 = 入场区间中点
    entry_price = (decision.entry_price_range[0] + decision.entry_price_range[1]) / 2

    # 4. 构造订单
    order_req = SubmitOrderRequest(
        full_symbol=decision.full_symbol,
        direction=decision.direction,
        offset="open",
        order_type="limit",
        lots=lots,
        price=entry_price,
        stop_loss=decision.risk_parameters.stop_loss_price,
        take_profit=decision.risk_parameters.take_profit_price,
    )

    # 5. 提交
    order = await submit_order(account_id, order_req)
    order.source = "agent_decision"
    order.decision_id = decision_id
    await repo.save_order(order)
    return {"status": "submitted", "order_id": order.id, "lots": lots}
```

---

## 十、Vue 前端(`PaperTrading.vue`)

### 10.1 布局

```
┌────────────────────────────────────────────────────────────┐
│  账户卡片(顶部 4 列)                                          │
│  ┌──────────┬──────────┬──────────┬──────────┐              │
│  │ 余额     │ 可用     │ 占用保证金 │ 风险度    │              │
│  │ 998,500  │ 850,000  │ 150,000  │ 14.8%    │              │
│  └──────────┴──────────┴──────────┴──────────┘              │
│  净值:1,012,000  实现:+8,500  浮动:+13,500  [重置] [新建账户]│
├────────────────────────────────────────────────────────────┤
│  PnL 折线图(2 个月)│  当前持仓(右)                          │
│  <EquityChart>       │  合约/多空/手数/成本/现价/浮盈/止损止盈│
├────────────────────────────────────────────────────────────┤
│  订单历史(分页)                                              │
│  时间/合约/方向/类型/价格/状态/成交/来源(agent/manual)/[撤单] │
└────────────────────────────────────────────────────────────┘
```

### 10.2 SSE 实时推送

```typescript
// frontend/src/stores/commodity_paper.ts
const eventSource = new EventSource('/api/sse/commodity-paper');
eventSource.addEventListener('paper.order.filled', (e) => {
  const fill = JSON.parse(e.data);
  orders.value.unshift(fill);
  ElNotification.success(`订单成交:${fill.full_symbol} ${fill.direction} ${fill.lots}手 @${fill.price}`);
});
eventSource.addEventListener('paper.risk.alert', (e) => {
  const alert = JSON.parse(e.data);
  ElNotification.error(alert.type === 'margin_call' ? '⚠️ 保证金不足,已触发强平' : '风控告警');
});
```

### 10.3 dataviz skill 复用

PnL 折线图调用 dataviz skill 出设计:
- 双线:净值(主轴)/ 沪深 300 基线(可选,次轴)
- 颜色:涨绿跌红(国内习惯)/ 或中性灰(无方向偏好)
- 交互:hover 显示当日 PnL / 持仓数 / 成交数

---

## 十一、测试矩阵(`tests/test_commodity_paper.py`)

| 类别 | 关键测试 | 数量 |
|---|---|---|
| TestContractSpec | 保证金计算 / 手续费 / 涨跌停预检 / 24 个品种覆盖 | 8 |
| TestAccount | 初始化 / 多账户隔离 / 重置 / 软删 | 6 |
| TestOrderSubmit | 资金足下单 / 资金不足拒单 / 涨跌停拒单 / 撤单仅 pending | 8 |
| TestMatcher | market 立即 / limit 触价 / stop 触发 / 滑点方向 | 6 |
| TestPosition | 加仓平均成本 / 减仓部分平仓 / 反向开仓自动平旧仓 | 6 |
| TestPnL | 浮动盈亏 / 已实现盈亏 / 手续费扣减 / 净值重算 | 8 |
| TestRisk | 止损触发 / 止盈触发 / 风险度 > 100% 强平 | 6 |
| TestPersistence | 4 集合读写 / 索引 / 软删保留 | 6 |
| TestFromDecision | CIO decision → paper order 转换 / neutral 不下单 / 手数换算 | 6 |
| **合计** | | **~60** |

目标:`pytest tests/test_commodity_paper.py --tb=short -q` 全过。

---

## 十二、工作量与依赖

| 子模块 | 工作量 | 依赖 |
|---|---|---|
| `paper/spec.py`(合约规格扩展 + 补 multiplier/margin_rate) | 1 天 | commodity_metadata 已有 |
| `paper/matcher.py` + `paper/pnl.py` + `paper/account.py` | 2 天 | spec |
| `paper/risk.py` + `paper/repo.py` | 2 天 | matcher/pnl |
| `app/routers/commodity/paper_rules.py` + service | 2 天 | paper 全部 |
| `frontend/PaperTrading.vue` + Pinia store + API | 2 天 | 后端完成 |
| 测试 + 调试 | 2 天 | 全部 |
| **总计** | **~11 天(2 周)** | |

依赖:
- commodity_metadata 需要先补 multiplier / margin_rate / commission_rate / limit_up_down 4 个字段
- Phase 3b CIO 输出格式确定后,`from_decision` 才能精确转换

---

## 十三、风险与限制

| 风险 | 影响 | 缓解 |
|---|---|---|
| **合约规格数据过期**(保证金率交易所可能调整) | 强平阈值偏差 | 接入 `get_fees_and_margin` 实时拉,fallback 到静态 |
| **涨跌停预检缺失** | 模拟成交价突破涨跌停 | 必须预检,加单元测试 |
| **T+0 强平复杂度** | 当日开仓当日亏损可能穿仓 | 当日盯市 + 风险度 > 100% 立即强平 |
| **撮合不真实**(实际盘口撮合很复杂) | 与真实成交偏差大 | 文档明确"模拟撮合"性质,不冒充实盘 |
| **多用户并发账户操作** | 数据竞争 | MongoDB `account_id` 索引 + 乐观锁(`updated_at` 校验) |
| **SSE 连接数过多** | 单用户连接泄漏 | 前端组件卸载时 close |

---

## 十四、交付清单(2 周)

| 文件 | 状态 | 备注 |
|---|---|---|
| `tradingagents/dataflows/providers/commodity/commodity_metadata.py` | 🟡 待补 | 加 `multiplier / margin_rate / commission_rate / limit_up_down` 字段 |
| `tradingagents/paper/{__init__,spec,matcher,pnl,account,risk,repo}.py` | 🟡 待写 | 7 文件 |
| `app/models/commodity_paper.py` | 🟡 待写 | 5 ODM |
| `app/routers/commodity/paper_rules.py` | 🟡 待写 | 15 HTTP 端点 |
| `app/services/commodity/paper_trading_service.py` | 🟡 待写 | 业务编排 + from_decision |
| `app/main.py` | 🟡 待改 | 注册 paper_router(flag 控制) |
| `.env` | 🟡 待翻 | `FEATURE_COMMODITY_PAPER=true` |
| `frontend/src/api/commodity.ts` | 🟡 待补 | 15 paper_* 方法 |
| `frontend/src/stores/commodity_paper.ts` | 🟡 待写 | Pinia store |
| `frontend/src/views/Commodity/PaperTrading.vue` | 🟡 待写 | 账户 + 持仓 + 订单 + PnL |
| `frontend/src/router/index.ts` | 🟡 待改 | 加 `/commodity/paper` 路由 |
| `tests/test_commodity_paper.py` | 🟡 待写 | ~60 单测 |
| `docs/progress/screenshots/paper-*.png` | 🟡 待截图 | 实测截图 |
| `docs/progress/phase-4.md`(本文档) | 🟡 完工后追加 | 实际交付 vs 设计差异 |

---

## 十五、Phase 4 之后的路线图(决策辅助)

| 后续 | 主题 | 与 Phase 4 关系 | 周期 |
|---|---|---|---|
| **Phase 5** | 删除期货品种 | 与 Phase 4 独立 | 1-2 周 |
| **Phase 6** ⭐ | 回测框架 | 复用 Phase 4 撮合/PnL/risk,只换 K 线 driver | 2-3 周 |
| **Phase 7** | 实盘接入(谨慎) | 同一接口替换 paper → live broker | 4-6 周 |
| **Phase 8** | 组合管理 | 多账户 / 多策略聚合 | 2-3 周 |
| **Phase 9** | 监控告警 | 复用 risk + 新增飞书/微信通知 | 1-2 周 |

**推荐**:Phase 4 → 5 → 6 一气呵成(5-7 周),把"分析 + 模拟交易 + 回测"这条**完整量化闭环**做完。Phase 7 实盘接入**不建议做**,本项目 CLAUDE.md 已经声明"仅用于研究与教学"。

---

**文档版本**:v1(2026-07-14 起草)
**下次开工第一句话**:"开工 Phase 4:先做 spec.py,把 commodity_metadata 4 个字段补齐"