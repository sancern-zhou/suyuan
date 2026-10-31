<template>
  <img
    v-if="resolvedUrl"
    v-bind="$attrs"
    :src="resolvedUrl"
    @click="emit('click', $event)"
    @error="emit('error', $event)"
  />
</template>

<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'

import { createMessageAttachmentMedia } from './messageAttachmentMedia.js'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  source: {
    type: String,
    required: true
  }
})
const emit = defineEmits(['click', 'resolved', 'error'])
const resolvedUrl = ref('')
const media = createMessageAttachmentMedia({
  onChange: value => {
    resolvedUrl.value = value
    emit('resolved', value)
  },
  onError: (error, source) => {
    console.error('附件图片加载失败:', source, error)
    emit('error', error)
  }
})

watch(
  () => props.source,
  source => media.setSource(source),
  { immediate: true }
)

onBeforeUnmount(() => media.clear())
</script>
