<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'

const orders = ref<any[]>([])
const latest = ref<any>(null)
const error = ref('')
const busy = ref<number | null>(null)

const STATUS_LABEL: Record<string, string> = {
  active: '未核销',
  verified: '已核销',
  voided: '已作废',
}
const STATUS_BADGE: Record<string, string> = {
  active: 'badge-warn',
  verified: 'badge-ok',
  voided: 'badge-bad',
}
const LINE_STATUS: Record<string, string> = { need_fill: '待补', full: '满仓', overbooked: '超占' }

async function refresh() {
  const [list, head] = await Promise.all([
    api<any[]>('/refills?location_id=1'),
    api('/refills/latest?location_id=1'),
  ])
  orders.value = list
  latest.value = head
}

async function run() {
  error.value = ''
  try {
    await api('/refills/run?location_id=1', { method: 'POST' })
    await refresh()
  } catch (e: any) { error.value = e.message }
}

async function act(id: number, kind: 'void' | 'verify') {
  error.value = ''
  busy.value = id
  try {
    await api(`/refills/${id}/${kind}`, { method: 'POST' })
    await refresh()
  } catch (e: any) {
    error.value = e.message
    await refresh()
  } finally { busy.value = null }
}

onMounted(refresh)
</script>
<template>
  <h1>补货小票</h1>
  <p class="sub">gap = 容量 − 库存 − 在途 · 作废后该单不再作为有效单，库存与在途不变</p>
  <button class="btn" @click="run">生成补货单</button>
  <p v-if="error" class="card" style="color:var(--vf-red);margin-top:0.75rem">{{ error }}</p>

  <h2 class="sub" style="margin-top:1.2rem">当前有效单（满仓 / 汇总默认依据）</h2>
  <div v-if="latest && latest.has_order" class="vf-receipt">
    <h2>*** VendFill 补货单 #{{ latest.id }} · {{ STATUS_LABEL[latest.status] }} ***</h2>
    <div class="vf-receipt-line" style="font-weight:700;border-bottom:2px dashed #8a7e64">
      <span>货道 / 商品</span><span>补量</span>
    </div>
    <div class="vf-receipt-line" v-for="l in latest.lines" :key="l.lane_id">
      <span>{{ l.slot_no }} {{ l.sku_name }}
        <small>({{ LINE_STATUS[l.status] }})</small>
      </span>
      <span>{{ l.fill_qty }} / 缺{{ l.gap }}</span>
    </div>
    <p style="text-align:center;margin:1rem 0 0;font-size:0.72rem;color:#6a5e48">谢谢使用 · 请核对后装机</p>
  </div>
  <div v-else class="card" style="color:var(--vf-amber)">无有效补货单（所有单据均已作废），请生成新补货单。</div>

  <h2 class="sub" style="margin-top:1.2rem">历史单据</h2>
  <div class="card">
    <table>
      <thead><tr><th>单号</th><th>状态</th><th>建议补货总量</th><th>生成时间</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="o in orders" :key="o.id">
          <td>#{{ o.id }}</td>
          <td><span class="badge" :class="STATUS_BADGE[o.status]">{{ STATUS_LABEL[o.status] }}</span></td>
          <td>{{ o.total_fill }}</td>
          <td>{{ o.created_at.replace('T', ' ').slice(0, 19) }}</td>
          <td>
            <template v-if="o.status === 'active'">
              <button class="btn" :disabled="busy === o.id" @click="act(o.id, 'verify')">核销</button>
              <button class="btn" style="background:var(--vf-red);color:#fff;margin-left:0.4rem"
                      :disabled="busy === o.id" @click="act(o.id, 'void')">作废</button>
            </template>
            <span v-else-if="o.status === 'verified'" class="muted">已核销单禁止作废</span>
            <span v-else class="muted">已作废，不参与默认展示</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
