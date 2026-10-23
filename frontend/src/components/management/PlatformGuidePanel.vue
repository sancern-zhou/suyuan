<template>
  <div class="management-panel platform-guide-panel">
    <div class="panel-header">
      <h3>平台使用说明</h3>
      <button class="panel-btn" type="button" @click="$emit('close')">关闭</button>
    </div>

    <div class="guide-body">
      <section v-if="usageModes.length" class="guide-section">
        <h4 class="guide-title">如何选择使用模式</h4>
        <div class="mode-grid">
          <div v-for="mode in usageModes" :key="mode.name" class="mode-card">
            <p class="mode-name">{{ mode.name }}</p>
            <p class="mode-desc">{{ mode.desc }}</p>
            <p class="mode-example">"{{ mode.example }}"</p>
          </div>
        </div>
        <p v-if="modeMotto" class="mode-motto">{{ modeMotto }}</p>      </section>

      <section v-if="dataSourceGroups.length" class="guide-section">
        <h4 class="guide-title">数据接入情况</h4>
        <p class="guide-subtitle">以下为平台当前已接入的数据类别与实际可用时间范围，可直接在对话中查询使用。</p>

        <div
          v-for="group in dataSourceGroups"
          :key="group.title"
          class="data-group"
        >
          <h5 class="data-group-title">{{ group.title }}</h5>
          <div class="data-table-wrapper">
            <table class="data-table">
              <thead>
                <tr>
                  <th style="width: 24%">数据类别</th>
                  <th style="width: 10%">粒度</th>
                  <th style="width: 18%">实际可用时间范围</th>
                  <th>说明</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in group.rows" :key="row.name">
                  <td class="cell-name">{{ row.name }}</td>
                  <td>{{ row.granularity }}</td>
                  <td class="cell-range">{{ row.range }}</td>
                  <td class="cell-desc">{{ row.desc }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <p v-if="!usageModes.length && !dataSourceGroups.length" class="guide-empty">
        共享版本不内置使用说明，内容由各项目分支按实际模式与数据接入情况维护。
      </p>
    </div>
  </div>
</template>

<script setup>
defineEmits(['close'])

// 共享段不内置任何项目定制内容：模式介绍、口诀与数据接入表由各项目分支维护。
const usageModes = []
const dataSourceGroups = []
const modeMotto = ''
</script>

<style scoped>
.management-panel {
  height: 100%;
  overflow-y: auto;
  padding: 20px;
  background: white;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 15px;
  border-bottom: 1px solid var(--border-2);
}

.panel-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--text-1);
}

.panel-btn {
  padding: 6px 12px;
  border: 1px solid var(--color-primary);
  background: white;
  color: var(--color-primary);
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.panel-btn:hover {
  background: var(--color-primary);
  color: white;
}

.guide-body {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.guide-section {
  margin-bottom: 8px;
}

.guide-title {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-1);
}

.guide-subtitle {
  margin: 0 0 14px;
  font-size: 13px;
  color: var(--text-2);
}

.guide-empty {
  margin: 40px 0;
  text-align: center;
  font-size: 13px;
  color: var(--text-2);
}

.mode-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.mode-card {
  padding: 12px 14px;
  border: 1px solid var(--border-2);
  border-radius: 8px;
  background: var(--bg-1, #fafafa);
}

.mode-name {
  margin: 0 0 6px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-primary);
}

.mode-desc {
  margin: 0 0 6px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-1);
}

.mode-example {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-2);
}

.mode-motto {
  margin: 12px 0 0;
  padding: 10px 14px;
  border-radius: 6px;
  background: rgba(64, 128, 255, 0.08);
  font-size: 13px;
  color: var(--text-1);
}

.data-group {
  margin-bottom: 20px;
}

.data-group-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-1);
}

.data-table-wrapper {
  overflow-x: auto;
  border: 1px solid var(--border-2);
  border-radius: 8px;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.data-table th,
.data-table td {
  padding: 9px 12px;
  text-align: left;
  vertical-align: top;
  border-bottom: 1px solid var(--border-2);
}

.data-table thead th {
  position: sticky;
  top: 0;
  background: var(--bg-1, #f7f8fa);
  font-weight: 600;
  color: var(--text-1);
  white-space: nowrap;
}

.data-table tbody tr:last-child td {
  border-bottom: none;
}

.data-table tbody tr:nth-child(even) {
  background: rgba(0, 0, 0, 0.015);
}

.cell-name {
  font-weight: 500;
  color: var(--text-1);
}

.cell-range {
  white-space: nowrap;
  color: var(--text-1);
}

.cell-desc {
  color: var(--text-2);
  line-height: 1.5;
}
</style>
