import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { ConfigData, ParamRange } from '../types'
import * as flaskApi from '../api/flask'

const DEFAULTS: ConfigData = {
  singleBuyAmount: 35000,
  firstProfitSell: 5.0,
  firstProfitSellEnabled: true,
  stockGainSellPencent: 60.0,
  firstProfitSellPencent: true,
  allowBuy: true,
  allowSell: true,
  stopLossBuy: 5.0,
  stopLossBuyEnabled: true,
  stockStopLoss: 7.0,
  StopLossEnabled: true,
  singleStockMaxPosition: 70000,
  totalMaxPosition: 400000,
  globalAllowBuySell: true,
  globalAllowGridTrading: true,
  simulationMode: false,
}

export const useConfigStore = defineStore('config', () => {
  const config = ref<ConfigData>({ ...DEFAULTS })
  const ranges = ref<Record<string, ParamRange>>({})
  const loading = ref(false)
  const saving = ref(false)

  const configData = computed(() => config.value)

  async function fetchConfig() {
    loading.value = true
    const r = await flaskApi.getConfig()
    if (r) {
      config.value = { ...DEFAULTS, ...r.data }
      ranges.value = r.ranges
    }
    loading.value = false
  }

  async function saveConfig(fields?: Partial<ConfigData>) {
    saving.value = true
    const ok = await flaskApi.saveConfig(fields || config.value)
    saving.value = false
    return ok
  }

  function updateField<K extends keyof ConfigData>(key: K, value: ConfigData[K]) {
    (config.value as any)[key] = value
  }

  function getRange(key: string): ParamRange {
    return ranges.value[key] || { min: 0, max: 999999999 }
  }

  return { config, ranges, loading, saving, configData, fetchConfig, saveConfig, updateField, getRange }
})
