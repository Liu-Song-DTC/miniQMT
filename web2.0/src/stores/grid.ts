import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { GridSession, RiskTemplate } from '../types'
import * as flaskApi from '../api/flask'

export const useGridStore = defineStore('grid', () => {
  const sessions = ref<GridSession[]>([])
  const riskTemplates = ref<Record<string, RiskTemplate>>({})
  const templates = ref<any[]>([])
  const loading = ref(false)

  async function fetchSessions() {
    sessions.value = await flaskApi.getAllGridSessions()
  }

  async function fetchRiskTemplates() {
    riskTemplates.value = await flaskApi.getGridRiskTemplates()
  }

  async function fetchTemplates() {
    templates.value = await flaskApi.getGridTemplates()
  }

  async function fetchAll() {
    loading.value = true
    await Promise.all([fetchSessions(), fetchRiskTemplates(), fetchTemplates()])
    loading.value = false
  }

  async function startSession(params: any) {
    const r = await flaskApi.startGrid(params)
    if (r?.success) await fetchSessions()
    return r
  }

  async function stopSession(sessionId: number) {
    const r = await flaskApi.stopGrid(sessionId)
    if (r?.success) await fetchSessions()
    return r
  }

  function getSessionByStock(stockCode: string): GridSession | undefined {
    return sessions.value.find(s => s.stock_code === stockCode)
  }

  return { sessions, riskTemplates, templates, loading, fetchSessions, fetchRiskTemplates, fetchTemplates, fetchAll, startSession, stopSession, getSessionByStock }
})
