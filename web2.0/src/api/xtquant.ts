import { apiGet, apiPost } from './adapter'
import { getCurrentAccountId } from './accounts'

// ---- xtquant_manager API (v1) ----

function aid(): string { return getCurrentAccountId() }

export async function getAccountIds() {
  const r = await apiGet('/api/v1/accounts')
  if (!r?.success) return []
  return r.data?.accounts || []
}

export async function getAccountStatus(accountId?: string) {
  const r = await apiGet(`/api/v1/accounts/${accountId || aid()}/status`)
  return r?.data || {}
}

export async function getXqPositions(accountId?: string) {
  const r = await apiGet(`/api/v1/accounts/${accountId || aid()}/positions`)
  if (!r?.success) return []
  const raw = r.data?.positions || []
  return raw.map((p: any) => ({
    stock_code: p['证券代码'] || '',
    stock_name: p['证券名称'] || '',
    volume: p['股票余额'] || 0,
    available: p['可用余额'] || 0,
    cost_price: p['成本价'] || 0,
    current_price: p['市价'] || 0,
    market_value: p['市值'] || 0,
    profit_ratio: p['盈亏比(%)'] ? p['盈亏比(%)'] / 100 : 0,
    profit_triggered: false,
    highest_price: p['市价'] || 0,
    stop_loss_price: 0,
    open_date: '--',
    grid_session_active: false,
  }))
}

export async function getXqAsset(accountId?: string) {
  return (await apiGet(`/api/v1/accounts/${accountId || aid()}/asset`))?.data || {}
}

export async function getXqOrders(accountId?: string) {
  const r = await apiGet(`/api/v1/accounts/${accountId || aid()}/orders`)
  if (!r?.success) return []
  return r.data?.orders || []
}

export async function getXqTrades(accountId?: string) {
  const r = await apiGet(`/api/v1/accounts/${accountId || aid()}/trades`)
  if (!r?.success) return []
  return r.data?.trades || []
}

export async function getXqTick(codes: string[], accountId?: string) {
  const r = await apiGet(`/api/v1/market/tick?stock_codes=${codes.join(',')}&account_id=${accountId || aid()}`)
  return r?.data || {}
}

export async function getXqHealth() {
  return (await apiGet('/api/v1/health'))?.data || {}
}

// ---- 止盈止损 API ----

export async function getStopProfitStatus() {
  return (await apiGet('/api/v1/stop-profit/status'))?.data || {}
}

export async function toggleStopProfit(enabled: boolean) {
  const r = await apiPost(`/api/v1/stop-profit/toggle?enabled=${enabled}`)
  return r
}

export async function updateStopProfitConfig(cfg: Record<string, any>) {
  return apiPost('/api/v1/stop-profit/config', cfg)
}

export async function placeXqOrder(order: {
  stock_code: string; order_type: number; order_volume: number;
  price_type: number; price: number; strategy_name?: string; order_remark?: string;
}, accountId?: string) {
  const r = await apiPost(`/api/v1/accounts/${accountId || aid()}/orders`, order)
  if (!r?.success) return -1
  return r.data?.order_id || -1
}
