<template>
  <div class="kb-selector">
    <div class="kb-header" @click="toggleExpand">
      <span class="kb-icon">&#128218;</span>
      <span class="kb-title">知识库</span>
      <span v-if="selectedCount > 0" class="kb-count">{{ selectedCount }}</span>
      <span class="expand-icon" :class="{ expanded: isExpanded }">&#9660;</span>
    </div>

    <div class="kb-list" v-show="isExpanded">
      <div v-if="loading" class="kb-loading">加载中...</div>

      <template v-else>
        <!-- 公共知识库分组 -->
        <div class="kb-group" v-if="publicKnowledgeBases.length > 0">
          <div class="kb-group-header">公共知识库</div>
          <div
            v-for="kb in publicKnowledgeBases"
            :key="kb.id"
            class="kb-item"
            :class="{ selected: isSelected(kb.id) }"
            @click="toggleSelect(kb.id)"
          >
            <input
              type="checkbox"
              :checked="isSelected(kb.id)"
              @click.stop
              @change="toggleSelect(kb.id)"
            />
            <div class="kb-info">
              <span class="kb-name">
                <span class="kb-type-badge public">公共</span>
                {{ kb.name }}
              </span>
              <span class="kb-meta">{{ kb.document_count }} 文档</span>
            </div>
          </div>
        </div>

        <!-- 个人知识库分组 -->
        <div class="kb-group" v-if="privateKnowledgeBases.length > 0">
          <div class="kb-group-header">我的知识库</div>
          <div
            v-for="kb in privateKnowledgeBases"
            :key="kb.id"
            class="kb-item"
            :class="{ selected: isSelected(kb.id) }"
            @click="toggleSelect(kb.id)"
          >
            <input
              type="checkbox"
              :checked="isSelected(kb.id)"
              @click.stop
              @change="toggleSelect(kb.id)"
            />
            <div class="kb-info">
              <span class="kb-name">
                <span class="kb-type-badge private">个人</span>
                {{ kb.name }}
              </span>
              <span class="kb-meta">{{ kb.document_count }} 文档</span>
            </div>
          </div>
        </div>

        <div v-if="knowledgeBases.length === 0" class="kb-empty">
          暂无可用知识库
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useKnowledgeBaseStore } from '@/stores/knowledgeBaseStore'

const store = useKnowledgeBaseStore()
const isExpanded = ref(false)

const loading = computed(() => store.loading)
const knowledgeBases = computed(() => store.knowledgeBases)
const publicKnowledgeBases = computed(() => store.publicKbs)
const privateKnowledgeBases = computed(() => store.privateKbs)
const selectedIds = computed(() => store.selectedIds)
const selectedCount = computed(() => store.selectedCount)

const toggleExpand = () => {
  isExpanded.value = !isExpanded.value
}

const isSelected = (id) => selectedIds.value.includes(id)

const toggleSelect = (id) => {
  store.toggleSelection(id)
}

onMounted(async () => {
  if (knowledgeBases.value.length === 0) {
    await store.fetchKnowledgeBases()
  }
})
</script>

<style scoped>
.kb-selector {
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e8e8e8;
  overflow: hidden;
}

.kb-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
  background: #fafafa;
  transition: background 0.2s;
}

.kb-header:hover {
  background: #f0f0f0;
}

.kb-icon {
  font-size: 16px;
}

.kb-title {
  flex: 1;
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

.kb-count {
  background: #1890ff;
  color: #fff;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
}

.expand-icon {
  font-size: 10px;
  color: #999;
  transition: transform 0.2s;
}

.expand-icon.expanded {
  transform: rotate(180deg);
}

.kb-list {
  max-height: 300px;
  overflow-y: auto;
  border-top: 1px solid #e8e8e8;
}

.kb-loading {
  padding: 20px;
  text-align: center;
  color: #999;
  font-size: 13px;
}

.kb-group {
  padding: 4px 0;
}

.kb-group-header {
  font-size: 12px;
  color: #666;
  padding: 8px 12px 4px;
  font-weight: 500;
}

.kb-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  cursor: pointer;
  transition: background 0.2s;
}

.kb-item:hover {
  background: #f5f5f5;
}

.kb-item.selected {
  background: #e6f7ff;
}

.kb-item input[type="checkbox"] {
  width: 16px;
  height: 16px;
  cursor: pointer;
}

.kb-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.kb-name {
  font-size: 13px;
  color: #333;
  display: flex;
  align-items: center;
  gap: 6px;
}

.kb-meta {
  font-size: 11px;
  color: #999;
}

.kb-type-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

.kb-type-badge.public {
  background: #e6f7ff;
  color: #1890ff;
}

.kb-type-badge.private {
  background: #f6ffed;
  color: #52c41a;
}

.kb-empty {
  padding: 20px;
  text-align: center;
  color: #999;
  font-size: 13px;
}
</style>
