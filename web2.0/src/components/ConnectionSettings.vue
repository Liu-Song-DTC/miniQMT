<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { loadConnection, saveConnection, checkSecurityWarning, isSecureContext, isRemoteUrl } from '../api/accounts'
import type { ConnectionSettings } from '../api/accounts'

const emit = defineEmits<{ close: []; changed: [] }>()
const form = ref<ConnectionSettings>({ mode: 'auto', xtquantUrl: '', apiToken: '' })
const showToken = ref(false); const testing = ref(false); const testResult = ref('')
const securityWarning = ref<string | null>(null)

onMounted(() => { form.value = loadConnection(); securityWarning.value = checkSecurityWarning() })

function save() {
  if (form.value.mode === 'auto') form.value.mode = 'auto'
  saveConnection({ ...form.value }); securityWarning.value = checkSecurityWarning(); emit('changed')
}

async function testConnection() {
  testing.value = true; testResult.value = ''; save()
  try {
    const base = form.value.xtquantUrl || window.location.origin
    const headers: Record<string, string> = {}
    if (form.value.apiToken) headers['X-API-Token'] = form.value.apiToken
    const ctrl = new AbortController(); setTimeout(() => ctrl.abort(), 5000)
    const resp = await fetch(`${base}/api/v1/health`, { headers, signal: ctrl.signal })
    const data = await resp.json()
    if (resp.ok && data.success) {
      const total = data.data?.total || 0; const healthy = data.data?.healthy || 0
      testResult.value = `✓ 连接成功 — ${total} 个账号, ${healthy} 个在线`
    } else { testResult.value = `✗ HTTP ${resp.status}` }
  } catch (e: any) { testResult.value = `✗ ${e.message}` }
  testing.value = false
}
</script>

<template>
  <Teleport to="body">
    <div class="modal-overlay" @click.self="emit('close')">
      <div class="modal-content w-[540px]">
        <div class="px-6 py-4 border-b border-slate-100">
          <h3 class="text-lg font-semibold text-slate-800">连接设置</h3>
          <p class="text-xs text-slate-400 mt-1">配置 QMT 后端服务器地址和 API Token</p>
        </div>
        <div class="p-6 space-y-5">
          <div v-if="securityWarning" class="bg-amber-50 border border-amber-200 rounded-xl p-3 text-xs text-amber-800 whitespace-pre-line">{{ securityWarning }}</div>

          <div :class="['flex items-center gap-2 text-xs px-3 py-2 rounded-lg', isSecureContext() ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-50 text-slate-500']">
            <span :class="['w-2 h-2 rounded-full', isSecureContext() ? 'bg-emerald-500' : 'bg-slate-300']"></span>
            当前: <strong>{{ isSecureContext() ? 'HTTPS (安全)' : 'HTTP (本地)' }}</strong>
            <span v-if="isSecureContext()" class="text-emerald-600 text-[11px]">— 后端也必须 HTTPS</span>
          </div>

          <div>
            <label class="label-text mb-2">后端模式</label>
            <div class="grid grid-cols-2 gap-2">
              <label :class="['flex items-start gap-2.5 p-3.5 rounded-xl border-2 cursor-pointer transition-all',
                form.mode === 'xtquant' ? 'border-blue-400 bg-blue-50' : 'border-slate-200 hover:border-slate-300']">
                <input type="radio" v-model="form.mode" value="xtquant" class="mt-0.5 accent-blue-600" />
                <div><div class="text-sm font-semibold text-slate-700">网关模式</div><div class="text-[11px] text-slate-400 mt-0.5">xtquant_manager 统一入口（推荐）</div></div>
              </label>
              <label :class="['flex items-start gap-2.5 p-3.5 rounded-xl border-2 cursor-pointer transition-all',
                form.mode === 'flask' ? 'border-blue-400 bg-blue-50' : 'border-slate-200 hover:border-slate-300']">
                <input type="radio" v-model="form.mode" value="flask" class="mt-0.5 accent-blue-600" />
                <div><div class="text-sm font-semibold text-slate-700">直连模式</div><div class="text-[11px] text-slate-400 mt-0.5">每账号独立 Flask 实例</div></div>
              </label>
            </div>
          </div>

          <div v-if="form.mode === 'xtquant'">
            <label class="label-text">网关地址</label>
            <input v-model="form.xtquantUrl" type="url" placeholder="https://your-server.com:8888" class="input-field font-mono" />
          </div>

          <div>
            <label class="label-text">API Token</label>
            <div class="relative">
              <input v-model="form.apiToken" :type="showToken ? 'text' : 'password'" placeholder="留空则不验证（仅限本机）" class="input-field font-mono pr-16" autocomplete="off" />
              <button @click="showToken = !showToken" class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-slate-600">{{ showToken ? '隐藏' : '显示' }}</button>
            </div>
          </div>

          <div class="bg-slate-50 rounded-xl p-4">
            <div class="flex items-center justify-between mb-2"><span class="text-sm font-medium text-slate-600">连通性测试</span>
              <button @click="testConnection" :disabled="testing" class="btn-outline btn-xs">{{ testing ? '测试中...' : '测试连接' }}</button>
            </div>
            <div v-if="testResult" :class="['text-xs font-mono px-3 py-2 rounded-lg', testResult.startsWith('✓') ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700']">{{ testResult }}</div>
            <p v-else class="text-xs text-slate-400">点击测试按钮检查后端可达性</p>
          </div>
        </div>
        <div class="px-6 py-3 bg-slate-50/80 rounded-b-2xl flex justify-end gap-2">
          <button @click="emit('close')" class="btn-ghost">关闭</button>
          <button @click="save(); emit('close')" class="btn-primary">保存</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
