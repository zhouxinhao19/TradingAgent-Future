<template>
  <div class="paper-trading">
    <div class="header">
      <div class="title">
        <el-icon style="margin-right:8px"><CreditCard /></el-icon>
        <span>模拟交易</span>
      </div>
      <div class="actions">
        <el-button :icon="Refresh" text size="small" @click="refreshAll">刷新</el-button>
        <el-button type="primary" :icon="Plus" @click="openOrderDialog">下市场单</el-button>
        <el-button type="danger" plain :icon="Delete" @click="confirmReset">重置账户</el-button>
      </div>
    </div>

    <el-row :gutter="16" class="body">
      <el-col :span="8">
        <el-card shadow="hover" class="account-card">
          <template #header><div class="card-hd">账户信息</div></template>
          <el-descriptions :column="1" border v-if="account">
            <el-descriptions-item label="现金">{{ fmtAmount(account.cash) }}</el-descriptions-item>
            <el-descriptions-item label="持仓市值">{{ fmtAmount(account.positions_value) }}</el-descriptions-item>
            <el-descriptions-item label="总权益">{{ fmtAmount(account.equity) }}</el-descriptions-item>
            <el-descriptions-item label="已实现盈亏">{{ fmtAmount(account.realized_pnl) }}</el-descriptions-item>
            <el-descriptions-item label="更新时间">{{ account.updated_at || '-' }}</el-descriptions-item>
          </el-descriptions>
          <el-empty v-else description="暂无账户数据" />
        </el-card>
      </el-col>

      <el-col :span="16">
        <el-card shadow="hover" class="positions-card">
          <template #header><div class="card-hd">持仓</div></template>
          <el-table :data="positions" size="small" v-loading="loading.positions">
            <el-table-column prop="code" label="代码" width="120" />
            <el-table-column prop="quantity" label="数量" width="120" />
            <el-table-column prop="avg_cost" label="均价" width="120">
              <template #default="{ row }">{{ fmtPrice(row.avg_cost) }}</template>
            </el-table-column>
            <el-table-column prop="last_price" label="最新价" width="120">
              <template #default="{ row }">{{ fmtPrice(row.last_price) }}</template>
            </el-table-column>
            <el-table-column label="浮盈" width="120">
              <template #default="{ row }">{{ fmtAmount((Number(row.last_price || 0) - Number(row.avg_cost || 0)) * Number(row.quantity || 0)) }}</template>
            </el-table-column>
          </el-table>
        </el-card>

        <el-card shadow="hover" class="orders-card" style="margin-top:16px">
          <template #header><div class="card-hd">订单记录</div></template>
          <el-table :data="orders" size="small" v-loading="loading.orders">
            <el-table-column prop="created_at" label="时间" width="180" />
            <el-table-column prop="side" label="方向" width="100" />
            <el-table-column prop="code" label="代码" width="120" />
            <el-table-column prop="price" label="成交价" width="120">
              <template #default="{ row }">{{ fmtPrice(row.price) }}</template>
            </el-table-column>
            <el-table-column prop="quantity" label="数量" width="100" />
            <el-table-column prop="status" label="状态" width="100" />
            <!-- 新增：关联分析 -->
            <el-table-column label="分析" width="120">
              <template #default="{ row }">
                <el-tag v-if="row.analysis_id" size="small" type="success" style="cursor:pointer" @click="goAnalysis(row.analysis_id)">关联分析</el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="orderDialog" title="下市场单" width="480px">
      <!-- 分析上下文提示 -->
      <div v-if="(order as any).analysis_id" class="analysis-context" style="margin-bottom:12px">
        <el-alert :closable="false" type="info" show-icon>
          <template #title>
            来自分析：<span style="font-family:monospace">{{ (order as any).analysis_id }}</span>
            <el-button link size="small" type="primary" style="margin-left:8px" @click="goAnalysis((order as any).analysis_id)">查看分析</el-button>
          </template>
          <div v-if="analysisLoading" style="color:#666">正在加载分析摘要…</div>
          <div v-else-if="analysisContext">
            <div style="font-size:12px;color:#666">
              <span>标的：{{ analysisContext.stock_symbol || '-' }}</span>
              <span style="margin-left:8px">模型建议：{{ analysisContext.recommendation || '-' }}</span>
            </div>
          </div>
        </el-alert>
      </div>

      <el-form label-width="90px">
        <el-form-item label="方向">
          <el-radio-group v-model="order.side">
            <el-radio-button label="buy">买入</el-radio-button>
            <el-radio-button label="sell">卖出</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="代码">
          <el-input v-model="order.code" placeholder="如 600519 或 000001" />
        </el-form-item>
        <el-form-item label="数量">
          <el-input-number v-model="order.qty" :min="1" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="orderDialog=false">取消</el-button>
        <el-button type="primary" @click="submitOrder">提交</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { CreditCard, Refresh, Plus, Delete } from '@element-plus/icons-vue'
