<script setup lang="ts">
import { computed, ref } from 'vue'
import { useGridStore } from '../stores/grid'
import type { GridSession, GridTrade } from '../types'
import { fmtMoney, fmtNumber, fmtPercent, fmtPrice, fmtTime, profitClass } from '../utils/format'

const grid = useGridStore()
const selectedSession = ref<GridSession | null>(null)

const visibleSessions = computed(() =>
  [...grid.sessions].sort((a, b) => {
    const rank: Record<string, number> = { active: 0, stopping: 1, paused: 2, stopped: 3, completed: 4 }
    const ar = rank[a.status] ?? 9
    const br = rank[b.status] ?? 9
    if (ar !== br) return ar - br
    return String(b.start_time || '').localeCompare(String(a.start_time || ''))
  })
)

const selectedTrades = computed<GridTrade[]>(() => {
  if (!selectedSession.value) return []
  return grid.tradesBySession[selectedSession.value.session_id] || []
})

const selectedTradeTotal = computed(() => {
  if (!selectedSession.value) return 0
  return grid.tradeTotalsBySession[selectedSession.value.session_id] ?? selectedTrades.value.length
})

const totalPnl = computed(() =>
  grid.sessions.reduce((sum, s) => sum + Number(s.pnl_snapshot?.total_pnl ?? s.grid_profit ?? 0), 0)
)

function ratioForDisplay(v: number | null | undefined) {
  if (v == null || Number.isNaN(Number(v))) return undefined
  const n = Number(v)
  return Math.abs(n) <= 1 ? n * 100 : n
}

function investmentRatio(session: GridSession) {
  const used = Number(session.current_investment || 0)
  const max = Number(session.max_investment || session.pnl_snapshot?.denominator || 0)
  return max > 0 ? used / max * 100 : undefined
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    active: '运行中',
    stopping: '停止中',
    paused: '已暂停',
    stopped: '已停止',
    completed: '已完成',
  }
  return map[status] || status || '--'
}

function statusClass(status: string) {
  if (status === 'active') return 'badge-green'
  if (status === 'stopping') return 'badge-amber'
  if (status === 'stopped' || status === 'completed') return 'badge-slate'
  return 'badge-blue'
}

function pnlMethod(session: GridSession) {
  const snapshot = session.pnl_snapshot
  if (!snapshot) return '--'
  const map: Record<string, string> = {
    ledger_true_pnl: '真实账本',
    memory_true_pnl: '内存真实盈亏',
    cash_flow_legacy: '兼容降级',
  }
  return `${map[snapshot.method] || snapshot.method}${snapshot.is_degraded ? ' · 降级' : ''}`
}

async function openDetail(session: GridSession) {
  selectedSession.value = session
  await grid.fetchTrades(session.session_id, 20, 0)
}

function closeDetail() {
  selectedSession.value = null
}
</script>

