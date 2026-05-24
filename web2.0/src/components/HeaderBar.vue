<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useSystemStore } from '../stores/system'
import type { AccountEntry } from '../api/accounts'
import ConnectionSettings from './ConnectionSettings.vue'

const system = useSystemStore()
const showAccountDialog = ref(false)
const showConnSettings = ref(false)
const showDropdown = ref(false)
const editForm = ref<AccountEntry>({ id: '', label: '', flaskUrl: '' })
const dropdownRef = ref<HTMLElement | null>(null)

function toggleDropdown() { showDropdown.value = !showDropdown.value }
function closeDropdown() { showDropdown.value = false }

function onSwitchAccount(accId: string) {
  system.switchAccount(accId)
  closeDropdown()
}

function openAdd() { editForm.value = { id: '', label: '', flaskUrl: '' }; showAccountDialog.value = true; closeDropdown() }
function openEdit(acc: AccountEntry) { editForm.value = { ...acc }; showAccountDialog.value = true; closeDropdown() }
function saveAccount() {
  if (!editForm.value.id || !editForm.value.label) return
  system.addAccount({ ...editForm.value }); showAccountDialog.value = false
}
function onConnectionChanged() { system.fetchStatus(); system.fetchConnection() }

function onClickOutside(e: MouseEvent) {
  if (dropdownRef.value && !dropdownRef.value.contains(e.target as Node)) {
    closeDropdown()
  }
}
onMounted(() => document.addEventListener('click', onClickOutside))
onUnmounted(() => document.removeEventListener('click', onClickOutside))
</script>

<template>
  <header class="bg-white/80 backdrop-blur-md border-b border-slate-200/60 px-6 py-3 flex items-center justify-between gap-4 sticky top-0 z-40">
    <!-- left: branding + status -->
    <div class="flex items-center gap-4">
      <div class="flex items-center gap-2">
        <div class="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-blue-700 flex items-center justify-center shadow-md shadow-blue-200">
          <span class="text-white font-black text-xs">MQ</span>
        </div>
        <div>
          <h1 class="text-base font-bold text-slate-800 leading-tight">miniQMT</h1>
          <p class="text-[10px] text-slate-400 leading-tight -mt-0.5">v2.0</p>
        </div>
      </div>

      <div class="h-6 w-px bg-slate-200"></div>

      <div class="flex items-center gap-2">
        <span :class="['badge text-[11px]', system.isMonitoring ? 'badge-green' : 'badge-red']">
          <span :class="system.isMonitoring ? 'dot-green' : 'dot-red'"></span>
          {{ system.statusText }}
        </span>
        <span :class="['badge text-[11px]', system.connected ? 'badge-green' : 'badge-amber']">
          <span :class="system.connected ? 'dot-green' : 'dot-amber'"></span>
          {{ system.connected ? '已连接' : '未连接' }}
        </span>
      </div>

      <!-- Account switcher -->
      <div class="relative" ref="dropdownRef">
        <button @click="toggleDropdown" class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold
                       bg-blue-50 text-blue-700 border border-blue-200/60
                       hover:bg-blue-100 hover:border-blue-300 transition-all duration-150">
          <span class="dot-green"></span>
          {{ system.currentAccount.label || system.currentAccount.id }}
          <svg class="w-3 h-3 opacity-40 transition-transform" :class="showDropdown ? 'rotate-180' : ''" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/></svg>
        </button>
        <div v-show="showDropdown" class="absolute top-full left-0 mt-2 w-72 bg-white rounded-xl shadow-lg border border-slate-200/80 z-50">
          <div class="p-2">
            <button v-for="acc in system.accounts" :key="acc.id"
              @click="onSwitchAccount(acc.id)"
              :class="['w-full text-left px-3 py-2.5 rounded-lg text-sm transition-all flex items-center justify-between',
                acc.id === system.currentAccountId ? 'bg-blue-50 text-blue-700 shadow-sm' : 'hover:bg-slate-50 text-slate-600']">
              <div class="flex items-center gap-2">
                <span :class="acc.id === system.currentAccountId ? 'dot-green' : 'dot w-2 h-2 rounded-full bg-slate-300'"></span>
                <span>{{ acc.label }}</span>
              </div>
              <div class="flex items-center gap-1">
                <span class="text-[11px] text-slate-400 font-mono">{{ acc.id.slice(0,4) }}***</span>
                <span @click.stop="openEdit(acc)" class="text-slate-300 hover:text-slate-500 cursor-pointer p-0.5 rounded transition-colors" title="编辑">
                  <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/></svg>
                </span>
              </div>
            </button>
          </div>
          <div class="border-t border-slate-100 px-2 py-1.5">
            <button @click="openAdd" class="w-full text-left px-3 py-2 rounded-lg text-xs font-medium text-blue-600 hover:bg-blue-50 transition-colors">+ 添加账户</button>
          </div>
        </div>
      </div>

      <button @click="showConnSettings = true" class="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors" title="连接设置">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
      </button>
    </div>

    <!-- right: account stats -->
    <div class="flex items-center gap-3">
      <div class="stat-card !py-2 !px-3"><span class="stat-label">可用</span><span class="stat-value !text-sm">¥{{ system.account.availableBalance.toLocaleString() }}</span></div>
      <div class="stat-card !py-2 !px-3"><span class="stat-label">市值</span><span class="stat-value !text-sm">¥{{ system.account.maxHoldingValue.toLocaleString() }}</span></div>
      <div class="stat-card !py-2 !px-3"><span class="stat-label">总资产</span><span class="stat-value !text-sm">¥{{ system.account.totalAssets.toLocaleString() }}</span></div>
    </div>
  </header>

  <!-- Account edit dialog -->
  <Teleport to="body">
    <div v-if="showAccountDialog" class="modal-overlay" @click.self="showAccountDialog = false">
      <div class="modal-content w-[420px]">
        <div class="px-6 py-4 border-b border-slate-100"><h3 class="text-lg font-semibold text-slate-800">{{ system.accounts.some(a => a.id === editForm.id) ? '编辑账户' : '添加账户' }}</h3></div>
        <div class="p-6 space-y-4">
          <div><label class="label-text">账户 ID <span class="text-red-400">*</span></label><input v-model="editForm.id" placeholder="如 25105132" class="input-field" :disabled="system.accounts.some(a => a.id === editForm.id)" /></div>
          <div><label class="label-text">显示名称 <span class="text-red-400">*</span></label><input v-model="editForm.label" placeholder="如 账户A" class="input-field" /></div>
          <div><label class="label-text">Flask 直连地址 <span class="text-slate-400 font-normal">(可选)</span></label><input v-model="editForm.flaskUrl" placeholder="http://127.0.0.1:5000" class="input-field" /><p class="text-[10px] text-slate-400 mt-1">使用 Flask 直连模式时单独指定地址</p></div>
        </div>
        <div class="px-6 py-3 bg-slate-50/80 rounded-b-2xl flex justify-between">
          <button v-if="system.accounts.some(a => a.id === editForm.id) && system.accounts.length > 1" @click="system.removeAccount(editForm.id); showAccountDialog = false" class="btn-ghost !text-red-500 text-xs">删除</button>
          <span v-else></span>
          <div class="flex gap-2"><button @click="showAccountDialog = false" class="btn-ghost">取消</button><button @click="saveAccount" :disabled="!editForm.id || !editForm.label" class="btn-primary">保存</button></div>
        </div>
      </div>
    </div>
  </Teleport>
  <ConnectionSettings v-if="showConnSettings" @close="showConnSettings = false" @changed="onConnectionChanged" />
</template>
