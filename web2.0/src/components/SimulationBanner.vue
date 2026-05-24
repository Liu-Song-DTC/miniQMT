<script setup lang="ts">
import { useSystemStore } from '../stores/system'
const system = useSystemStore()
</script>

<template>
  <div v-if="system.simulationMode" class="bg-amber-50/80 backdrop-blur-sm border-b border-amber-200/60 px-6 py-2 flex items-center gap-2.5 text-sm text-amber-800">
    <svg class="w-5 h-5 flex-shrink-0 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z"/></svg>
    <strong>模拟交易模式</strong><span class="opacity-70">— 所有交易操作均为模拟，不涉及真实资金</span>
  </div>
</template>
