import { authFetch } from '@/auth/http.js'
import { connectScheduledTaskWebSocket } from '@/auth/websocket.js'
import { defineStore } from 'pinia';

const API_BASE = '/api/scheduled-tasks';

const responseErrorMessage = async (response, fallback) => {
  const payload = await response.json().catch(() => null)
  const detail = payload?.detail
  const message = Array.isArray(detail)
    ? detail.map(item => item?.msg || String(item)).join('；')
    : (typeof detail === 'string' ? detail : payload?.message)

  return message || `${fallback}（HTTP ${response.status}）`
}

export const useScheduledTasksStore = defineStore('scheduledTasks', {
  state: () => ({
    tasks: [],
    stats: {
      total: 0,
      running: 0,
      successRate: 0
    },
    eventTypes: [],
    socialUsers: [],
    availableTools: [],
    ws: null,
    wsConnected: false,
    wsConnecting: false,
    wsReconnectEnabled: true
  }),

  actions: {
    async fetchTasks() {
      try {
        const response = await authFetch(API_BASE);
        if (!response.ok) throw new Error('Failed to fetch tasks');
        const data = await response.json();
        // API返回的是 [{task: {...}, next_run_time: ...}, ...]
        // 提取task对象
        this.tasks = Array.isArray(data)
          ? data.map(item => ({
              ...(item.task || item),
              next_run_at: item.next_run_time || item.task?.next_run_at || item.next_run_at || null
            }))
          : [];
      } catch (error) {
        console.error('Failed to fetch tasks:', error);
        this.tasks = [];
      }
    },

    async fetchEventTypes() {
      const response = await authFetch(`${API_BASE}/event-types`);
      if (!response.ok) throw new Error('Failed to fetch event types');
      this.eventTypes = await response.json();
      return this.eventTypes;
    },

    async fetchSocialUsers() {
      const response = await authFetch('/api/social/users');
      if (!response.ok) throw new Error('Failed to fetch social users');
      this.socialUsers = await response.json();
      return this.socialUsers;
    },

    async fetchAvailableTools() {
      const response = await authFetch(`${API_BASE}/tools`, {
        clearOnUnauthorized: false
      });
      if (!response.ok) throw new Error('Failed to fetch available tools');
      const data = await response.json();
      this.availableTools = Array.isArray(data?.tools) ? data.tools : [];
      return this.availableTools;
    },

    async fetchStats() {
      try {
        const response = await authFetch(`${API_BASE}/statistics/summary`);
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

    async fetchTaskExecutions(taskId, limit = 50) {
      const response = await authFetch(`${API_BASE}/${taskId}/executions?limit=${limit}`);
      if (!response.ok) throw new Error('Failed to fetch task executions');
      const data = await response.json();
      return Array.isArray(data?.executions) ? data.executions : [];
    },

    async createTask(data) {
      const response = await authFetch(API_BASE, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const items = body?.detail?.items || [];
        throw new Error(body?.detail?.code === 'invalid_custom_task_tools'
          ? `工具配置无效：${items.map(item => `${item.name}（${item.reason}）`).join('、')}`
          : (body?.detail || 'Failed to create task'));
      }
      const task = await response.json();
      await this.fetchTasks();
      await this.fetchStats();
      return task;
    },

    // WebSocket连接
    async connectWebSocket() {
      if ((this.ws && this.wsConnected) || this.wsConnecting) return;
      this.wsConnecting = true;
      this.wsReconnectEnabled = true;
      try {
        this.ws = await connectScheduledTaskWebSocket();
      } catch (error) {
        this.wsConnecting = false;
        console.error('Failed to obtain WebSocket ticket:', error);
        return;
      }

      this.ws.onopen = () => {
        console.log('WebSocket connected to scheduled tasks');
        this.wsConnected = true;
        this.wsConnecting = false;
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
        this.wsConnecting = false;
      };

      this.ws.onclose = () => {
        console.log('WebSocket disconnected');
        this.wsConnected = false;
        this.wsConnecting = false;
        this.ws = null;
        if (this.wsReconnectEnabled) {
          // Every reconnect obtains a fresh single-use ticket.
          setTimeout(() => this.connectWebSocket(), 5000);
        }
      };
    },

    // 断开WebSocket
    disconnectWebSocket() {
      this.wsReconnectEnabled = false;
      if (this.ws) {
        this.ws.close();
        this.ws = null;
        this.wsConnected = false;
        this.wsConnecting = false;
      }
    },

    async enableTask(taskId) {
      const response = await authFetch(`${API_BASE}/${taskId}/enable`, {
        method: 'POST'
      });
      if (!response.ok) throw new Error('Failed to enable task');
      await this.fetchTasks();
    },

    async disableTask(taskId) {
      const response = await authFetch(`${API_BASE}/${taskId}/disable`, {
        method: 'POST'
      });
      if (!response.ok) throw new Error('Failed to disable task');
      await this.fetchTasks();
    },

    async updateTask(taskId, data) {
      const response = await authFetch(`${API_BASE}/${taskId}`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(data)
      });
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        const items = body?.detail?.items || [];
        throw new Error(body?.detail?.code === 'invalid_custom_task_tools'
          ? `工具配置无效：${items.map(item => `${item.name}（${item.reason}）`).join('、')}`
          : (body?.detail || 'Failed to update task'));
      }
      await this.fetchTasks();
    },

    async deleteTask(taskId) {
      const response = await authFetch(`${API_BASE}/${taskId}`, {
        method: 'DELETE'
      });
      if (!response.ok) throw new Error('Failed to delete task');
      await this.fetchTasks();
    },

    async executeTaskNow(taskId) {
      const response = await authFetch(`${API_BASE}/${taskId}/execute`, {
        method: 'POST'
      });
      if (!response.ok) {
        throw new Error(await responseErrorMessage(response, '立即执行任务失败'))
      }
      const data = await response.json();
      return data;
    }
  }
});
