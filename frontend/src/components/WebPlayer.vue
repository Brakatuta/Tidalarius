<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { playerStore } from '../playerStore.js'
import MarqueeText from './MarqueeText.vue'

const audioRef = ref(null)

const displayQuality = computed(() => {
    if (!playerStore.currentTrack) return ''
    const q = playerStore.currentTrack.quality
    if (q && q !== 'TIDAL') {
        return q === 'HI_RES_LOSSLESS' ? 'MAX' : q
    }
    const streamQ = localStorage.getItem('streamQuality') || 'HIGH'
    return streamQ === 'HI_RES_LOSSLESS' ? 'MAX' : streamQ
})

const getQualityClasses = (quality) => {
    switch (quality) {
        case 'LOW': return 'bg-green-900/40 text-green-400 border border-green-700/50'
        case 'HIGH': return 'bg-info-20 text-info-light border border-info-30'
        case 'LOSSLESS': return 'bg-warning-20 text-warning border border-warning-30'
        case 'MAX':
        case 'HI_RES_LOSSLESS': return 'bg-purple-900/40 text-purple-400 border border-purple-500/50'
        case 'YOUTUBE': return 'bg-pink-900/40 text-pink-400 border border-pink-500/50'
        default: return 'bg-surface-elevated text-text-secondary border border-border-strong'
    }
}
const currentTime = ref(0)
const duration = ref(0)
const volume = ref(0.8)

watch(() => playerStore.currentTrack, (newTrack) => {
    if (newTrack && newTrack.stream_url && audioRef.value) {
        audioRef.value.src = newTrack.stream_url
        if (playerStore.isPlaying) {
            audioRef.value.play().catch(e => console.error("Playback failed", e))
        }
        
        if ('mediaSession' in navigator) {
            navigator.mediaSession.metadata = new MediaMetadata({
                title: newTrack.title,
                artist: newTrack.artist,
                album: newTrack.album,
                artwork: newTrack.picture_url ? [{ src: newTrack.picture_url, sizes: '320x320', type: 'image/jpeg' }] : []
            });
            navigator.mediaSession.setActionHandler('play', () => playerStore.togglePlayPause());
            navigator.mediaSession.setActionHandler('pause', () => playerStore.togglePlayPause());
            navigator.mediaSession.setActionHandler('previoustrack', () => playerStore.previous());
            navigator.mediaSession.setActionHandler('nexttrack', () => playerStore.next());
        }
    }
}, { immediate: true })

watch(() => playerStore.isPlaying, (isPlaying) => {
    if (audioRef.value) {
        if (isPlaying) {
            audioRef.value.play().catch(e => console.error("Playback failed", e))
        } else {
            audioRef.value.pause()
        }
    }
})

const isMuted = ref(false)
const previousVolume = ref(0.8)

watch(volume, (newVol) => {
    if (newVol > 0 && isMuted.value) {
        isMuted.value = false
    } else if (newVol === 0 && !isMuted.value) {
        isMuted.value = true
    }
    
    if (audioRef.value) {
        audioRef.value.volume = newVol
    }
})

const toggleMute = () => {
    if (isMuted.value) {
        isMuted.value = false
        volume.value = previousVolume.value
    } else {
        isMuted.value = true
        previousVolume.value = volume.value
        volume.value = 0
    }
}

const onTimeUpdate = () => {
    if (audioRef.value) {
        currentTime.value = audioRef.value.currentTime
        duration.value = audioRef.value.duration || playerStore.currentTrack?.duration || 0
    }
}

const onEnded = () => {
    playerStore.next()
}

const onError = (e) => {
    console.error("Audio playback error:", e)
    
    // Attempt fallback for local file error (e.g. unsupported FLAC in Safari)
    if (playerStore.currentTrack && playerStore.currentTrack.stream_url) {
        const url = playerStore.currentTrack.stream_url;
        
        if (url.startsWith('/music_files/')) {
            console.log("Local file playback failed, falling back to Tidal stream...");
            playerStore.currentTrack.stream_url = `/api/music/stream/${playerStore.currentTrack.id}?quality=HIGH`;
            if (audioRef.value) {
                audioRef.value.src = playerStore.currentTrack.stream_url;
                audioRef.value.play().catch(err => console.error("Fallback to stream failed", err));
            }
            return;
        }

        // Attempt frontend quality fallback for unsupported stream formats (e.g. FLAC on iOS Safari)
        let newQuality = null;
        if (url.includes('quality=HI_RES_LOSSLESS') || url.includes('quality=MAX')) {
            newQuality = 'LOSSLESS';
        } else if (url.includes('quality=LOSSLESS')) {
            newQuality = 'HIGH';
        } else if (url.includes('quality=HIGH')) {
            newQuality = 'LOW';
        }
        
        if (newQuality) {
            console.log(`Fallback: Retrying playback with quality=${newQuality}`);
            playerStore.currentTrack.stream_url = url.replace(/quality=[A-Z_]+/, `quality=${newQuality}`);
            if (audioRef.value) {
                audioRef.value.src = playerStore.currentTrack.stream_url;
                audioRef.value.play().catch(err => console.error("Fallback playback failed", err));
            }
            return;
        }
    }
    
    console.error("All qualities failed or unrecoverable error. Skipping to next track in 1.5s.")
    setTimeout(() => {
        if (playerStore.isPlaying) playerStore.next()
    }, 1500)
}

const seek = (e) => {
    if (audioRef.value && duration.value) {
        const time = (e.target.value / 100) * duration.value
        audioRef.value.currentTime = time
    }
}

const progressStyle = computed(() => {
    const percent = duration.value ? (currentTime.value / duration.value) * 100 : 0
    return {
        background: `linear-gradient(to right, var(--color-accent) 0%, var(--color-accent) ${percent}%, var(--color-surface-elevated) ${percent}%, var(--color-surface-elevated) 100%)`
    }
})

