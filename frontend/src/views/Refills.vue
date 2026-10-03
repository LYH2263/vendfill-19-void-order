<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api'

function errText(e: any, fallback: string) {
  try { return JSON.parse(e?.message || '').detail || fallback } catch { return fallback }
}

interface FillLine { lane_id: number; slot_no: string; sku_name: string; status: string; gap: number; fill_qty: number }
interface Order {
  id: number
  status: 'active' | 'verified' | 'void'
  status_label: string
  created_at: string | null
  total_fill: number
  need_fill_count: number
  full_count: number
  overbooked_count: number
  lines?: FillLine[]
}

const orders = ref<Order[]>([])
const current = ref<Order | null>(null)
const loading = ref(false)
const error = ref('')

const validCurrent = computed(() => current.value && current.value.id != null ? current.value : null)

async function refresh() {
  const [list, latest] = await Promise.all([
    api<Order[]>('/refills?location_id=1'),
    api<Order>('/refills/latest?location_id=1'),
  ])
  orders.value = list
  current.value = latest.id != null ? latest : null
}

async function run() {
  loading.value = true; error.value = ''
  try {
    await api('/refills/run?location_id=1', { method: 'POST' })
    await refresh()
  } catch (e: any) {
    error.value = errText(e, '生成失败')
  } finally {
    loading.value = false
  }
}

async function act(id: number, kind: 'verify' | 'void') {
  error.value = ''
  // 作废失败（如已核销）时保持改前展示：后端拒绝即不刷新
  try {
    await api(`/refills/${id}/${kind}`, { method: 'POST' })
    await refresh()
  } catch (e: any) {
    error.value = errText(e, '操作失败')
  }
}

function fmtTime(t: string | null) {
  return t ? new Date(t).toLocaleString('zh-CN', { hour12: false }) : ''
}
function badgeClass(status: string) {
  return status === 'verified' ? 'badge-ok' : status === 'void' ? 'badge-bad' : 'badge-warn'
}

onMounted(refresh)
</script>
<template>
  <h1>补货小票</h1>
  <p class="sub">gap = 容量 − 库存 − 在途 · 未核销单可作废，已核销单禁止作废</p>
  <button class="btn" :disabled="loading" @click="run">{{ loading ? '生成中…' : '生成补货单' }}</button>
  <p v-if="error" class="badge badge-bad" style="margin-top:0.6rem">{{ error }}</p>

  <div class="vf-machine-layout" style="margin-top:1rem">
    <div>
      <div class="card" v-if="validCurrent">
        <div class="vf-receipt">
          <h2>*** VendFill 补货单 ***</h2>
          <div style="text-align:center;font-size:0.72rem;margin-bottom:0.4rem">
            #{{ validCurrent.id }} · {{ fmtTime(validCurrent.created_at) }}
            <span class="badge" :class="badgeClass(validCurrent.status)">{{ validCurrent.status_label }}</span>
          </div>
          <div class="vf-receipt-line" style="font-weight:700;border-bottom:2px dashed #8a7e64">
            <span>货道 / 商品</span><span>补量</span>
          </div>
          <div class="vf-receipt-line" v-for="l in validCurrent.lines" :key="l.lane_id">
            <span>{{ l.slot_no }} {{ l.sku_name }}
              <small>({{ l.status === 'need_fill' ? '待补' : l.status === 'full' ? '满仓' : '超占' }})</small>
            </span>
            <span>{{ l.fill_qty }} / 缺{{ l.gap }}</span>
          </div>
          <p style="text-align:center;margin:1rem 0 0;font-size:0.72rem;color:#6a5e48">谢谢使用 · 请核对后装机</p>
        </div>
      </div>
      <div class="card" v-else>
        <div class="muted">当前无有效补货单（未作废单不存在），请生成新补货单。</div>
      </div>
    </div>

    <div class="card">
      <strong style="font-size:0.85rem">全部单据</strong>
      <table style="margin-top:0.5rem">
        <thead><tr><th>#</th><th>状态</th><th>总件数</th><th>时间</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="o in orders" :key="o.id">
            <td>{{ o.id }}</td>
            <td><span class="badge" :class="badgeClass(o.status)">{{ o.status_label }}</span></td>
            <td>{{ o.total_fill }}</td>
            <td style="font-size:0.72rem">{{ fmtTime(o.created_at) }}</td>
            <td style="white-space:nowrap">
              <button class="btn" style="font-size:0.68rem;padding:0.2rem 0.5rem;margin-right:0.3rem"
                      :disabled="o.status !== 'active'"
                      @click="act(o.id, 'verify')">核销</button>
              <button class="btn" style="font-size:0.68rem;padding:0.2rem 0.5rem;background:var(--vf-red);color:#1a0508"
                      :disabled="o.status !== 'active'"
                      @click="act(o.id, 'void')">作废</button>
            </td>
          </tr>
          <tr v-if="!orders.length"><td colspan="5" class="muted">暂无单据</td></tr>
        </tbody>
      </table>
      <p class="muted" style="font-size:0.7rem;margin:0.5rem 0 0">
        作废只翻转单据状态：货道库存与在途不变；满仓与汇总回退到上一张未作废单。
      </p>
    </div>
  </div>
</template>
