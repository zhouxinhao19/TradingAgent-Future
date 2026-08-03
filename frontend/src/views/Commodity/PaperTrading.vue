<template>
  <div class="commodity-paper-trading">
    <!-- 顶部操作栏 -->
    <div class="header">
      <div class="title">
        <el-icon style="margin-right:8px"><Coin /></el-icon>
        <span>期货模拟交易</span>
      </div>
      <div class="header-actions">
        <el-button :icon="Refresh" text size="small" @click="refreshAll" :loading="loading('snapshot')">
          刷新
        </el-button>
        <el-button type="primary" :icon="Plus" @click="showCreateAccount = true" v-if="!hasAccounts">
          创建账户
        </el-button>
        <el-button type="success" :icon="Plus" @click="openOrderDialog" v-if="hasAccounts">
          下单
        </el-button>
        <el-button type="danger" plain :icon="Delete" @click="confirmReset" v-if="hasAccounts">
          重置
        </el-button>
      </div>
    </div>

    <!-- 创建账户对话框 -->
    <el-dialog v-model="showCreateAccount" title="创建模拟账户" width="420px">
      <el-form label-width="100px">
        <el-form-item label="账户名称">
          <el-input v-model="newAccountName" placeholder="默认账户" />
        </el-form-item>
        <el-form-item label="初始资金">
          <el-input-number v-model="newAccountCapital" :min="10000" :step="100000" :precision="0" />
          <span style="margin-left:8px;color:#909399">元</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateAccount = false">取消</el-button>
        <el-button type="primary" @click="handleCreateAccount" :loading="loading('createAccount')">
          创建
        </el-button>
      </template>
    </el-dialog>

    <!-- 无账户提示 -->
    <el-empty v-if="!hasAccounts && !loading('accounts')" description="暂无模拟账户">
      <el-button type="primary" @click="showCreateAccount = true">创建模拟账户</el-button>
    </el-empty>

    <!-- 账户信息 + 下单面板 -->
    <template v-if="hasAccounts">
      <el-row :gutter="16" class="body">
        <!-- 左侧:账户信息 -->
        <el-col :span="7">
          <!-- 账户选择器 -->
          <el-select v-model="activeAccountId" style="width:100%;margin-bottom:12px" @change="refreshAll">
            <el-option
              v-for="a in accounts" :key="a.account_id"
              :label="a.name" :value="a.account_id"
            >
              <span>{{ a.name }}</span>
              <span style="float:right;color:#909399;font-size:12px">
                ¥{{ fmtAmount(a.equity) }}
              </span>
            </el-option>
          </el-select>

          <!-- 账户概览卡片 -->
          <el-card shadow="hover">
            <template #header><div class="card-hd">账户概览</div></template>
            <div v-if="account">
              <el-descriptions :column="1" border size="small">
                <el-descriptions-item label="总资产">
                  <span style="font-weight:600;font-size:16px">¥{{ fmtAmount(account.equity) }}</span>
                </el-descriptions-item>
                <el-descriptions-item label="可用资金">¥{{ fmtAmount(account.available) }}</el-descriptions-item>
                <el-descriptions-item label="占用保证金">¥{{ fmtAmount(account.margin_used) }}</el-descriptions-item>
                <el-descriptions-item label="冻结资金">¥{{ fmtAmount(account.frozen) }}</el-descriptions-item>
                <el-descriptions-item label="浮动盈亏">
                  <span :style="{ color: account.unrealized_pnl >= 0 ? '#67C23A' : '#F56C6C' }">
                    ¥{{ fmtAmount(account.unrealized_pnl) }}
                  </span>
                </el-descriptions-item>
                <el-descriptions-item label="已实现盈亏">
                  <span :style="{ color: account.realized_pnl >= 0 ? '#67C23A' : '#F56C6C' }">
                    ¥{{ fmtAmount(account.realized_pnl) }}
                  </span>
                </el-descriptions-item>
                <el-descriptions-item label="风险度">
                  <el-progress
                    :percentage="Math.min(riskPercent, 100)"
                    :status="riskPercent > 80 ? 'exception' : riskPercent > 50 ? 'warning' : 'success'"
                    :stroke-width="14"
                  >
                    <span style="font-size:12px">{{ (account.risk_ratio * 100).toFixed(1) }}%</span>
                  </el-progress>
                </el-descriptions-item>
              </el-descriptions>
            </div>
            <el-skeleton :rows="6" animated v-else />
          </el-card>

          <!-- 合约规格 -->
          <el-card shadow="hover" style="margin-top:12px" v-if="positions.length > 0">
            <template #header><div class="card-hd">持仓汇总</div></template>
            <div v-for="pos in positions" :key="pos.id" class="pos-summary-item">
              <div class="pos-symbol">
                <el-tag size="small" :type="pos.direction === 'long' ? 'danger' : 'success'" effect="plain">
                  {{ pos.direction === 'long' ? '多' : '空' }}
                </el-tag>
                <span style="margin-left:6px;font-weight:500">{{ pos.full_symbol }}</span>
              </div>
              <div class="pos-detail">
                <span>{{ pos.lots }} 手</span>
                <span>均价 {{ fmtPrice(pos.avg_cost) }}</span>
                <span :style="{ color: pos.floating_pnl >= 0 ? '#67C23A' : '#F56C6C' }">
                  {{ pos.floating_pnl >= 0 ? '+' : '' }}{{ fmtAmount(pos.floating_pnl) }}
                </span>
              </div>
            </div>
          </el-card>
        </el-col>

        <!-- 右侧:持仓 + 订单 + 成交 -->
        <el-col :span="17">
          <el-tabs v-model="activeTab">
            <!-- 持仓 Tab -->
            <el-tab-pane label="持仓" name="positions">
              <el-table :data="positions" size="small" v-loading="loading('snapshot')" stripe>
                <el-table-column label="合约" width="140">
                  <template #default="{ row }">{{ row.full_symbol }}</template>
                </el-table-column>
                <el-table-column label="方向" width="80">
                  <template #default="{ row }">
                    <el-tag :type="row.direction === 'long' ? 'danger' : 'success'" size="small">
                      {{ row.direction === 'long' ? '做多' : '做空' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="手数" width="70" prop="lots" />
                <el-table-column label="均价" width="110">
                  <template #default="{ row }">¥{{ fmtPrice(row.avg_cost) }}</template>
                </el-table-column>
                <el-table-column label="最新价" width="110">
                  <template #default="{ row }">¥{{ fmtPrice(row.current_price) }}</template>
                </el-table-column>
                <el-table-column label="浮盈" width="120">
                  <template #default="{ row }">
                    <span :style="{ color: row.floating_pnl >= 0 ? '#67C23A' : '#F56C6C' }">
                      ¥{{ fmtAmount(row.floating_pnl) }}
                    </span>
                  </template>
                </el-table-column>
                <el-table-column label="保证金" width="120">
                  <template #default="{ row }">¥{{ fmtAmount(row.margin_used) }}</template>
                </el-table-column>
                <el-table-column label="操作" width="160" fixed="right">
                  <template #default="{ row }">
                    <el-button size="small" type="primary" link @click="quickClose(row)">
                      {{ row.direction === 'long' ? '平多' : '平空' }}
                    </el-button>
                    <el-button size="small" type="success" link @click="goAnalysis(row.full_symbol)">分析</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-if="positions.length === 0" description="暂无持仓" />
            </el-tab-pane>

            <!-- 订单 Tab -->
            <el-tab-pane label="订单" name="orders">
              <div style="margin-bottom:8px">
                <el-radio-group v-model="orderFilter" size="small" @change="loadOrders">
                  <el-radio-button label="all">全部</el-radio-button>
                  <el-radio-button label="pending">待成交</el-radio-button>
                  <el-radio-button label="filled">已成交</el-radio-button>
                  <el-radio-button label="cancelled">已撤单</el-radio-button>
                </el-radio-group>
              </div>
              <el-table :data="orders" size="small" v-loading="loading('orders')" stripe>
                <el-table-column label="合约" width="140">
                  <template #default="{ row }">{{ row.full_symbol }}</template>
                </el-table-column>
                <el-table-column label="方向" width="70">
                  <template #default="{ row }">
                    <el-tag :type="row.direction === 'long' ? 'danger' : 'success'" size="small">
                      {{ row.direction === 'long' ? '多' : '空' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="类型" width="80">
                  <template #default="{ row }">
                    {{ orderTypeLabel(row.order_type) }}
                  </template>
                </el-table-column>
                <el-table-column label="手数" width="60" prop="lots" />
                <el-table-column label="价格" width="100">
                  <template #default="{ row }">{{ row.price ? '¥' + fmtPrice(row.price) : '市价' }}</template>
                </el-table-column>
                <el-table-column label="状态" width="90">
                  <template #default="{ row }">
                    <el-tag :type="orderStatusType(row.status)" size="small">
                      {{ orderStatusLabel(row.status) }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="已成交" width="80">
                  <template #default="{ row }">{{ row.filled_lots }}/{{ row.lots }}</template>
                </el-table-column>
                <el-table-column label="时间" width="160">
                  <template #default="{ row }">{{ formatDateTime(row.created_at) }}</template>
                </el-table-column>
                <el-table-column label="操作" width="100" fixed="right">
                  <template #default="{ row }">
                    <el-button
                      v-if="row.status === 'pending'"
                      size="small" type="danger" link
                      @click="cancelOrder(row.id)"
                    >撤单</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-if="orders.length === 0" description="暂无订单" />
            </el-tab-pane>

            <!-- 成交 Tab -->
            <el-tab-pane label="成交" name="fills">
              <el-table :data="fills" size="small" v-loading="loading('fills')" stripe>
                <el-table-column label="合约" width="140">
                  <template #default="{ row }">{{ row.full_symbol }}</template>
                </el-table-column>
                <el-table-column label="方向" width="70">
                  <template #default="{ row }">
                    <el-tag :type="row.direction === 'long' ? 'danger' : 'success'" size="small">
                      {{ row.direction === 'long' ? '多' : '空' }}
                    </el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="开/平" width="70">
                  <template #default="{ row }">{{ row.offset === 'open' ? '开仓' : '平仓' }}</template>
                </el-table-column>
                <el-table-column label="手数" width="60" prop="lots" />
                <el-table-column label="成交价" width="110">
                  <template #default="{ row }">¥{{ fmtPrice(row.price) }}</template>
                </el-table-column>
                <el-table-column label="手续费" width="100">
                  <template #default="{ row }">¥{{ fmtAmount(row.commission) }}</template>
                </el-table-column>
                <el-table-column label="滑点" width="80">
                  <template #default="{ row }">¥{{ fmtAmount(row.slippage) }}</template>
                </el-table-column>
                <el-table-column label="时间" width="160">
                  <template #default="{ row }">{{ formatDateTime(row.matched_at) }}</template>
                </el-table-column>
              </el-table>
              <el-empty v-if="fills.length === 0" description="暂无成交记录" />
            </el-tab-pane>
          </el-tabs>
        </el-col>
      </el-row>

      <!-- 下单对话框 -->
      <el-dialog v-model="orderDialog" title="下单" width="500px">
        <el-form label-width="90px">
          <el-form-item label="合约代码">
            <el-input v-model="order.full_symbol" placeholder="如 CU2501.SHF" />
          </el-form-item>
          <el-form-item label="方向">
            <el-radio-group v-model="order.direction">
              <el-radio-button label="long">做多</el-radio-button>
              <el-radio-button label="short">做空</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="类型">
            <el-radio-group v-model="order.order_type">
              <el-radio-button label="market">市价</el-radio-button>
              <el-radio-button label="limit">限价</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="开/平">
            <el-radio-group v-model="order.offset">
              <el-radio-button label="open">开仓</el-radio-button>
              <el-radio-button label="close">平仓</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item label="手数">
            <el-input-number v-model="order.lots" :min="1" :max="100" />
          </el-form-item>
          <el-form-item label="价格" v-if="order.order_type === 'limit'">
            <el-input-number v-model="order.price" :min="0.01" :step="10" :precision="2" />
          </el-form-item>
          <el-form-item label="止损价">
            <el-input-number v-model="order.stop_loss" :min="0" :step="10" :precision="2" placeholder="可选" />
          </el-form-item>
          <el-form-item label="止盈价">
            <el-input-number v-model="order.take_profit" :min="0" :step="10" :precision="2" placeholder="可选" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="orderDialog = false">取消</el-button>
          <el-button type="primary" @click="handleSubmitOrder" :loading="loading('submitOrder')">
            提交
          </el-button>
        </template>
      </el-dialog>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Coin, Refresh, Plus, Delete } from '@element-plus/icons-vue'
import { useCommodityPaperStore } from '@/stores/commodity_paper'
import { formatDateTime as formatDateTimeUtil } from '@/utils/datetime'

const route = useRoute()
const router = useRouter()
const store = useCommodityPaperStore()

// ---- 计算属性 ----
const accounts = computed(() => store.accounts)
const activeAccountId = computed({
  get: () => store.activeAccountId,
  set: (v: string) => { store.activeAccountId = v },
})
const account = computed(() => store.account)
const positions = computed(() => store.positions)
const orders = computed(() => store.orders)
const fills = computed(() => store.fills)
const hasAccounts = computed(() => store.hasAccounts)

const loading = (key: string) => store.loading(key)

// 风险度百分比(用于进度条)
const riskPercent = computed(() => {
  if (!account.value) return 0
  return Math.round((account.value.risk_ratio || 0) * 100)
})

// ---- 本地状态 ----
const showCreateAccount = ref(false)
const newAccountName = ref('期货账户')
const newAccountCapital = ref(1_000_000)
const orderDialog = ref(false)
const activeTab = ref('positions')
const orderFilter = ref('all')

const order = ref({
  full_symbol: '',
  direction: 'long' as 'long' | 'short',
  order_type: 'market' as 'market' | 'limit',
  offset: 'open' as 'open' | 'close',
  lots: 1,
  price: undefined as number | undefined,
  stop_loss: undefined as number | undefined,
  take_profit: undefined as number | undefined,
})

// ---- 格式化 ----
function fmtPrice(n: number | null | undefined) {
  if (n == null || Number.isNaN(Number(n))) return '-'
  return Number(n).toFixed(2)
}
function fmtAmount(n: number | null | undefined) {
  if (n == null || Number.isNaN(Number(n))) return '-'
  return Number(n).toFixed(2)
}
function formatDateTime(dt: string | undefined | null) {
  if (!dt) return '-'
  return formatDateTimeUtil(dt)
}
function orderTypeLabel(t: string) {
  const map: Record<string, string> = { market: '市价', limit: '限价', stop: '止损', stop_limit: '止损限价' }
  return map[t] || t
}
function orderStatusLabel(s: string) {
  const map: Record<string, string> = { pending: '待成交', filled: '已成交', partial: '部分成交', cancelled: '已撤单', rejected: '已拒单' }
  return map[s] || s
}
function orderStatusType(s: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = { pending: 'warning', filled: 'success', partial: 'primary', cancelled: 'info', rejected: 'danger' }
  return map[s] || 'info'
}

// ---- 动作 ----
async function handleCreateAccount() {
  const ok = await store.createAccount(newAccountName.value, newAccountCapital.value)
  if (ok) {
    ElMessage.success('账户创建成功')
    showCreateAccount.value = false
    await store.refreshAll()
  } else {
    ElMessage.error('创建账户失败')
  }
}

function openOrderDialog() {
  order.value = {
    full_symbol: '',
    direction: 'long',
    order_type: 'market',
    offset: 'open',
    lots: 1,
    price: undefined,
    stop_loss: undefined,
    take_profit: undefined,
  }
  // 从路由参数预填
  const qSymbol = String(route.query.symbol || '').trim()
  if (qSymbol) order.value.full_symbol = qSymbol
  const qDirection = String(route.query.direction || '').trim().toLowerCase()
  if (qDirection === 'long' || qDirection === 'short') order.value.direction = qDirection
  orderDialog.value = true
}

async function handleSubmitOrder() {
  const result = await store.submitOrder({ ...order.value })
  if (result?.status === 'accepted') {
    ElMessage.success('下单成功')
    orderDialog.value = false
  } else {
    ElMessage.error(result?.reject_reason || '下单失败')
  }
}

async function confirmReset() {
  try {
    await ElMessageBox.confirm(
      '重置将清空所有持仓、订单和成交记录，账户恢复初始资金。确认重置？',
      '重置账户',
      { type: 'warning' },
    )
    await store.resetAccount()
    ElMessage.success('账户已重置')
  } catch {
    // 取消
  }
}

async function cancelOrder(orderId: string) {
  try {
    await store.cancelOrder(orderId)
    ElMessage.success('撤单成功')
  } catch (e: any) {
    ElMessage.error(e?.message || '撤单失败')
  }
}

function quickClose(pos: any) {
  order.value = {
    full_symbol: pos.full_symbol,
    direction: pos.direction === 'long' ? 'short' : 'long',
    order_type: 'market',
    offset: 'close',
    lots: pos.lots,
    price: undefined,
    stop_loss: undefined,
    take_profit: undefined,
  }
  orderDialog.value = true
}

function goAnalysis(symbol: string) {
  router.push({ name: 'CommodityAnalysis', query: { symbol } })
}

function loadOrders() {
  const params: any = { limit: 50 }
  if (orderFilter.value !== 'all') params.status = orderFilter.value
  store.loadOrders(params)
}

async function refreshAll() {
  await store.refreshAll()
}

// ---- 初始化 ----
onMounted(async () => {
  await store.loadAccounts()
  if (store.hasAccounts) {
    // 路由参数优先
    const qAccount = String(route.query.account_id || '').trim()
    if (qAccount) store.activeAccountId = qAccount
    await store.refreshAll()
  }
})
</script>

<style scoped>
.commodity-paper-trading { padding: 16px; }
.header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.title { display: flex; align-items: center; font-weight: 600; font-size: 16px; }
.header-actions { display: flex; gap: 8px; }
.card-hd { font-weight: 600; }
.pos-summary-item {
  padding: 8px 0;
  border-bottom: 1px solid #f0f0f0;
}
.pos-summary-item:last-child { border-bottom: none; }
.pos-symbol { margin-bottom: 4px; }
.pos-detail {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  color: #606266;
}
</style>
