<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { api } from '../api'
const data = ref<any>({ lanes: [] })
const hasOrder = ref(true)
onMounted(async () => {
  data.value = await api('/refills/full?location_id=1')
  hasOrder.value = data.value.order_id != null
})
</script>
<template>
  <h1>满仓</h1>
  <p class="sub">缺口为 0 的货道（无需补货）· 依据最新一张未作废补货单</p>
  <div class="card" v-if="!hasOrder">
    <div class="muted">无有效补货单，暂无可展示的满仓货道。</div>
  </div>
  <div class="card" v-else>
    <table>
      <thead><tr><th>货道</th><th>商品</th><th>库存</th><th>在途</th><th>容量</th></tr></thead>
      <tbody>
        <tr v-for="l in data.lanes" :key="l.lane_id">
          <td>{{ l.slot_no }}</td><td>{{ l.sku_name }}</td><td>{{ l.stock }}</td><td>{{ l.in_transit }}</td><td>{{ l.capacity }}</td>
        </tr>
        <tr v-if="!data.lanes.length"><td colspan="5" class="muted">当前有效单中没有满仓货道</td></tr>
      </tbody>
    </table>
  </div>
</template>
