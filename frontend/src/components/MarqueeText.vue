<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'

const props = defineProps({
  text: {
    type: String,
    default: ''
  },
  speed: {
    type: Number,
    default: 25 // pixels per second
  },
  pauseTime: {
    type: Number,
    default: 2 // seconds to pause at start and end
  }
})

const containerRef = ref(null)
const contentRef = ref(null)
const isOverflowing = ref(false)
const distance = ref(0)
const duration = ref(6)

const updateOverflow = () => {
  if (!containerRef.value || !contentRef.value) return
  const containerWidth = containerRef.value.clientWidth
  const contentWidth = contentRef.value.scrollWidth
  
  if (contentWidth > containerWidth + 4) {
    isOverflowing.value = true
    const dist = contentWidth - containerWidth
    distance.value = dist
    const scrollTime = dist / props.speed
    duration.value = Math.max(5, (props.pauseTime * 2) + (scrollTime * 2))
  } else {
    isOverflowing.value = false
    distance.value = 0
  }
}

const marqueeStyle = computed(() => {
  return {
    '--marquee-dist': `-${distance.value}px`,
    '--marquee-duration': `${duration.value}s`
  }
})

let resizeObserver = null

onMounted(() => {
  nextTick(() => {
    updateOverflow()
  })
  if (window.ResizeObserver && containerRef.value) {
    resizeObserver = new ResizeObserver(() => {
      updateOverflow()
    })
    resizeObserver.observe(containerRef.value)
  }
})

watch(() => props.text, () => {
  nextTick(() => {
    updateOverflow()
  })
})

onUnmounted(() => {
  if (resizeObserver) {
    resizeObserver.disconnect()
  }
})
</script>

<template>
  <div ref="containerRef" class="marquee-container overflow-hidden whitespace-nowrap relative" :title="text">
    <div 
      ref="contentRef" 
      class="marquee-content inline-block"
      :class="{ 'animate-marquee': isOverflowing }"
      :style="isOverflowing ? marqueeStyle : {}"
    >
      <slot>{{ text }}</slot>
    </div>
  </div>
</template>

<style scoped>
@keyframes marquee-pingpong {
  0%, 20% {
    transform: translateX(0);
  }
  50%, 70% {
    transform: translateX(var(--marquee-dist, 0px));
  }
  100% {
    transform: translateX(0);
  }
}

.animate-marquee {
  animation: marquee-pingpong var(--marquee-duration, 8s) ease-in-out infinite;
  will-change: transform;
}

.marquee-container:hover .animate-marquee {
  animation-play-state: paused;
}
</style>