<template>
  <div class="card">
    <div class="card-header">
      <div class="flex items-center gap-2">
        <svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7h16M4 12h16M4 17h16"/></svg>
        <span>网格交易状态</span>
        <span class="badge-blue text-[10px]">{{ grid.sessions.length }} 个会话</span>
        <span v-if="grid.activeSessions.length" class="badge-green text-[10px]">{{ grid.activeSessions.length }} 个运行中</span>
      </div>
      <div class="flex items-center gap-3 text-xs text-slate-400">
        <span>汇总盈亏 <strong :class="['font-mono', profitClass(totalPnl)]">{{ fmtMoney(totalPnl) }}</strong></span>
        <button @click="grid.fetchSessions()" :disabled="grid.loading" class="btn-ghost btn-xs">{{ grid.loading ? '刷新中' : '刷新' }}</button>
      </div>
    </div>

    <div v-if="grid.sessions.length === 0" class="py-12 text-center">
      <svg class="w-10 h-10 text-slate-200 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 17v-6m4 6V7m4 10v-3M5 20h14"/></svg>
      <p class="text-sm font-medium text-slate-400">暂无网格交易会话</p>
      <p class="text-[11px] text-slate-300 mt-1">这里只展示只读状态，不会启动、停止或清空持仓。</p>
    </div>

    <div v-else class="overflow-x-auto">
      <table class="w-full min-w-[980px] text-xs">
        <thead>
          <tr class="bg-slate-50/80 border-b border-slate-200 text-slate-500">
            <th class="px-4 py-2.5 text-left font-semibold">股票</th>
            <th class="px-3 py-2.5 text-left font-semibold">状态</th>
            <th class="px-3 py-2.5 text-right font-semibold">总盈亏</th>
            <th class="px-3 py-2.5 text-right font-semibold">盈亏率</th>
            <th class="px-3 py-2.5 text-right font-semibold">已实现/未实现</th>
            <th class="px-3 py-2.5 text-right font-semibold">资金使用</th>
            <th class="px-3 py-2.5 text-right font-semibold">交易</th>
            <th class="px-3 py-2.5 text-right font-semibold">中心价</th>
            <th class="px-3 py-2.5 text-left font-semibold">口径</th>
            <th class="px-4 py-2.5 text-right font-semibold">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="session in visibleSessions" :key="session.session_id" class="border-b border-slate-100 hover:bg-slate-50/70 transition-colors">
            <td class="px-4 py-2.5">
              <div class="font-mono font-semibold text-slate-700">{{ session.stock_code }}</div>
              <div class="text-[10px] text-slate-400">#{{ session.session_id }}</div>
            </td>
            <td class="px-3 py-2.5">
              <span :class="[statusClass(session.status), '!text-[10px]']">{{ statusLabel(session.status) }}</span>
            </td>
            <td :class="['px-3 py-2.5 text-right font-mono font-semibold', profitClass(Number(session.pnl_snapshot?.total_pnl ?? session.grid_profit ?? 0))]">
              {{ fmtMoney(Number(session.pnl_snapshot?.total_pnl ?? session.grid_profit ?? 0)) }}
            </td>
            <td :class="['px-3 py-2.5 text-right font-mono', profitClass(Number(session.profit_ratio || 0))]">
              {{ fmtPercent(ratioForDisplay(session.pnl_snapshot?.profit_ratio ?? session.profit_ratio)) }}
            </td>
            <td class="px-3 py-2.5 text-right font-mono text-slate-600">
              {{ fmtMoney(session.pnl_snapshot?.realized_pnl || 0) }}
              <span class="text-slate-300">/</span>
              {{ fmtMoney(session.pnl_snapshot?.unrealized_pnl || 0) }}
            </td>
            <td class="px-3 py-2.5 text-right">
              <div class="font-mono text-slate-600">
                {{ fmtMoney(session.current_investment || 0, 0) }}
                <span class="text-slate-300">/</span>
                {{ fmtMoney(session.max_investment || session.pnl_snapshot?.denominator || 0, 0) }}
              </div>
              <div class="text-[10px] text-slate-400">{{ fmtPercent(investmentRatio(session)) }}</div>
            </td>
            <td class="px-3 py-2.5 text-right font-mono text-slate-600">
              {{ session.trade_count || 0 }}次
              <span class="text-slate-300">·</span>
              买{{ session.buy_count || 0 }}/卖{{ session.sell_count || 0 }}
            </td>
            <td class="px-3 py-2.5 text-right font-mono text-slate-600">
              {{ fmtPrice(session.center_price) }}
              <span class="text-slate-300">→</span>
              {{ fmtPrice(session.current_center_price) }}
            </td>
            <td class="px-3 py-2.5">
              <span :class="[session.pnl_snapshot?.is_degraded ? 'badge-amber' : 'badge-blue', '!text-[10px]']">{{ pnlMethod(session) }}</span>
            </td>
            <td class="px-4 py-2.5 text-right">
              <button @click="openDetail(session)" class="btn-outline btn-xs">详情</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <Teleport to="body">
    <div v-if="selectedSession" class="modal-overlay" @click.self="closeDetail">
      <div class="modal-content w-[920px]">
        <div class="px-6 py-4 border-b border-slate-100 flex items-start justify-between">
          <div>
            <h3 class="text-lg font-semibold text-slate-800">网格交易详情</h3>
            <p class="text-xs text-slate-400 mt-0.5 font-mono">
              {{ selectedSession.stock_code }} · {{ statusLabel(selectedSession.status) }} · #{{ selectedSession.session_id }}
            </p>
          </div>
          <button @click="closeDetail" class="w-8 h-8 flex items-center justify-center rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors text-xl">&times;</button>
        </div>

        <div class="p-6 space-y-5">
          <div class="grid grid-cols-4 gap-3">
            <div class="stat-card">
              <div class="stat-label">总盈亏</div>
              <div :class="['stat-value font-mono', profitClass(Number(selectedSession.pnl_snapshot?.total_pnl ?? selectedSession.grid_profit ?? 0))]">
                {{ fmtMoney(Number(selectedSession.pnl_snapshot?.total_pnl ?? selectedSession.grid_profit ?? 0)) }}
              </div>
              <div :class="['text-xs mt-1 font-mono', profitClass(Number(selectedSession.profit_ratio || 0))]">
                {{ fmtPercent(ratioForDisplay(selectedSession.pnl_snapshot?.profit_ratio ?? selectedSession.profit_ratio)) }}
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-label">已实现</div>
              <div :class="['stat-value font-mono', profitClass(Number(selectedSession.pnl_snapshot?.realized_pnl || 0))]">
                {{ fmtMoney(selectedSession.pnl_snapshot?.realized_pnl || 0) }}
              </div>
              <div class="text-xs mt-1 text-slate-400">已配对成交</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">未实现</div>
              <div :class="['stat-value font-mono', profitClass(Number(selectedSession.pnl_snapshot?.unrealized_pnl || 0))]">
                {{ fmtMoney(selectedSession.pnl_snapshot?.unrealized_pnl || 0) }}
              </div>
              <div class="text-xs mt-1 text-slate-400">未平网格 {{ fmtNumber(selectedSession.pnl_snapshot?.open_volume || 0) }} 股</div>
            </div>
            <div class="stat-card">
              <div class="stat-label">资金使用</div>
              <div class="stat-value font-mono text-slate-800">
                {{ fmtMoney(selectedSession.current_investment || 0, 0) }}
              </div>
              <div class="text-xs mt-1 text-slate-400">
                上限 {{ fmtMoney(selectedSession.max_investment || selectedSession.pnl_snapshot?.denominator || 0, 0) }}
              </div>
            </div>
          </div>

          <div class="grid grid-cols-3 gap-3">
            <div class="rounded-lg border border-slate-200 p-3">
              <div class="text-[11px] font-medium text-slate-400">交易统计</div>
              <div class="mt-2 text-sm font-medium text-slate-700">{{ selectedSession.trade_count || 0 }}次（买{{ selectedSession.buy_count || 0 }}/卖{{ selectedSession.sell_count || 0 }}）</div>
            </div>
            <div class="rounded-lg border border-slate-200 p-3">
              <div class="text-[11px] font-medium text-slate-400">中心价</div>
              <div class="mt-2 text-sm font-mono text-slate-700">{{ fmtPrice(selectedSession.center_price) }} → {{ fmtPrice(selectedSession.current_center_price) }}</div>
            </div>
            <div class="rounded-lg border border-slate-200 p-3">
              <div class="text-[11px] font-medium text-slate-400">计算口径</div>
              <div class="mt-2"><span :class="[selectedSession.pnl_snapshot?.is_degraded ? 'badge-amber' : 'badge-blue']">{{ pnlMethod(selectedSession) }}</span></div>
            </div>
          </div>

          <div>
            <div class="flex items-center justify-between mb-2">
              <h4 class="text-sm font-semibold text-slate-700">最近网格交易</h4>
              <span class="text-[11px] text-slate-400">共 {{ selectedTradeTotal }} 条，显示 {{ selectedTrades.length }} 条</span>
            </div>
            <div class="overflow-x-auto rounded-lg border border-slate-200">
              <table class="w-full min-w-[760px] text-xs">
                <thead>
                  <tr class="bg-slate-50 text-slate-500 border-b border-slate-200">
                    <th class="px-3 py-2 text-left font-semibold">时间</th>
                    <th class="px-3 py-2 text-left font-semibold">方向</th>
                    <th class="px-3 py-2 text-right font-semibold">触发价</th>
                    <th class="px-3 py-2 text-right font-semibold">数量</th>
                    <th class="px-3 py-2 text-right font-semibold">金额</th>
                    <th class="px-3 py-2 text-right font-semibold">档位</th>
                    <th class="px-3 py-2 text-left font-semibold">委托/成交ID</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-if="grid.tradesLoading">
                    <td colspan="7" class="px-3 py-8 text-center text-slate-400">正在加载交易流水...</td>
                  </tr>
                  <tr v-else-if="selectedTrades.length === 0">
                    <td colspan="7" class="px-3 py-8 text-center text-slate-400">暂无网格交易记录</td>
                  </tr>
                  <tr v-for="trade in selectedTrades" :key="trade.trade_id || `${trade.session_id}-${trade.trade_time}`" class="border-b border-slate-100 hover:bg-slate-50/70">
                    <td class="px-3 py-2 font-mono text-slate-500">{{ fmtTime(trade.trade_time) }}</td>
                    <td class="px-3 py-2">
                      <span :class="['inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold ring-1',
                        String(trade.trade_type).toUpperCase() === 'BUY' ? 'bg-red-50 text-red-600 ring-red-200' : 'bg-emerald-50 text-emerald-600 ring-emerald-200']">
                        {{ String(trade.trade_type).toUpperCase() === 'BUY' ? '买入' : String(trade.trade_type).toUpperCase() === 'SELL' ? '卖出' : trade.trade_type }}
                      </span>
                    </td>
                    <td class="px-3 py-2 text-right font-mono text-slate-600">{{ fmtPrice(trade.trigger_price || 0) }}</td>
                    <td class="px-3 py-2 text-right font-mono text-slate-600">{{ fmtNumber(trade.volume || 0) }}</td>
                    <td class="px-3 py-2 text-right font-mono text-slate-600">{{ fmtMoney(trade.amount || 0) }}</td>
                    <td class="px-3 py-2 text-right font-mono text-slate-600">{{ fmtPrice(trade.grid_level || 0) }}</td>
                    <td class="px-3 py-2 font-mono text-slate-500">{{ trade.trade_id || '--' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
            说明：本面板为只读展示。停止网格策略只停止自动网格交易与撤销未完成网格委托，不会清空当前股票持仓。
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
