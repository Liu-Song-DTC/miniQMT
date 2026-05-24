import { getFlaskUrl, getXtquantUrl, getApiToken } from './accounts'

export async function apiGet(path: string): Promise<any> {
  const url = resolveUrl(path)
  const headers: Record<string, string> = {}
  const token = getApiToken()
  if (token) headers['X-API-Token'] = token
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
  try {
    const resp = await fetch(url, { method: 'POST', headers, body: body ? JSON.stringify(body) : undefined })
    if (!resp.ok) return { success: false, error: `HTTP ${resp.status}` }
    return resp.json()
  } catch (e: any) {
    return { success: false, error: e.message || 'Network error' }
  }
}

function resolveUrl(path: string): string {
  // xtquant_manager 路径 (/api/v1/...) → 走 xtquant 网关
  if (path.startsWith('/api/v1/')) {
    const base = getXtquantUrl()
    return `${base}${path}`
  }
  // Flask 路径 (/api/...) → 走对应账号的 Flask 实例
  const base = getFlaskUrl()
  if (base) return `${base}${path}`
  // 无 Flask URL → 同源（Vite dev proxy 或反向代理）
  return path
}