const volumeStyle = computed(() => {
    const percent = volume.value * 100
    return {
        background: `linear-gradient(to right, var(--color-accent) 0%, var(--color-accent) ${percent}%, var(--color-surface-elevated) ${percent}%, var(--color-surface-elevated) 100%)`
    }
})

const formatTime = (seconds) => {
    if (isNaN(seconds)) return "0:00"
    const m = Math.floor(seconds / 60)
    const s = Math.floor(seconds % 60)
    return `${m}:${s.toString().padStart(2, '0')}`
}
</script>

<template>
  <div class="fixed bottom-0 left-0 right-0 h-20 md:h-24 bg-background border-t border-border-subtle shadow-[0_-10px_30px_rgba(0,0,0,0.5)] flex items-center justify-between px-2 md:px-4 z-50">
      
      <audio ref="audioRef" @timeupdate="onTimeUpdate" @ended="onEnded" @error="onError" :volume="volume"></audio>
      
      <!-- Left: Track Info -->
      <div class="w-1/2 md:w-1/3 flex items-center gap-2 md:gap-4 truncate">
          <template v-if="playerStore.currentTrack">
              <img v-if="playerStore.currentTrack.picture_url" :src="playerStore.currentTrack.picture_url" class="w-12 h-12 md:w-14 md:h-14 rounded shadow object-cover flex-shrink-0" />
              <div class="w-12 h-12 md:w-14 md:h-14 rounded bg-surface flex items-center justify-center border border-border-strong flex-shrink-0" v-else>
                  <svg class="w-6 h-6 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"></path></svg>
              </div>
              <div class="flex flex-col truncate max-w-full">
                  <div class="flex items-center mb-0.5">
                      <span class="px-1.5 py-0.5 rounded text-[8px] md:text-[10px] font-mono font-bold tracking-wider leading-none" 
                          :class="getQualityClasses(displayQuality)">
                          {{ displayQuality }}
                      </span>
                  </div>
                  <MarqueeText :text="playerStore.currentTrack.title" class="text-text-primary font-medium text-sm md:text-base hover:underline cursor-pointer" />
                  <span class="text-xs text-text-muted hover:underline cursor-pointer truncate">{{ playerStore.currentTrack.artist }}</span>
              </div>
          </template>
      </div>
      
      <!-- Center: Controls -->
      <div class="w-1/2 md:w-1/3 flex flex-col items-center justify-center">
          <div class="flex items-center gap-2 md:gap-6 md:mb-2">
              <button @click="playerStore.toggleShuffle()" class="hidden md:block" :class="playerStore.isShuffle ? 'text-accent hover:text-accent-light' : 'text-text-muted hover:text-text-primary'">
                  <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z"/></svg>
              </button>
              
              <button @click="playerStore.previous()" class="text-text-muted hover:text-text-primary transition">
                  <svg class="w-6 h-6 md:w-6 md:h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M6 6h2v12H6zm3.5 6l8.5 6V6z"/></svg>
              </button>
              
              <button @click="playerStore.togglePlayPause()" class="text-text-muted hover:text-text-primary transition mx-1 md:mx-2">
                  <svg v-if="playerStore.isPlaying" class="w-8 h-8 md:w-8 md:h-8" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                  <svg v-else class="w-8 h-8 md:w-8 md:h-8" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
              </button>
              
              <button @click="playerStore.next()" class="text-text-muted hover:text-text-primary transition">
                  <svg class="w-6 h-6 md:w-6 md:h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z"/></svg>
              </button>
          </div>
          
          <div class="flex items-center gap-1 md:gap-2 w-[160px] sm:w-[250px] md:w-full max-w-md mt-2 md:mt-0">
              <span class="text-xs text-text-muted w-10 text-right tabular-nums">{{ formatTime(currentTime) }}</span>
              <input type="range" min="0" :max="100" :value="duration ? (currentTime / duration) * 100 : 0" @input="seek"
                     class="w-full h-1.5 rounded-lg appearance-none cursor-pointer slider-thumb-accent" :style="progressStyle">
              <span class="text-xs text-text-muted w-10 tabular-nums">{{ formatTime(duration) }}</span>
          </div>
          
          
      </div>
      
      <!-- Right: Quality & Volume -->
      <div class="hidden md:flex w-1/3 items-center justify-end gap-4 pr-2">
          <div class="flex items-center gap-3 w-40 mt-8">
              <button @click="toggleMute()" class="text-text-muted hover:text-text-primary transition-colors">
                  <svg v-if="isMuted || volume === 0" class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M16.5 12c0-1.77-1.02-3.29-2.5-4.03v2.21l2.45 2.45c.03-.2.05-.41.05-.63zm2.5 0c0 .94-.2 1.82-.54 2.64l1.51 1.51C20.63 14.91 21 13.5 21 12c0-4.28-2.99-7.86-7-8.77v2.06c2.89.86 5 3.54 5 6.71zM4.27 3L3 4.27 7.73 9H3v6h4l5 5v-6.73l4.25 4.25c-.67.52-1.42.93-2.25 1.18v2.06c1.38-.31 2.63-.95 3.69-1.81L19.73 21 21 19.73l-9-9L4.27 3zM12 4L9.91 6.09 12 8.18V4z"/></svg>
                  <svg v-else class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/></svg>
              </button>
              <input type="range" min="0" max="1" step="0.01" v-model.number="volume" 
                     class="w-full h-1.5 rounded-lg appearance-none cursor-pointer slider-thumb-accent" :style="volumeStyle">
              <span class="text-xs text-text-muted w-8 tabular-nums">{{ Math.round(volume * 100) }}%</span>
          </div>
      </div>
  </div>
</template>

