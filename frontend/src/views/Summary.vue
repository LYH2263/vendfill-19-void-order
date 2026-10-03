<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const s = ref<any>({ has_valid_order: false })
onMounted(async () => { s.value = await api('/refills/summary?location_id=1') })
</script>
<template>
  <h1>汇总</h1>
  <p class="sub">本点位补货建议合计 · 依据最新一张未作废补货单
    <span v-if="s.order_id != null">（#{{ s.order_id }} {{ s.status_label }}）</span>
  </p>
  <div class="card" v-if="s.has_valid_order === false">
    <div class="muted">无有效补货单，以下为零值空态；生成新补货单后恢复。</div>
  </div>
  <div class="card grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:1rem">
    <div><div class="muted">建议补货总量</div><div class="stat">{{ s.total_fill ?? 0 }}</div></div>
    <div><div class="muted">待补货道</div><div class="stat">{{ s.need_fill_count ?? 0 }}</div></div>
    <div><div class="muted">满仓货道</div><div class="stat">{{ s.full_count ?? 0 }}</div></div>
    <div><div class="muted">超占货道</div><div class="stat">{{ s.overbooked_count ?? 0 }}</div></div>
  </div>
</template>
