<template>
  <div class="message user-message" :id="`msg-${message.id}`">
    <div class="message-content">
      <div class="text">{{ message.content }}</div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  message: {
    type: Object,
    required: true
  }
})
</script>

<style lang="scss" scoped>
.user-message {
  padding: 16px 0;
  border-bottom: 1px solid #f0f0f0;
  animation: fadeIn 0.3s;
}

.message-content {
  background: #E3F2FD;
  padding: 12px 16px;
  border-radius: 8px;
  display: inline-block;
  max-width: 80%;
  word-wrap: break-word;
  margin-left: 60%;
}

.text {
  font-size: 15px;
  line-height: 1.6;
  color: #333;
  white-space: pre-wrap;
}
</style>
