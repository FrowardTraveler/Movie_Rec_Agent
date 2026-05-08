<template>
  <div
    class="message-bubble animate-slide-up"
    :class="isUser ? 'message-user' : 'message-agent'"
  >
    <div class="flex items-start space-x-2">
      <!-- 头像 -->
      <div
        class="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold"
        :class="isUser ? 'bg-primary-500 text-white' : 'bg-gray-200 text-gray-600'"
      >
        {{ isUser ? '你' : 'AI' }}
      </div>

      <!-- 消息内容 -->
      <div class="flex-1 min-w-0">
        <!-- 思考过程 -->
        <div v-if="message.thinkingSteps && message.thinkingSteps.length" class="mb-3">
          <div 
            @click="showThinking = !showThinking" 
            class="cursor-pointer select-none"
          >
            <span class="text-xs text-gray-500 inline-flex items-center space-x-1">
              <svg 
                class="w-3 h-3 transform transition-transform" 
                :class="{ 'rotate-90': showThinking }"
                fill="none" 
                stroke="currentColor" 
                viewBox="0 0 24 24"
              >
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path>
              </svg>
              <span>{{ showThinking ? '收起思考过程' : '查看思考过程' }}</span>
              <span class="text-gray-400">({{ message.thinkingSteps.length }} 步)</span>
            </span>
          </div>
          
          <!-- 展开的思考过程 -->
          <div v-if="showThinking" class="mt-2 p-3 bg-gray-50 rounded-lg text-xs font-mono space-y-1 max-h-64 overflow-y-auto">
            <div 
              v-for="(step, index) in message.thinkingSteps" 
              :key="index"
              class="flex items-start space-x-2"
              :class="{
                'text-blue-600': step.type === 'thinking',
                'text-green-600': step.type === 'agent_success',
                'text-red-600': step.type === 'agent_error',
                'text-orange-600': step.type === 'agent_start',
                'text-purple-600': step.type === 'done',
              }"
            >
              <span class="text-gray-400">{{ index + 1 }}.</span>
              <span>{{ step.content }}</span>
            </div>
          </div>
        </div>

        <!-- 文本消息 -->
        <p class="text-sm whitespace-pre-wrap">{{ message.text }}</p>

        <!-- 电影推荐结果 -->
        <div v-if="message.movies && message.movies.length" class="mt-3">
          <p class="text-xs font-medium text-gray-500 mb-2">
            为你推荐 {{ message.movies.length }} 部电影：
          </p>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <MovieCard
              v-for="(movie, idx) in message.movies"
              :key="movie.id || idx"
              :movie="movie"
              :user-id="message.userId || ''"
              :query="message.query || ''"
              :strategy="message.strategy || 'llm_only'"
              :session-id="message.sessionId || ''"
              :recommended-movies="message.movies.map(m => m.id || m.movie_id)"
            />
          </div>
        </div>

        <!-- 搜索结果 -->
        <div v-if="message.searchResults && message.searchResults.length" class="mt-3">
          <p class="text-xs font-medium text-gray-500 mb-2">
            找到 {{ message.searchResults.length }} 部相关电影：
          </p>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
            <MovieCard
              v-for="movie in message.searchResults"
              :key="movie.id"
              :movie="movie"
              :user-id="message.userId || ''"
              :query="message.query || ''"
              :strategy="message.strategy || 'llm_only'"
              :session-id="message.sessionId || ''"
              :recommended-movies="message.searchResults.map(m => m.id || m.movie_id)"
            />
          </div>
        </div>

        <!-- 延迟信息 -->
        <p v-if="message.latency_ms" class="text-xs text-gray-400 mt-2">
          响应时间: {{ message.latency_ms }}ms
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import MovieCard from './MovieCard.vue'

const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
  isUser: {
    type: Boolean,
    default: false,
  },
})

const showThinking = ref(false)
</script>
