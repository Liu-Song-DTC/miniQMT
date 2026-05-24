<script setup lang="ts">
import { useConfigStore } from '../stores/config'

const store = useConfigStore()

interface FieldDef {
  label: string
  key: string
  suffix?: string
  step?: number
  decimals?: number
}

const NUMERIC_FIELDS: FieldDef[] = [
  { label: '单次买入金额', key: 'singleBuyAmount', suffix: '元', step: 1, decimals: 0 },
  { label: '首次止盈阈值', key: 'firstProfitSell', suffix: '%', step: 0.01, decimals: 2 },
  { label: '首次卖出比例', key: 'stockGainSellPencent', suffix: '%', step: 0.01, decimals: 2 },
  { label: '补仓跌幅阈值', key: 'stopLossBuy', suffix: '%', step: 0.01, decimals: 2 },
  { label: '止损比例', key: 'stockStopLoss', suffix: '%', step: 0.01, decimals: 2 },
  { label: '单股最大持仓', key: 'singleStockMaxPosition', suffix: '元', step: 1, decimals: 0 },
  { label: '最大总持仓', key: 'totalMaxPosition', suffix: '元', step: 1, decimals: 0 },
]

function displayValue(field: FieldDef): string | number {
  const raw = (store.config as any)[field.key]
  if (raw == null || isNaN(raw)) return ''
  return Number(raw).toFixed(field.decimals ?? 0)
}

function onFieldChange(field: FieldDef, raw: string) {
  const v = parseFloat(raw)
  ;(store.config as any)[field.key] = isNaN(v) ? 0 : v
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
    <div class="card-body">
      <div class="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-3">
        <div v-for="f in NUMERIC_FIELDS" :key="f.key" class="space-y-1">
          <label class="label-text">{{ f.label }}</label>
          <div class="flex items-center gap-1.5">
            <input
              type="number"
              :value="displayValue(f)"
              @input="onFieldChange(f, ($event.target as HTMLInputElement).value)"
              :step="f.step"
              class="input-field flex-1 min-w-0 !text-xs"
            />
            <span v-if="f.suffix" class="text-[11px] text-slate-400 flex-shrink-0 w-6 text-right">{{ f.suffix }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
