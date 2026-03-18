import { defineStore } from 'pinia';

const API_BASE = '/api/scheduled-tasks';

export const useScheduledTasksStore = defineStore('scheduledTasks', {
  state: () => ({
    tasks: [],
    stats: {
      total: 0,
      running: 0,
      successRate: 0
    },
    ws: null,
    wsConnected: false
  }),

  actions: {
    async fetchTasks() {
      try {
        const response = await fetch(API_BASE);
        if (!response.ok) throw new Error('Failed to fetch tasks');
        const data = await response.json();
        // API返回的是 [{task: {...}, next_run_time: ...}, ...]
        // 提取task对象
        this.tasks = Array.isArray(data) ? data.map(item => item.task || item) : [];
      } catch (error) {
        console.error('Failed to fetch tasks:', error);
        this.tasks = [];
      }
    },

    async fetchStats() {
      try {
        const response = await fetch(`${API_BASE}/statistics/summary`);
        if (!response.ok) throw new Error('Failed to fetch stats');
        const data = await response.json();
        this.stats = {
          total: data.total,
          running: data.running,
          successRate: (data.success_rate * 100).toFixed(1)
        };
      } catch (error) {
        console.error('Failed to fetch stats:', error);
      }
    },

    // WebSocket连接
    connectWebSocket() {
      if (this.ws && this.wsConnected) return;

      const wsUrl = `ws://${window.location.host}/ws/scheduled-tasks`;
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('WebSocket connected to scheduled tasks');
        this.wsConnected = true;
      };

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          console.log('WebSocket message:', message);

          // 根据事件类型处理
          if (message.event === 'task_created' ||
              message.event === 'task_updated' ||
              message.event === 'task_deleted' ||
              message.event === 'task_enabled' ||
              message.event === 'task_disabled') {
            // 任务变化，重新获取任务列表
            this.fetchTasks();
            this.fetchStats();
          }
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.wsConnected = false;
      };

      this.ws.onclose = () => {
        console.log('WebSocket disconnected');
        this.wsConnected = false;
        // 5秒后重连
        setTimeout(() => {
          this.connectWebSocket();
        }, 5000);
      };
    },

    // 断开WebSocket
    disconnectWebSocket() {
      if (this.ws) {
        this.ws.close();
        this.ws = null;
        this.wsConnected = false;
      }
    },

    async enableTask(taskId) {
      const response = await fetch(`${API_BASE}/${taskId}/enable`, {
        method: 'POST'
      });
      if (!response.ok) throw new Error('Failed to enable task');
      await this.fetchTasks();
    },

    async disableTask(taskId) {
      const response = await fetch(`${API_BASE}/${taskId}/disable`, {
        method: 'POST'
      });
      if (!response.ok) throw new Error('Failed to disable task');
      await this.fetchTasks();
    },

    async updateTask(taskId, data) {
      const response = await fetch(`${API_BASE}/${taskId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });
      if (!response.ok) throw new Error('Failed to update task');
      await this.fetchTasks();
    },

    async deleteTask(taskId) {
      const response = await fetch(`${API_BASE}/${taskId}`, {
        method: 'DELETE'
      });
      if (!response.ok) throw new Error('Failed to delete task');
      await this.fetchTasks();
    },

    async executeTaskNow(taskId) {
      const response = await fetch(`${API_BASE}/${taskId}/execute`, {
        method: 'POST'
      });
      if (!response.ok) throw new Error('Failed to execute task');
      const data = await response.json();
      return data;
    }
  }
});
