import axios from 'axios'

// 创建 axios 实例
const api = axios.create({
  baseURL: '/api',
  timeout: 60000,  // 60秒，因为LLM调用可能需要较长时间
  headers: {
    'Content-Type': 'application/json',
  },
})

// 推荐接口
export const recommend = async (userId, query, topK = 10) => {
  const response = await api.post('/recommend', {
    user_id: userId,
    query,
    top_k: topK,
  })
  return response.data
}

// 流式对话接口 (SSE via fetch)
export const streamChat = (userId, query, topK = 10, callbacks) => {
  const controller = new AbortController()
  const signal = controller.signal

  ;(async () => {
    try {
      callbacks.onStart?.()
      
      const response = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, query, top_k: topK }),
        signal,
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`)
      }

      if (!response.body) {
        throw new Error('ReadableStream not supported')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed || !trimmed.startsWith('data: ')) continue
          
          try {
            const data = JSON.parse(trimmed.slice(6))
            switch (data.type) {
              case 'start':
                callbacks.onStart?.()
                break
              case 'thinking':
                callbacks.onThinking?.(data.steps || data.content)
                break
              case 'chunk':
                callbacks.onChunk?.(data.content)
                break
              case 'end':
                callbacks.onEnd?.(data)
                return
              case 'error':
                callbacks.onError?.(data.message)
                return
            }
          } catch (e) {
            // 忽略解析错误
          }
        }
      }
      
      callbacks.onEnd?.({})
    } catch (error) {
      if (error.name !== 'AbortError') {
        console.error('SSE error:', error)
        callbacks.onError?.(error.message || '连接错误')
      }
    }
  })()

  // 返回取消函数
  return () => controller.abort()
}

// 获取对话历史
export const getHistory = async (userId, n = 10) => {
  const response = await api.get(`/history/${userId}`, {
    params: { n }
  })
  return response.data
}

// 更新用户偏好
export const updateProfile = async (userId, preferences) => {
  const response = await api.post(`/profile/${userId}`, preferences)
  return response.data
}

// 健康检查
export const healthCheck = async () => {
  const response = await api.get('/health')
  return response.data
}

// 记录用户行为事件
export const recordEvent = async (eventData) => {
  try {
    await api.post('/events', eventData)
  } catch (error) {
    console.error('Failed to record event:', error)
  }
}

// 批量记录用户行为事件
export const recordBatchEvents = async (events) => {
  try {
    await api.post('/events/batch', events)
  } catch (error) {
    console.error('Failed to record batch events:', error)
  }
}

// 获取评估指标
export const getEvaluationMetrics = async (strategy = 'all', timeWindow = '24h') => {
  const response = await api.get('/evaluation/metrics', {
    params: { strategy, time_window: timeWindow }
  })
  return response.data
}

// 获取 A/B 测试对比报告
export const getABTestReport = async (timeWindow = '24h') => {
  const response = await api.get('/evaluation/abtest/report', {
    params: { time_window: timeWindow }
  })
  return response.data
}

export default api
