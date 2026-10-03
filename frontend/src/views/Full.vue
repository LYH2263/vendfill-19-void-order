<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const data = ref<any>({ lanes: [], has_order: false })
onMounted(async () => { data.value = await api('/refills/full?location_id=1') })
</script>
<template>
  <h1>满仓</h1>
  <p class="sub">缺口为 0 的货道（无需补货）· 依据最新未作废补货单
    <template v-if="data.has_order">#{{ data.order_id }}</template>
  </p>
  <div v-if="!data.has_order" class="card" style="color:var(--vf-amber)">无有效补货单（所有单据均已作废），暂无满仓依据。</div>
  <div v-else-if="data.lanes.length === 0" class="card muted">当前有效单中没有满仓货道。</div>
  <div v-else class="card">
    <table>
      <thead><tr><th>货道</th><th>商品</th><th>库存</th><th>在途</th><th>容量</th></tr></thead>
      <tbody>
        <tr v-for="l in data.lanes" :key="l.lane_id">
          <td>{{ l.slot_no }}</td><td>{{ l.sku_name }}</td><td>{{ l.stock }}</td><td>{{ l.in_transit }}</td><td>{{ l.capacity }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
