<script setup lang="ts">
import { useConfigStore } from '../stores/config'

const store = useConfigStore()

interface FieldDef {
  label: string
  key: string
  suffix?: string
  checkboxKey?: string
  step?: number
  decimals?: number
}

const NUMERIC_FIELDS: FieldDef[] = [
  { label: '单次买入金额', key: 'singleBuyAmount', suffix: '元', step: 1, decimals: 0 },
  { label: '首次止盈阈值', key: 'firstProfitSell', suffix: '%', checkboxKey: 'firstProfitSellEnabled', step: 0.01, decimals: 2 },
  { label: '首次卖出比例', key: 'stockGainSellPencent', suffix: '%', checkboxKey: 'firstProfitSellPencent', step: 0.01, decimals: 2 },
  { label: '补仓跌幅阈值', key: 'stopLossBuy', suffix: '%', checkboxKey: 'stopLossBuyEnabled', step: 0.01, decimals: 2 },
  { label: '止损比例', key: 'stockStopLoss', suffix: '%', checkboxKey: 'StopLossEnabled', step: 0.01, decimals: 2 },
  { label: '单股最大持仓', key: 'singleStockMaxPosition', suffix: '元', step: 1, decimals: 0 },
  { label: '最大总持仓', key: 'totalMaxPosition', suffix: '元', step: 1, decimals: 0 },
]

const BOOL_FIELDS = [
  { label: '允许买入', key: 'allowBuy' },
  { label: '允许卖出', key: 'allowSell' },
  { label: '模拟交易', key: 'simulationMode' },
  { label: '全局总开关', key: 'globalAllowBuySell' },
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

function onBoolChange(key: string, checked: boolean) {
  ;(store.config as any)[key] = checked
  store.saveConfig({ [key]: checked } as any)
}
</script>

<template>
  <div class="card">
    <div class="card-header flex items-center justify-between">
      <span>参数设置</span>
      <button class="btn-primary text-xs px-3 py-1" @click="store.saveConfig()" :disabled="store.saving">
        {{ store.saving ? '保存中...' : '保存配置' }}
      </button>
    </div>
    <div class="card-body">
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        <div v-for="f in NUMERIC_FIELDS" :key="f.key" class="space-y-1">
          <label class="label-text">{{ f.label }}</label>
          <div class="flex items-center gap-1">
            <input v-if="f.checkboxKey"
              type="checkbox"
              :checked="(store.config as any)[f.checkboxKey]"
              @change="onBoolChange(f.checkboxKey, ($event.target as HTMLInputElement).checked)"
              class="w-4 h-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500" />
            <input
              type="number"
              :value="displayValue(f)"
              @input="onFieldChange(f, ($event.target as HTMLInputElement).value)"
              :step="f.step"
              class="input-field w-20"
            />
            <span v-if="f.suffix" class="text-xs text-slate-400">{{ f.suffix }}</span>
          </div>
        </div>
      </div>
      <div class="flex flex-wrap gap-4 mt-4 pt-3 border-t border-slate-100">
        <label v-for="item in BOOL_FIELDS" :key="item.key" class="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            :checked="(store.config as any)[item.key]"
            @change="onBoolChange(item.key, ($event.target as HTMLInputElement).checked)"
            class="w-4 h-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"
          />
          <span class="text-slate-600">{{ item.label }}</span>
        </label>
      </div>
    </div>
  </div>
</template>
