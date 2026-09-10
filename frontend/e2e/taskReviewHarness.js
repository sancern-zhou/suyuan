import { createApp, h } from 'vue'
import { createPinia } from 'pinia'
import TaskSchedulerCenter from '../src/components/coordinator/TaskSchedulerCenter.vue'
import TaskReviewPanel from '../src/components/reviews/TaskReviewPanel.vue'
const scheduler = document.querySelector('#app').dataset.scheduler === 'true'
createApp({ render: () => scheduler ? h(TaskSchedulerCenter) : h(TaskReviewPanel, { reviewId: 'review_123' }) })
  .use(createPinia()).mount('#app')
