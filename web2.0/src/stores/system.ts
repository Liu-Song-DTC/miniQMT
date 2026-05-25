import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import * as flaskApi from '../api/flask'
import { loadAccounts, saveAccounts, getCurrentAccountId, setCurrentAccountId, discoverAccounts } from '../api/accounts'
import type { AccountEntry } from '../api/accounts'

export const useSystemStore = defineStore('system', () => {
  const connected = ref(false)
  const accounts = ref<AccountEntry[]>(loadAccounts())
  const currentAccountId = ref(getCurrentAccountId())
  const account = ref({
    id: '--', availableBalance: 0, maxHoldingValue: 0, totalAssets: 0, timestamp: '--'
  })
  const isMonitoring = ref(false)
  const autoTrading = ref(false)
  const allowBuy = ref(true)
  const allowSell = ref(true)
  const simulationMode = ref(false)
  const positionMonitorRunning = ref(false)
  const lastUpdateTime = ref('')

  const currentAccount = computed(() =>
    accounts.value.find(a => a.id === currentAccountId.value) || accounts.value[0]
  )

  function switchAccount(accountId: string) {
    currentAccountId.value = accountId
    setCurrentAccountId(accountId)
    // reset stale data
    account.value = { id: accountId, availableBalance: 0, maxHoldingValue: 0, totalAssets: 0, timestamp: '--' }
  }

  function addAccount(entry: AccountEntry) {
    const exists = accounts.value.find(a => a.id === entry.id)
    if (exists) Object.assign(exists, entry)
    else accounts.value.push(entry)
    saveAccounts(accounts.value)
  }

  function removeAccount(accountId: string) {
    accounts.value = accounts.value.filter(a => a.id !== accountId)
    saveAccounts(accounts.value)
    if (currentAccountId.value === accountId && accounts.value.length > 0) {
      switchAccount(accounts.value[0].id)
    }
  }

  async function syncAccountsFromGateway() {
    const discovered = await discoverAccounts()
    if (!discovered.length) return false
    // 合并：已手动配置的账号保留，新增自动发现的账号
    const existingIds = new Set(accounts.value.map(a => a.id))
    for (const acc of discovered) {
      if (!existingIds.has(acc.id)) {
        accounts.value.push(acc)
      } else {
        // 更新标签（保留用户自定义的 label 如果已有）
        const existing = accounts.value.find(a => a.id === acc.id)
        if (existing && existing.label === acc.id) {
          existing.label = acc.label
        }
      }
    }
    saveAccounts(accounts.value)
    // 如果当前选中账号不在列表中，切换到第一个
    if (!accounts.value.find(a => a.id === currentAccountId.value)) {
      switchAccount(accounts.value[0].id)
    }
    return true
  }

  async function fetchStatus() {
    const r = await flaskApi.getStatus()
    if (!r) return
    if (r.account) account.value = r.account
    const s = r.settings
    if (s) {
      isMonitoring.value = s.isMonitoring
      autoTrading.value = s.enableAutoTrading
      allowBuy.value = s.allowBuy
      allowSell.value = s.allowSell
      simulationMode.value = s.simulationMode
      positionMonitorRunning.value = s.positionMonitorRunning
    }
    lastUpdateTime.value = new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  async function fetchConnection() {
    connected.value = await flaskApi.getConnectionStatus()
  }

  async function toggleMonitor(on: boolean) {
    await flaskApi.toggleMonitor(on)
    isMonitoring.value = on
  }

  return {
    connected, accounts, currentAccountId, currentAccount, account,
    isMonitoring, autoTrading, allowBuy, allowSell,
    simulationMode, positionMonitorRunning, lastUpdateTime,
    switchAccount, addAccount, removeAccount, syncAccountsFromGateway,
    fetchStatus, fetchConnection, toggleMonitor,
  }
})
