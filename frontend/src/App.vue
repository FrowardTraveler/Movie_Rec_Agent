<template>
  <div class="min-h-screen bg-gradient-to-br from-primary-50 via-white to-gray-50 flex flex-col">
    <!-- 头部 -->
    <header class="bg-white border-b border-gray-200 shadow-sm">
      <div class="chat-container py-4">
        <div class="flex items-center justify-between">
          <div class="flex items-center space-x-3">
            <div class="w-10 h-10 bg-gradient-to-br from-primary-500 to-primary-700 rounded-lg flex items-center justify-center">
              <svg class="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z" />
              </svg>
            </div>
            <div>
              <h1 class="text-lg font-bold text-gray-900">智能电影推荐 Agent</h1>
              <p class="text-xs text-gray-500">基于 LLM + 推荐算法的智能推荐</p>
            </div>
          </div>
          <div class="flex items-center space-x-2">
            <span
              class="px-2 py-1 text-xs font-medium rounded-full"
              :class="isConnected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'"
            >
              {{ isConnected ? '已连接' : '未连接' }}
            </span>
            <button
              @click="clearChat"
              class="px-3 py-1.5 text-xs font-medium text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
            >
              清空对话
            </button>
          </div>
        </div>
      </div>
    </header>

    <!-- 聊天区域 -->
    <main class="flex-1 overflow-y-auto">
      <div class="chat-container py-6">
        <!-- 欢迎消息 -->
        <div v-if="messages.length === 0" class="text-center py-12">
          <div class="w-16 h-16 bg-gradient-to-br from-primary-500 to-primary-700 rounded-full flex items-center justify-center mx-auto mb-4">
            <svg class="w-8 h-8 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
          </div>
          <h2 class="text-2xl font-bold text-gray-900 mb-2">你好！我是你的智能电影推荐助手</h2>
          <p class="text-gray-600 mb-6">告诉我你喜欢什么类型的电影，或者你的心情如何，我来为你推荐合适的影片</p>
          
          <!-- 快捷按钮 -->
          <div class="flex flex-wrap justify-center gap-2">
            <button
              v-for="suggestion in suggestions"
              :key="suggestion"
              @click="sendSuggestion(suggestion)"
              class="px-4 py-2 text-sm bg-white border border-gray-200 hover:border-primary-500 hover:text-primary-600 rounded-full transition-all"
            >
              {{ suggestion }}
            </button>
          </div>
        </div>

        <!-- 消息列表 -->
        <div v-else class="space-y-4">
          <ChatMessage
            v-for="(msg, index) in messages"
            :key="index"
            :message="msg"
            :is-user="msg.isUser"
          />

          <!-- 正在输入指示器 -->
          <div v-if="isTyping" class="message-agent">
            <div class="flex items-start space-x-2">
              <div class="flex-shrink-0 w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-xs font-bold text-gray-600">
                AI
              </div>
              <TypingIndicator />
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- 输入区域 -->
    <footer class="bg-white border-t border-gray-200">
      <div class="chat-container py-4">
        <form @submit.prevent="sendMessage" class="flex items-end space-x-3">
          <div class="flex-1">
            <input
              v-model="inputMessage"
              type="text"
              placeholder="输入你的想法，例如：推荐几部科幻电影..."
              class="w-full px-4 py-3 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent resize-none"
              :disabled="isTyping"
              @keydown.enter.exact.prevent="sendMessage"
            />
          </div>
          <button
            type="submit"
            :disabled="!inputMessage.trim() || isTyping"
            class="px-6 py-3 bg-primary-600 text-white font-medium rounded-xl hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center space-x-2"
          >
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
            </svg>
            <span>发送</span>
          </button>
        </form>
        <p class="text-xs text-gray-400 mt-2 text-center">
          按 Enter 发送 · 支持推荐、搜索、对话等功能
        </p>
      </div>
    </footer>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import ChatMessage from './components/ChatMessage.vue'
import TypingIndicator from './components/TypingIndicator.vue'
import { recommend, streamChat, healthCheck, recordEvent } from './services/api'

const messages = ref([])
const inputMessage = ref('')
const isTyping = ref(false)
const isConnected = ref(false)
const userId = ref('user_' + Math.random().toString(36).substring(2, 10))
const currentSessionId = ref('')
const currentStrategy = ref('llm_only')

