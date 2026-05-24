import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Position, PositionMetrics, TradeRecord } from '../types'
import * as flaskApi from '../api/flask'

export const usePositionsStore = defineStore('positions', () => {
  const positions = ref<Position[]>([])
  const metrics = ref<PositionMetrics>({ total_market_value: 0, total_profit: 0, total_profit_ratio: 0, position_count: 0, stock_count: 0 })
  const trades = ref<TradeRecord[]>([])
  const dataVersion = ref(0)
  const loading = ref(false)

  const hasPositions = computed(() => positions.value.length > 0)
  const totalMarketValue = computed(() => metrics.value.total_market_value)
  const selectedStocks = ref<Set<string>>(new Set())

  async function fetchPositions() {
    const r = await flaskApi.getPositions(dataVersion.value)
    if (!r || r.noChange) return
    positions.value = r.positionsAll
    metrics.value = r.metrics
    dataVersion.value = r.version
  }

  async function fetchTrades() {
    trades.value = await flaskApi.getTradeRecords()
  }

  async function fetchAll() {
    loading.value = true
    await Promise.all([fetchPositions(), fetchTrades()])
    loading.value = false
  }

  function toggleSelect(stockCode: string, selected: boolean) {
    const s = new Set(selectedStocks.value)
    if (selected) s.add(stockCode); else s.delete(stockCode)
    selectedStocks.value = s
  }

  function selectAll(codes: string[]) {
    selectedStocks.value = new Set(codes)
  }

  function deselectAll() {
    selectedStocks.value = new Set()
  }

  return {
    positions, metrics, trades, dataVersion, loading, selectedStocks,
    hasPositions, totalMarketValue,
    fetchPositions, fetchTrades, fetchAll,
    toggleSelect, selectAll, deselectAll,
  }
})
