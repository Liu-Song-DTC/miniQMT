import { getFlaskUrl, getXtquantUrl, getApiToken, loadConnection, getCurrentAccountId } from './accounts'

export async function apiGet(path: string): Promise<any> {
  const url = resolveUrl(path)
  const headers: Record<string, string> = {}
  const token = getApiToken()
  if (token) headers['X-API-Token'] = token
  const accountId = getCurrentAccountId()
  if (accountId) headers['X-Account-Id'] = accountId
  try {
    const resp = await fetch(url, { headers })
    if (!resp.ok) return { success: false, error: `HTTP ${resp.status}` }
    return resp.json()
  } catch (e: any) {
    return { success: false, error: e.message || 'Network error' }
  }
}

export async function apiPost(path: string, body?: any): Promise<any> {
  const url = resolveUrl(path)
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getApiToken()
  if (token) headers['X-API-Token'] = token
  const accountId = getCurrentAccountId()
  if (accountId) headers['X-Account-Id'] = accountId
  try {
    const resp = await fetch(url, { method: 'POST', headers, body: body ? JSON.stringify(body) : undefined })
    if (!resp.ok) return { success: false, error: `HTTP ${resp.status}` }
    return resp.json()
  } catch (e: any) {
    return { success: false, error: e.message || 'Network error' }
  }
}

function resolveUrl(path: string): string {
  const conn = loadConnection()
  // xtquant 网关模式：所有请求统一走网关（不区分 /api/ 还是 /api/v1/）
  if (conn.mode === 'xtquant') {
    const base = getXtquantUrl()
    return `${base}${path}`
  }
  // /api/v1/ 路径强制走 xtquant（不受 mode 限制）
  if (path.startsWith('/api/v1/')) {
    const base = getXtquantUrl()
    return `${base}${path}`
  }
  // auto 模式：检测是否在 xtquant_manager 同源下运行
  if (conn.mode === 'auto') {
    const xtquantBase = getXtquantUrl()
    if (xtquantBase && window.location.origin === xtquantBase) {
      return `${xtquantBase}${path}`
    }
  }
  // Flask 直连模式：走对应账号的 Flask 实例
  const base = getFlaskUrl()
  if (base) return `${base}${path}`
  // 无 Flask URL → 同源（Vite dev proxy 或反向代理）
  return path
}
