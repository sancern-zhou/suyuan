<template>
  <div class="data-table">
    <table>
      <thead>
        <tr>
          <th v-for="(header, index) in headers" :key="index">{{ header }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, rowIndex) in displayRows" :key="rowIndex">
          <td v-for="(cell, cellIndex) in row" :key="cellIndex">{{ cell }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { computed, onMounted } from 'vue'

const props = defineProps({
  rows: {
    type: Array,
    default: () => []
  }
})

const emit = defineEmits(['ready'])

const headers = computed(() => {
  if (props.rows.length > 0) {
    return Object.keys(props.rows[0])
  }
  return ['时间', '浓度', '超标情况']
})

const displayRows = computed(() => {
  return props.rows.map(row => {
    if (typeof row === 'object') {
      return Object.values(row)
    }
    return row
  })
})

onMounted(() => {
  emit('ready')
})
</script>

<style lang="scss" scoped>
.data-table {
  width: 100%;
  overflow-x: auto;
  background: #fafafa;
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);

  table {
    width: 100%;
    border-collapse: collapse;

    th {
      background: #1976D2;
      color: white;
      padding: 12px;
      text-align: left;
      font-weight: 600;
      font-size: 14px;
    }

    td {
      padding: 12px;
      border-bottom: 1px solid #e0e0e0;
      font-size: 14px;
      color: #333;
    }

    tr:last-child td {
      border-bottom: none;
    }

    tr:hover {
      background: #f5f5f5;
    }
  }
}
</style>