import { paperApi } from '@/api/paper'
import { analysisApi } from '@/api/analysis'

// 路由与初始化
const route = useRoute()
const router = useRouter()

// 数据
const account = ref<any | null>(null)
const positions = ref<any[]>([])
const orders = ref<any[]>([])
const loading = ref({ account: false, positions: false, orders: false })

const orderDialog = ref(false)
const order = ref({ side: 'buy', code: '', qty: 100 })

// 分析上下文
const analysisContext = ref<any | null>(null)
const analysisLoading = ref(false)

// 方法
function fmtPrice(n: number | null | undefined) {
  if (n == null || Number.isNaN(n as any)) return '-'
  return Number(n).toFixed(2)
}
function fmtAmount(n: number | null | undefined) {
  if (n == null || Number.isNaN(n as any)) return '-'
  return Number(n).toFixed(2)
}

async function fetchAccount() {
  try {
    loading.value.account = true
    const res = await paperApi.getAccount()
    if (res.success) {
      account.value = res.data.account
      // 可选：也可从account接口带回的positions中填充
      // positions.value = res.data.positions || positions.value
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '获取账户失败')
  } finally {
    loading.value.account = false
  }
}

async function fetchPositions() {
  try {
    loading.value.positions = true
    const res = await paperApi.getPositions()
    if (res.success) {
      positions.value = res.data.items || []
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '获取持仓失败')
  } finally {
    loading.value.positions = false
  }
}

async function fetchOrders() {
  try {
    loading.value.orders = true
    const res = await paperApi.getOrders(50)
    if (res.success) {
      orders.value = res.data.items || []
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '获取订单失败')
  } finally {
    loading.value.orders = false
  }
}

function openOrderDialog() {
  orderDialog.value = true
}

async function submitOrder() {
  try {
    const payload: any = { side: order.value.side as 'buy' | 'sell', code: order.value.code, quantity: Number(order.value.qty) }
    if ((order.value as any).analysis_id) payload.analysis_id = (order.value as any).analysis_id
    const res = await paperApi.placeOrder(payload)
    if (res.success) {
      ElMessage.success('下单成功')
      orderDialog.value = false
      await refreshAll()
    } else {
      ElMessage.error(res.message || '下单失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '下单失败')
  }
}

async function confirmReset() {
  try {
    await ElMessageBox.confirm('将清空所有订单与持仓，并重置账户为初始现金，确认重置？', '重置账户', { type: 'warning' })
    const res = await paperApi.resetAccount()
    if (res.success) {
      ElMessage.success('账户已重置')
      await refreshAll()
    }
  } catch (e) {
    // 取消或失败
  }
}

async function refreshAll() {
  await Promise.all([fetchAccount(), fetchPositions(), fetchOrders()])
}

function goAnalysis(analysisId: string) {
  if (!analysisId) return
  router.push({ name: 'SingleAnalysis', query: { analysis_id: analysisId } })
}

async function fetchAnalysisContext(analysisId: string) {
  try {
    analysisLoading.value = true
    analysisContext.value = null
    const res = await analysisApi.getResult(analysisId)
    analysisContext.value = res as any
  } catch (e) {
    // 忽略错误，仅用于展示
  } finally {
    analysisLoading.value = false
  }
}

onMounted(() => {
  let hasPrefill = false
  const qCode = String(route.query.code || '').trim()
  if (qCode) {
    order.value.code = qCode
    hasPrefill = true
  }
  const qSide = String(route.query.side || '').trim().toLowerCase()
  if (qSide === 'buy' || qSide === 'sell') {
    order.value.side = qSide as 'buy' | 'sell'
    hasPrefill = true
  }
  const qQty = Number(route.query.qty || route.query.quantity || 0)
  if (!Number.isNaN(qQty) && qQty > 0) {
    order.value.qty = Math.round(qQty)
    hasPrefill = true
  }
  // 可选：后续用于下单时带上分析ID
  const qAnalysisId = String(route.query.analysis_id || '').trim()
  if (qAnalysisId) {
    // 暂存于本地，等待提交订单时附带
    ;(order as any).analysis_id = qAnalysisId
    fetchAnalysisContext(qAnalysisId)
    hasPrefill = true
  }
  if (hasPrefill) {
    orderDialog.value = true
  }
  refreshAll()
})
</script>

<style scoped>
.paper-trading { padding: 16px; }
.header { display:flex; align-items:center; justify-content:space-between; margin-bottom: 12px; }
.title { display:flex; align-items:center; font-weight: 600; font-size: 16px; }
.card-hd { font-weight: 600; }
</style>