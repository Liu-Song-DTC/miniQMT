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
  // 默认双账号
  return [
    { id: '', label: '账户A', flaskUrl: 'http://127.0.0.1:5000' },
    { id: '', label: '账户B', flaskUrl: 'http://127.0.0.1:5001' },
  ]
}

export function saveAccounts(accounts: AccountEntry[]): void {
  localStorage.setItem(ACCOUNTS_KEY, JSON.stringify(accounts))
}

export function getCurrentAccountId(): string {
  return localStorage.getItem(CURRENT_KEY) || ''
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
