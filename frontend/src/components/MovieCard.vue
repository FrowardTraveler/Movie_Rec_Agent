<template>
  <div 
    class="movie-card group cursor-pointer"
    @click="handleClick"
  >
    <div class="relative aspect-[2/3] bg-gray-100">
      <!-- 电影海报 -->
      <img
        v-if="movie.poster && !showPlaceholder"
        :src="movie.poster"
        :alt="movie.title"
        class="w-full h-full object-cover"
        loading="lazy"
        @error="showPlaceholder = true"
      />

      <!-- 占位符（无海报时） -->
      <div
        v-if="!movie.poster || showPlaceholder"
        class="absolute inset-0 flex flex-col items-center justify-center bg-gradient-to-br from-gray-200 to-gray-300"
      >
        <svg class="w-12 h-12 text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 4v16M17 4v16M3 8h4m10 0h4M3 12h18M3 16h4m10 0h4M4 20h16a1 1 0 001-1V5a1 1 0 00-1-1H4a1 1 0 00-1 1v14a1 1 0 001 1z" />
        </svg>
        <span v-if="movie.title_en" class="text-xs text-gray-500 px-2 text-center line-clamp-2">{{ movie.title_en }}</span>
      </div>

      <!-- IMDB 链接标签（当无海报时） -->
      <a
        v-if="(!movie.poster || showPlaceholder) && movie.imdb_url"
        :href="movie.imdb_url"
        target="_blank"
        rel="noopener noreferrer"
        class="absolute top-2 right-2 px-2 py-1 bg-yellow-500 text-white text-xs rounded-full font-medium hover:bg-yellow-600 transition-colors z-10"
        @click.stop
      >
        IMDb 🔍
      </a>

      <!-- 悬停遮罩 -->
      <div class="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity duration-300 flex flex-col justify-end p-3">
        <h3 class="text-white text-sm font-semibold line-clamp-2 mb-1">
          {{ movie.title }}
        </h3>
        <div class="flex items-center justify-between text-xs">
          <span v-if="movie.year" class="text-gray-300">{{ movie.year }}</span>
          <div v-if="movie.rating" class="flex items-center space-x-1">
            <svg class="w-4 h-4 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
              <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
            </svg>
            <span class="text-white font-medium">{{ movie.rating.toFixed(1) }}</span>
          </div>
        </div>
        <div v-if="movie.genres" class="mt-2 flex flex-wrap gap-1">
          <span
            v-for="genre in getGenresArray(movie.genres)"
            :key="genre"
            class="text-xs px-2 py-0.5 bg-white/20 rounded-full text-white"
          >
            {{ genre }}
          </span>
        </div>
      </div>
    </div>

    <!-- 底部信息 -->
    <div class="p-2">
      <h4 class="text-sm font-medium text-gray-900 truncate">{{ movie.title }}</h4>
      <div class="flex items-center justify-between mt-1">
        <span v-if="movie.year" class="text-xs text-gray-500">{{ movie.year }}</span>
        <span v-if="movie.rating" class="text-xs text-yellow-600 font-medium">
          ★ {{ movie.rating.toFixed(1) }}
        </span>
      </div>
      <!-- IMDB 链接（底部展示） -->
      <a
        v-if="movie.imdb_url"
        :href="movie.imdb_url"
        target="_blank"
        rel="noopener noreferrer"
        class="block mt-1 text-xs text-blue-600 hover:underline truncate"
        @click.stop
      >
        🔍 在 IMDb 上搜索
      </a>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { recordEvent } from '../services/api.js'

const props = defineProps({
  movie: {
    type: Object,
    required: true,
  },
  userId: {
    type: String,
    default: '',
  },
  query: {
    type: String,
    default: '',
  },
  strategy: {
    type: String,
    default: 'llm_only',
  },
  sessionId: {
    type: String,
    default: '',
  },
  recommendedMovies: {
    type: Array,
    default: () => [],
  },
})

const showPlaceholder = ref(false)

const getGenresArray = (genres) => {
  if (!genres) return []
  if (Array.isArray(genres)) return genres
  if (typeof genres === 'string') return genres.split(/[,、]/).map(g => g.trim())
  return []
}

const handleClick = async () => {
  // 如果电影不在数据库中（movie_id=0），且有 IMDB 链接，直接打开 IMDB
  if (props.movie.movie_id === 0 && props.movie.imdb_url) {
    window.open(props.movie.imdb_url, '_blank')
    return
  }
  
  await recordEvent({
    user_id: props.userId,
    event_type: 'click',
    movie_id: props.movie.id || props.movie.movie_id,
    query: props.query,
    recommended_movies: props.recommendedMovies,
    strategy: props.strategy,
    session_id: props.sessionId,
  })
}
</script>
