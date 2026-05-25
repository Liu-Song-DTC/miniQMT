/**
 * 多账户 + 远程连接配置
 *
 * 部署架构:
 *   Vercel (静态 UI) ──HTTPS──► Windows 服务器 (QMT API)
 *
 * 两种后端模式:
 *   "flask"    — 每个账号独立 Flask 实例 (如 :5000 / :5001)
 *   "xtquant"  — 单一 xtquant_manager 网关管理多账号 (推荐远程部署)
 *
 * 配置优先级: 运行时(设置面板持久化 localStorage) > 构建时(env) > 硬编码默认值
 */

// ===== 全局连接设置 =====

export interface ConnectionSettings {
  mode: 'flask' | 'xtquant' | 'auto'
  xtquantUrl: string        // xtquant_manager 网关地址
  apiToken: string          // X-API-Token 请求头
}

const CONN_KEY = 'qmt_connection'

const ENV_DEFAULTS: ConnectionSettings = {
  mode: (import.meta.env.VITE_DEFAULT_BACKEND as any) || 'auto',
  xtquantUrl: import.meta.env.VITE_DEFAULT_XTQUANT_URL || 'http://127.0.0.1:8888',
  apiToken: import.meta.env.VITE_DEFAULT_TOKEN || '',
}

export function loadConnection(): ConnectionSettings {
  try {
    const raw = localStorage.getItem(CONN_KEY)
    if (raw) return { ...ENV_DEFAULTS, ...JSON.parse(raw) }
  } catch { /* ignore */ }
  return { ...ENV_DEFAULTS }
}

export function saveConnection(s: ConnectionSettings): void {
  localStorage.setItem(CONN_KEY, JSON.stringify(s))
}

// ===== 单账号配置 =====

export interface AccountEntry {
  id: string
  label: string
  flaskUrl?: string          // 可选: 覆盖全局连接模式,直接指定该账号的 Flask 地址
}

const ACCOUNTS_KEY = 'qmt_accounts'
const CURRENT_KEY = 'qmt_current_account'

export function loadAccounts(): AccountEntry[] {
  try {
    const raw = localStorage.getItem(ACCOUNTS_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  // 默认双账号（占位 ID，用户需在设置中填入真实账号）
  return [
    { id: '_account_a', label: '账户A', flaskUrl: 'http://127.0.0.1:5000' },
    { id: '_account_b', label: '账户B', flaskUrl: 'http://127.0.0.1:5001' },
  ]
}

export function saveAccounts(accounts: AccountEntry[]): void {
  localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(accounts))
}

export function getCurrentAccountId(): string {
  const stored = localStorage.getItem(CURRENT_KEY)
  if (stored) return stored
  const accounts = loadAccounts()
  return accounts.length > 0 ? accounts[0].id : ''
}

export function setCurrentAccountId(id: string): void {
  localStorage.setItem(CURRENT_KEY, id)
}

export function getCurrentAccount(): AccountEntry {
  const accounts = loadAccounts()
  const id = getCurrentAccountId()
  return accounts.find(a => a.id === id) || accounts[0]
}

// ===== 运行时 URL 解析 =====

export function getFlaskUrl(): string {
  const acc = getCurrentAccount()
  if (acc.flaskUrl) return acc.flaskUrl
  // fallback: 同源（Vite dev proxy 或 Nginx 反向代理）
  return ''
}

export function getXtquantUrl(): string {
  const conn = loadConnection()
  return conn.xtquantUrl
}

export function getApiToken(): string {
  return loadConnection().apiToken
}

/**
 * 当前是否处于 xtquant_manager 网关模式。
 * 网关模式（模式=xtquant，或 auto 且同源）下只能做只读监控+下单，
 * 配置持久化/监控开关/初始化等写操作需 Flask 直连模式。
 */
export function isGatewayMode(): boolean {
  const conn = loadConnection()
  if (conn.mode === 'xtquant') return true
  if (conn.mode === 'auto' && conn.xtquantUrl && window.location.origin === conn.xtquantUrl) return true
  return false
}

// ===== 账号自动发现 =====

export async function discoverAccounts(): Promise<AccountEntry[]> {
  const conn = loadConnection()
  if (conn.mode !== 'xtquant' && conn.mode !== 'auto') return []
  try {
    const base = conn.xtquantUrl
    const headers: Record<string, string> = {}
    if (conn.apiToken) headers['X-API-Token'] = conn.apiToken
    const resp = await fetch(`${base}/api/v1/accounts`, { headers })
    if (!resp.ok) return []
    const data = await resp.json()
    if (!data.success) return []
    const ids: string[] = data.data?.accounts || []
    return ids.map((id, i) => ({
      id,
      label: `账户${String.fromCharCode(65 + i)}`,
    }))
  } catch {
    return []
  }
}

// ===== 安全检测 =====

export function isSecureContext(): boolean {
  return window.isSecureContext || window.location.protocol === 'https:'
}

export function isRemoteUrl(url: string): boolean {
  if (!url) return false
  return !url.includes('127.0.0.1') && !url.includes('localhost') && !url.includes('[::1]')
}

export function checkSecurityWarning(): string | null {
  const conn = loadConnection()
  const warnings: string[] = []

  // Vercel HTTPS 页面不允许请求 HTTP 后端（mixed content）
  if (isSecureContext() && conn.xtquantUrl.startsWith('http://') && isRemoteUrl(conn.xtquantUrl)) {
    warnings.push('当前页面为 HTTPS,但 xtquant_manager 使用 HTTP——浏览器将阻止 mixed content 请求。请为后端配置 HTTPS 或使用 Cloudflare Tunnel。')
  }

  // 无 token 的远程连接
  if (!conn.apiToken && isRemoteUrl(conn.xtquantUrl)) {
    warnings.push('远程连接未设置 API Token,任何知道地址的人都可以访问你的 QMT 接口。')
  }

  return warnings.length > 0 ? warnings.join('\n') : null
}
