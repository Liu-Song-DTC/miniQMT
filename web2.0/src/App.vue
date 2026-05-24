<script setup lang="ts">
import { useSystemStore } from './stores/system'
import { useConfigStore } from './stores/config'
import { usePositionsStore } from './stores/positions'
import { useGridStore } from './stores/grid'
import { useSSE } from './composables/useSSE'
import { usePolling } from './composables/usePolling'
import { onMounted, watch, ref } from 'vue'
import * as xqApi from './api/xtquant'

import HeaderBar from './components/HeaderBar.vue'
import SimulationBanner from './components/SimulationBanner.vue'
import ConfigPanel from './components/ConfigPanel.vue'
import BuyPanel from './components/BuyPanel.vue'
import HoldingsTable from './components/HoldingsTable.vue'
import OrderLog from './components/OrderLog.vue'

const system = useSystemStore()
const config = useConfigStore()
const positions = usePositionsStore()
const grid = useGridStore()
const { healthy: sseHealthy, connect: sseConnect } = useSSE()
const { start: startPolling, stop: stopPolling } = usePolling()
const stopProfitEnabled = ref(false)
const stopProfitLoading = ref(false)

async function refreshAll() {
  await Promise.all([positions.fetchPositions(), positions.fetchTrades(), grid.fetchSessions()])
}

async function init() {
  config.fetchConfig()
  await Promise.all([system.fetchStatus(), positions.fetchAll(), grid.fetchAll()])
  system.fetchConnection()
}

function toggleMonitoring() {
  const next = !system.isMonitoring
  system.toggleMonitor(next).then(() => { if (next) startPolling(); else stopPolling() })
}

async function toggleStopProfit() {
  stopProfitLoading.value = true
  const next = !stopProfitEnabled.value
  await xqApi.toggleStopProfit(next)
  stopProfitEnabled.value = next
  stopProfitLoading.value = false
}

async function loadStopProfitStatus() {
  try { const data = await xqApi.getStopProfitStatus(); if (data?.config) stopProfitEnabled.value = data.config.enabled } catch {}
}

onMounted(() => { init(); loadStopProfitStatus(); setTimeout(() => sseConnect(), 1000); startPolling() })

watch(() => system.currentAccountId, () => {
  positions.dataVersion = 0; positions.positions = []; positions.trades = []; grid.sessions = []
  init(); sseConnect()
})
</script>

<template>
  <div class="min-h-screen flex flex-col">
    <HeaderBar />
    <SimulationBanner />

    <main class="flex-1 p-5 space-y-5 max-w-[1600px] mx-auto w-full">
      <!-- Control bar -->
      <div class="flex items-center gap-3 flex-wrap">
        <div class="flex items-center gap-2 bg-white rounded-xl border border-slate-200/80 px-2 py-1.5 shadow-sm">
          <button @click="toggleMonitoring"
            :class="['flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150',
              system.isMonitoring ? 'bg-red-50 text-red-700 hover:bg-red-100' : 'bg-blue-50 text-blue-700 hover:bg-blue-100']">
            <span :class="system.isMonitoring ? 'dot-red' : 'dot-green'"></span>
            {{ system.isMonitoring ? '停止更新' : '开启更新' }}
          </button>
          <button @click="toggleStopProfit" :disabled="stopProfitLoading"
            :class="['flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150',
              stopProfitEnabled ? 'bg-amber-50 text-amber-700 hover:bg-amber-100' : 'bg-emerald-50 text-emerald-700 hover:bg-emerald-100']">
            <span :class="stopProfitEnabled ? 'dot-amber' : 'dot-green'"></span>
            {{ stopProfitLoading ? '...' : stopProfitEnabled ? '止盈止损 ON' : '止盈止损 OFF' }}
          </button>
        </div>

        <div class="flex items-center gap-2 ml-auto text-[11px]">
          <span class="flex items-center gap-1.5 text-slate-500">
            <span :class="['w-6 h-6 rounded-lg flex items-center justify-center text-xs font-bold',
              sseHealthy ? 'bg-emerald-50 text-emerald-600' : 'bg-red-50 text-red-600']">SSE</span>
            {{ sseHealthy ? '实时连接正常' : '实时连接断开' }}
          </span>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div class="lg:col-span-2 space-y-5">
          <ConfigPanel />
          <BuyPanel @refresh="refreshAll" />
          <HoldingsTable @refresh="refreshAll" />
        </div>
        <div class="space-y-5">
          <OrderLog />
        </div>
      </div>
    </main>
  </div>
</template>