const suggestions = [
  '推荐几部电影',
  '我今天心情不好',
  '搜索复仇者联盟',
  '推荐一些治愈的电影',
]

onMounted(async () => {
  try {
    await healthCheck()
    isConnected.value = true
  } catch (error) {
    isConnected.value = false
  }
})

const generateSessionId = () => {
  return 'session_' + Date.now() + '_' + Math.random().toString(36).substring(2, 9)
}

const sendMessage = async () => {
  const text = inputMessage.value.trim()
  if (!text || isTyping.value) return

  // 生成新的会话 ID
  currentSessionId.value = generateSessionId()

  // 添加用户消息
  messages.value.push({
    text,
    isUser: true,
    timestamp: new Date(),
  })

  inputMessage.value = ''
  isTyping.value = true

  // 添加一个空的 AI 回复用于流式更新
  const aiMessageIndex = messages.value.length
  messages.value.push({
    text: '🧠 正在思考...',
    isUser: false,
    thinking: true,
    thinkingSteps: [],
    movies: null,
    searchResults: null,
    timestamp: new Date(),
    userId: userId.value,
    query: text,
    strategy: currentStrategy.value,
    sessionId: currentSessionId.value,
  })

  try {
    let fullText = ''
    let movieData = null

    // 使用 SSE 流式接口
    const cancelStream = streamChat(userId.value, text, 10, {
      onStart: () => {
        messages.value[aiMessageIndex].text = '🧠 正在思考...'
      },
      onThinking: (steps) => {
        // 只更新思考步骤，不清空已生成的文本
        messages.value[aiMessageIndex].thinkingSteps = Array.isArray(steps) ? steps : []
      },
      onChunk: (content) => {
        fullText += content
        messages.value[aiMessageIndex].text = fullText
      },
      onEnd: (data) => {
        // 从 agent_results 中提取电影推荐结果
        if (data.agent_results && Array.isArray(data.agent_results)) {
          const recommendResult = data.agent_results.find(
            r => r.agent_name === 'recommend_agent' && r.success
          )
          
          if (recommendResult && recommendResult.data && recommendResult.data.items) {
            const items = recommendResult.data.items
            // 转换为前端期望的电影格式
            movieData = items.map(item => ({
              id: item.movie_id || item.id,
              movie_id: item.movie_id || item.id,
              title: item.title_zh || item.title,
              title_en: item.title_en || item.title || '',
              genres: item.genres || '',
              rating: item.rating || item.score || '',
              year: item.year || '',
              poster: item.poster_url || item.poster || '',
              imdb_url: item.imdb_url || '',
              source: item.source || recommendResult.data.source || 'unknown',
              reason: item.reason || '',
            }))
            
            messages.value[aiMessageIndex].movies = movieData
            
            // 记录 impression 事件
            const movieIds = movieData.map(m => m.id || m.movie_id).filter(id => id)
            if (movieIds.length > 0) {
              recordEvent({
                user_id: userId.value,
                event_type: 'impression',
                movie_id: null,
                query: text,
                recommended_movies: movieIds,
                strategy: currentStrategy.value,
                session_id: currentSessionId.value,
                metadata: {
                  movie_count: movieIds.length,
                },
              })
            }
          }
        }
        
        if (data.latency_ms) {
          messages.value[aiMessageIndex].latency_ms = data.latency_ms
        }
        if (data.strategy) {
          messages.value[aiMessageIndex].strategy = data.strategy
        }
        isTyping.value = false
      },
      onError: (error) => {
        console.error('SSE 错误:', error)
        messages.value[aiMessageIndex].thinking = false
        messages.value[aiMessageIndex].text = '抱歉，系统出现了一些问题。请稍后再试。'
        isTyping.value = false
      },
    })

    // 如果需要在某个时机取消流，可以调用 cancelStream()
  } catch (error) {
    console.error('请求错误:', error)
    messages.value[aiMessageIndex].thinking = false
    messages.value[aiMessageIndex].text = '抱歉，系统出现了一些问题。请稍后再试。'
    isTyping.value = false
  }
}

const sendSuggestion = (suggestion) => {
  inputMessage.value = suggestion
  sendMessage()
}

const clearChat = () => {
  messages.value = []
  currentSessionId.value = ''
}
</script>
