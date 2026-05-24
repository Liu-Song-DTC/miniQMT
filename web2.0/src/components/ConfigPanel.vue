<script setup lang="ts">
import { useConfigStore } from '../stores/config'

const store = useConfigStore()

const FIELDS = [
  { label: '单次买入金额', key: 'singleBuyAmount', suffix: '元', step: 1, decimals: 0 },
  { label: '单股最大持仓', key: 'singleStockMaxPosition', suffix: '元', step: 1, decimals: 0 },
  { label: '最大总持仓', key: 'totalMaxPosition', suffix: '元', step: 1, decimals: 0 },
  { label: '止损比例', key: 'stockStopLoss', suffix: '%', step: 0.01, decimals: 2 },
  { label: '补仓跌幅阈值', key: 'stopLossBuy', suffix: '%', step: 0.01, decimals: 2 },
  { label: '首次止盈阈值', key: 'firstProfitSell', suffix: '%', step: 0.01, decimals: 2 },
  { label: '首次卖出比例', key: 'stockGainSellPencent', suffix: '%', step: 0.01, decimals: 2 },
]

function displayValue(key: string): string {
  const raw = (store.config as any)[key]
  if (raw == null || isNaN(raw)) return ''
  return Number(raw).toFixed(FIELDS.find(f => f.key === key)?.decimals ?? 0)
}

function onChange(key: string, raw: string) {
  const v = parseFloat(raw)
  ;(store.config as any)[key] = isNaN(v) ? 0 : v
}
</script>

<template>
  <div class="card">
    <div class="card-header flex items-center justify-between">
      <span>参数设置</span>
      <button class="btn-primary text-xs px-3 py-1.5" @click="store.saveConfig()" :disabled="store.saving">
        {{ store.saving ? '保存中...' : '保存配置' }}
      </button>
    </div>
    <div class="card-body !py-3">
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6 gap-y-2">
        <div v-for="f in FIELDS" :key="f.key" class="flex items-center gap-1.5">
          <label class="text-[11px] text-slate-500 whitespace-nowrap w-[78px] text-right flex-shrink-0">{{ f.label }}</label>
          <input
            type="number"
            :value="displayValue(f.key)"
            @input="onChange(f.key, ($event.target as HTMLInputElement).value)"
            :step="f.step"
            class="input-field !py-1 !text-xs w-full"
          />
          <span class="text-[11px] text-slate-400 w-5 flex-shrink-0">{{ f.suffix }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
