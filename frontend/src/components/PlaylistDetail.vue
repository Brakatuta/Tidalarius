<script setup>
import { ref, onMounted, computed, watch } from 'vue'
import { playerStore } from '../playerStore.js'
import { syncStore } from '../syncStore.js'

const props = defineProps({
    playlist: {
        type: Object,
        required: true
    }
})

const emit = defineEmits(['back'])

const playlistData = ref(null)
const loading = ref(true)
const searchQuery = ref('')
const error = ref(null)

const scheduleModalOpen = ref(false)
const syncModalOpen = ref(false)
const deleteModalOpen = ref(false)
const saving = ref(false)
const isDeleting = ref(false)
const qualityOptions = ['LOW', 'HIGH', 'LOSSLESS', 'HI_RES_LOSSLESS']
const streamQuality = ref(localStorage.getItem('streamQuality') || 'HIGH')

watch(streamQuality, (newQ) => {
    localStorage.setItem('streamQuality', newQ)
    if (playlistData.value && playlistData.value.tracks) {
        playlistData.value.tracks.forEach(t => {
            if (!t.is_downloaded && t.stream_url && t.stream_url.includes('/api/music/stream/')) {
                const baseUrl = t.stream_url.split('?')[0]
                t.stream_url = `${baseUrl}?quality=${newQ}`
            }
        })
    }
})
const commonSchedules = [
  { label: 'Never (Manual Only)', value: null },
  { label: 'Every hour', value: '0 * * * *' },
  { label: 'Every 6 hours', value: '0 */6 * * *' },
  { label: 'Every 12 hours', value: '0 */12 * * *' },
  { label: 'Daily at midnight', value: '0 0 * * *' },
  { label: 'Daily at 3 AM', value: '0 3 * * *' },
  { label: 'Weekly', value: '0 0 * * 0' },
]

const deleteDownloads = async () => {
    isDeleting.value = true
    try {
        const res = await fetch(`/api/sync/delete/${props.playlist.tidal_id}`, { method: 'DELETE' })
        if (res.ok) {
            // refresh data
            fetchDetailsSilent()
        }
    } catch (e) {
        console.error("Delete failed", e)
    } finally {
        isDeleting.value = false
        deleteModalOpen.value = false
    }
}

const downloadSingleTrack = async (trackId) => {
    try {
        await fetch(`/api/sync/track/${props.playlist.tidal_id}/${trackId}`, { method: 'POST' })
        // Optimistically we could update, but the daemon handles it. 
        // Sync status will eventually reflect it.
    } catch (e) {
        console.error("Failed to start track download", e)
    }
}

const trackToDelete = ref(null)
const trackDeleteModalOpen = ref(false)

const confirmDeleteSingleTrack = (track) => {
    trackToDelete.value = track
    trackDeleteModalOpen.value = true
}

const executeDeleteSingleTrack = async () => {
    if (!trackToDelete.value) return
    const trackId = trackToDelete.value.id
    playerStore.removeTrack(trackId)
    try {
        const res = await fetch(`/api/sync/track/${props.playlist.tidal_id}/${trackId}`, {
            method: 'DELETE'
        })
        if (res.ok) {
            fetchDetailsSilent()
        }
    } catch (e) {
        console.error("Failed to delete track", e)
    } finally {
        trackDeleteModalOpen.value = false
        trackToDelete.value = null
    }
}


const collageImages = computed(() => {
    if (!playlistData.value) return []
    const urls = playlistData.value.tracks
        .map(t => t.picture_url)
        .filter(url => url)
    return [...new Set(urls)].slice(0, 10)
})

const applyStreamQuality = () => {
    if (playlistData.value && playlistData.value.tracks) {
        playlistData.value.tracks.forEach(t => {
            if (!t.is_downloaded && t.stream_url && t.stream_url.includes('/api/music/stream/')) {
                const baseUrl = t.stream_url.split('?')[0]
                t.stream_url = `${baseUrl}?quality=${streamQuality.value}`
            }
        })
    }
}

const fetchDetails = async () => {
    loading.value = true
    error.value = null
    try {
        const res = await fetch(`/api/music/playlist/${props.playlist.tidal_id}`)
        if (res.ok) {
            playlistData.value = await res.json()
            applyStreamQuality()
            syncStore.fetchStatus(props.playlist.tidal_id)
        } else {
            const data = await res.json()
            error.value = data.detail || 'Failed to load playlist details'
        }
    } catch (e) {
        error.value = "Failed to fetch playlist details"
        console.error(e)
    } finally {
        loading.value = false
    }
}

onMounted(() => {
    fetchDetails()
})

const filteredTracks = computed(() => {
    if (!playlistData.value || !playlistData.value.tracks) return []
    if (!searchQuery.value) return playlistData.value.tracks
    
    // Split search query into individual words (lowercase)
    const terms = searchQuery.value.toLowerCase().split(' ').filter(t => t.trim() !== '')
    
    return playlistData.value.tracks.filter(t => {
        // Create a combined string of all searchable fields
        const combined = `${t.title} ${t.artist} ${t.album}`.toLowerCase()
        // The track matches if ALL search terms are found somewhere in the combined string
        return terms.every(term => combined.includes(term))
    })
})

const getQualityClasses = (quality) => {
    switch (quality) {
        case 'LOW': return 'bg-green-900/40 text-green-400 border border-green-700/50'
        case 'HIGH': return 'bg-info-20 text-info-light border border-info-30'
        case 'LOSSLESS': return 'bg-warning-20 text-warning border border-warning-30'
        case 'HI_RES_LOSSLESS': return 'bg-purple-900/40 text-purple-400 border border-purple-500/50'
        case 'YOUTUBE': return 'bg-pink-900/40 text-pink-400 border border-pink-500/50'
        default: return 'bg-surface-elevated text-text-secondary border border-border-strong'
    }
}

const formatTime = (seconds) => {
    if (!seconds) return "0:00"
    const m = Math.floor(seconds / 60)
    const s = Math.floor(seconds % 60)
    return `${m}:${s.toString().padStart(2, '0')}`
}

const expandedTrackId = ref(null)
const mobileDownloadTrack = ref(null)
const mobileDownloadModalOpen = ref(false)

const handleMobileDownload = () => {
    if (mobileDownloadTrack.value) {
        downloadSingleTrack(mobileDownloadTrack.value.id)
        mobileDownloadModalOpen.value = false
    }
}

const playTrack = (track) => {
    const isMobile = window.innerWidth < 768;
    
    if (isMobile) {
        expandedTrackId.value = expandedTrackId.value === track.id ? null : track.id;
    }

    if (!track.stream_url) return
    const idx = playlistData.value.tracks.findIndex(t => t.id === track.id)
    playerStore.playPlaylist(playlistData.value.tidal_id, playlistData.value.name, playlistData.value.tracks, idx)
}

const togglePlayPlaylist = () => {
    if (playerStore.currentPlaylistId === props.playlist.tidal_id) {
        playerStore.togglePlayPause()
    } else {
        const playableTrack = playlistData.value.tracks.find(t => t.is_downloaded)
        if (playableTrack) {
            playTrack(playableTrack)
        }
    }
}

const saveConfig = async () => {
  saving.value = true
  try {
    const payload = {
      sync_enabled: props.playlist.sync_enabled,
      qualities: props.playlist.qualities,
      schedule: props.playlist.schedule
    }
    
    const res = await fetch(`/api/playlists/${props.playlist.tidal_id}/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
    
    if (!res.ok) throw new Error("Failed to save config")
  } catch (e) {
    console.error(e)
    alert("Error saving playlist configuration")
  } finally {
    saving.value = false
  }
}

const toggleSync = async () => {
  props.playlist.sync_enabled = !props.playlist.sync_enabled
  await saveConfig()
}

const getSyncStatus = computed(() => {
    return syncStore.syncState[props.playlist.tidal_id] || { status: props.playlist.sync_status || 'idle' }
})

watch(() => syncStore.lastDownloadedTrack, (newTrack) => {
    if (newTrack && newTrack.playlist_id === props.playlist.tidal_id && playlistData.value) {
        const track = playlistData.value.tracks.find(t => t.title === newTrack.track_name)
        if (track) {
            track.is_downloaded = true
            track.quality = newTrack.quality
            fetchDetailsSilent()
        }
    }
})

watch(() => syncStore.trackDeleted, (delEvent) => {
    if (delEvent && delEvent.playlist_id === props.playlist.tidal_id && playlistData.value) {
        const track = playlistData.value.tracks.find(t => t.id === delEvent.track_id)
        if (track) {
            track.is_downloaded = false
            playerStore.removeTrack(delEvent.track_id)
            fetchDetailsSilent()
        }
    }
})

const fetchDetailsSilent = async () => {
    try {
        const res = await fetch(`/api/music/playlist/${props.playlist.tidal_id}`)
        if (res.ok) {
            playlistData.value = await res.json()
            applyStreamQuality()
        }
    } catch (e) {
        // ignore
    }
}

</script>

<template>
  <div class="w-full flex flex-col bg-background rounded-xl overflow-hidden shadow-2xl border border-border-subtle relative">
      
      <div v-if="loading" class="flex flex-col items-center justify-center p-24">
          <svg class="animate-spin h-12 w-12 text-accent mb-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <span class="text-text-muted">Loading tracks...</span>
      </div>
      
      <div v-else-if="error" class="p-12 text-center">
          <button @click="emit('back')" class="text-text-muted hover:text-text-primary mb-4 block">← Back to Library</button>
          <div class="bg-red-900/50 border border-danger text-red-200 p-4 rounded inline-block">
              {{ error }}
          </div>
      </div>
      
      <template v-else-if="playlistData">
          <!-- Header -->
          <div class="relative p-6 md:p-8 flex flex-col md:flex-row items-center md:items-end gap-6 border-b border-border-subtle overflow-hidden min-h-[300px]">
              <!-- Background Collage -->
              <div class="absolute inset-[-10%] z-0 flex flex-wrap justify-center items-center opacity-70">
                  <div v-for="(img, idx) in collageImages" :key="idx" 
                       class="w-1/3 md:w-1/4 lg:w-1/5 aspect-square"
                       :style="{
                           backgroundImage: `url(${img})`,
                           backgroundSize: 'cover',
                           backgroundPosition: 'center',
                           transform: `rotate(${(idx * 27) % 40 - 20}deg) scale(1.4)`,
                           boxShadow: '0 10px 30px rgba(0,0,0,0.5)'
                       }">
                  </div>
              </div>
              <div class="absolute inset-0 bg-background/60 backdrop-blur-3xl z-0"></div>
              
              <button @click="emit('back')" class="absolute top-4 left-4 p-2 bg-black-base/30 hover:bg-black-base/50 text-text-primary rounded-full transition-colors backdrop-blur z-10">
                  <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
              </button>
              
              <div class="relative z-10 w-48 h-48 md:w-64 md:h-64 shadow-2xl flex-shrink-0 mt-8 md:mt-0 mx-auto md:mx-0">
                  <img v-if="playlistData.picture_url" :src="playlistData.picture_url" class="w-full h-full object-cover rounded border border-white-base/10" />
                  <div v-else class="w-full h-full bg-surface flex items-center justify-center rounded border border-border-strong">
                      <svg class="w-16 h-16 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"></path></svg>
                  </div>
              </div>
              
              <div class="relative z-10 flex-grow text-text-primary w-full text-center md:text-left">
                  <div class="flex justify-between items-start w-full">
                      <div>
                          <span class="text-xs font-bold uppercase tracking-widest text-text-secondary">Playlist</span>
                          <h1 class="text-4xl md:text-7xl font-extrabold mb-2 line-clamp-2 leading-tight">{{ playlistData.name }}</h1>
                          <p class="text-sm text-text-secondary mb-6">
                              <span class="font-semibold">{{ playlistData.tracks.filter(t => t.is_downloaded).length }} tracks</span> downloaded of {{ playlistData.tracks.length }} total
                          </p>
                      </div>
                  </div>
                  
                  <!-- Sync Configuration inside Header -->
                  <div class="flex flex-col xl:flex-row items-start xl:items-center justify-between gap-4 bg-surface-80 p-3 rounded-lg border border-border-highlight w-full backdrop-blur shadow-inner">
                    <div class="flex flex-col md:flex-row gap-4">
                      <!-- Quality Select -->
                      <div class="flex flex-col">
                        <label class="text-xs text-text-muted mb-1 uppercase tracking-wide">Download Quality Priority</label>
                        <div class="flex flex-wrap gap-2">
                          <label v-for="q in qualityOptions" :key="q" class="flex items-center gap-1 text-sm cursor-pointer text-text-secondary whitespace-nowrap">
                            <input type="checkbox" :value="q" v-model="playlist.qualities" @change="saveConfig()" class="accent-accent bg-surface-elevated border-border-highlight rounded">
                            {{ q === 'HI_RES_LOSSLESS' ? 'MAX' : q }}
                          </label>
                        </div>
                      </div>
                      
                      <!-- Stream Quality Select -->
                      <div class="flex flex-col">
                        <label class="text-xs text-text-muted mb-1 uppercase tracking-wide">Stream Quality</label>
                        <select v-model="streamQuality" class="bg-surface-elevated border border-border-highlight rounded text-sm text-text-primary px-2 py-0.5 outline-none focus:border-accent appearance-none">
                            <option value="HI_RES_LOSSLESS">MAX</option>
                            <option value="LOSSLESS">LOSSLESS</option>
                            <option value="HIGH">HIGH</option>
                            <option value="LOW">LOW</option>
                        </select>
                      </div>
                    </div>
                    
                    <div class="flex items-center gap-4 ml-auto">
                      <!-- Sync Now Button -->
                      <div class="flex gap-2">
                        <button v-if="getSyncStatus.status === 'syncing' || getSyncStatus.status === 'queued' || getSyncStatus.status === 'paused'"
                                @click="syncModalOpen = true"
                                class="bg-surface-elevated hover:bg-gray-600 text-xs px-3 py-1.5 rounded text-text-primary font-bold flex items-center gap-2 cursor-pointer transition">
                          <span class="flex h-2 w-2 relative">
                            <span v-if="getSyncStatus.status !== 'paused'" class="animate-ping absolute inline-flex h-full w-full rounded-full bg-success-75"></span>
                            <span class="relative inline-flex rounded-full h-2 w-2" :class="getSyncStatus.status === 'paused' ? 'bg-warning' : 'bg-success'"></span>
                          </span>
                          <span v-if="getSyncStatus.status === 'paused'">Paused</span>
                          <span v-else>Syncing... ({{ getSyncStatus.progress }}%)</span>
                        </button>
                        <button v-else @click="syncStore.startManualSync(playlist.tidal_id)"
                                class="bg-info-dark hover:bg-info text-xs px-3 py-1.5 rounded text-text-primary font-bold transition">
                          Sync Now
                        </button>
                        <button v-if="getSyncStatus.status === 'idle'" @click="syncModalOpen = true" class="bg-surface hover:bg-surface-elevated text-text-muted hover:text-text-primary border border-border-strong text-xs px-2 py-1.5 rounded font-bold transition">
                          Logs
                        </button>
                        <button v-if="getSyncStatus.status === 'idle'" @click="deleteModalOpen = true" class="bg-danger hover:bg-danger-light text-text-primary border border-danger-30 text-xs px-2 py-1.5 rounded font-bold transition ml-2" title="Delete Downloaded Files">
                          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                        </button>
                      </div>
                      
                      <!-- Sync Toggle -->
                      <div class="flex items-center gap-2">
                        <span class="text-xs text-text-secondary">Auto-Sync</span>
                        <button @click="toggleSync()" 
                                class="relative inline-flex items-center h-6 rounded-full w-11 transition-colors focus:outline-none"
                                :class="playlist.sync_enabled ? 'bg-accent' : 'bg-gray-600'">
                          <span class="inline-block w-4 h-4 transform bg-white-base rounded-full transition-transform"
                                :class="playlist.sync_enabled ? 'translate-x-6' : 'translate-x-1'"></span>
                        </button>
                        <button @click="scheduleModalOpen = true" 
                                class="p-1 text-text-secondary hover:text-text-primary transition-colors"
                                title="Sync Schedule Settings">
                          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                        </button>
                      </div>
                    </div>
                  </div>
                  <!-- Progress Bar -->
                  <div v-if="getSyncStatus.status === 'syncing'" class="mt-2 h-1.5 w-full bg-surface-elevated rounded-full overflow-hidden">
                      <div class="h-full bg-accent transition-all duration-300" :style="`width: ${getSyncStatus.progress}%`"></div>
                  </div>
              </div>
          </div>
          
          <!-- Controls & Search -->
          <div class="p-6 bg-background flex justify-between items-center sticky top-0 z-10 border-b border-border-subtle-50 backdrop-blur bg-opacity-90">
              <button 
                  @click="togglePlayPlaylist()"
                  class="w-14 h-14 bg-accent rounded-full flex items-center justify-center text-text-inverse hover:bg-accent-light hover:scale-105 transition-all shadow-lg"
              >
                  <svg v-if="playerStore.currentPlaylistId === playlist.tidal_id && playerStore.isPlaying" class="w-7 h-7" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                  <svg v-else class="w-7 h-7 ml-1" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
              </button>
              
              <div class="relative w-64">
                  <div class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <svg class="w-4 h-4 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"></path></svg>
                  </div>
                  <input type="text" v-model="searchQuery" placeholder="Search in playlist..." class="bg-surface text-sm rounded-full pl-10 pr-4 py-2 w-full text-text-primary placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-accent border border-border-strong">
              </div>
          </div>
          
          <!-- Tracklist -->
          <div class="px-2 md:px-6 pb-6 bg-background flex-grow">
              <table class="w-full text-left text-sm text-text-muted">
                  <thead class="text-xs uppercase border-b border-border-subtle text-text-disabled sticky top-[104px] bg-background z-10">
                      <tr>
                          <th class="py-3 font-normal w-12 text-center">#</th>
                          <th class="py-3 font-normal">Title</th>
                          <th class="py-3 font-normal hidden md:table-cell">Album</th>
                          <th class="py-3 font-normal w-32 text-right pr-4 hidden md:table-cell">Quality</th>
                          <th class="py-3 font-normal w-16 text-right hidden md:table-cell"><svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg></th>
                      </tr>
                  </thead>
                  <tbody>
                      <template v-for="(track, index) in filteredTracks" :key="track.id">
                          <tr @click="playTrack(track)"
                              :class="[
                                  'group border-b border-border-subtle-50 hover:bg-surface-80 transition-colors',
                                  !track.is_downloaded ? 'opacity-70 cursor-pointer' : 'cursor-pointer',
                                  playerStore.currentTrack && playerStore.currentTrack.id === track.id ? 'bg-surface' : ''
                              ]">
                              <td class="py-3 text-center">
                                  <span v-if="playerStore.currentTrack && playerStore.currentTrack.id === track.id" class="text-accent">
                                      <svg class="w-4 h-4 inline" viewBox="0 0 24 24" fill="currentColor">
                                          <rect x="4" y="14" width="4" height="6" class="animate-pulse" />
                                          <rect x="10" y="8" width="4" height="12" class="animate-pulse" style="animation-delay: 0.2s" />
                                          <rect x="16" y="12" width="4" height="8" class="animate-pulse" style="animation-delay: 0.4s" />
                                      </svg>
                                  </span>
                                  <span v-else class="group-hover:hidden">{{ track.playlist_pos || (index + 1) }}</span>
                                  <svg v-if="!(playerStore.currentTrack && playerStore.currentTrack.id === track.id)" class="w-4 h-4 hidden group-hover:inline text-text-primary" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                              </td>
                              <td class="py-3">
                                  <div class="flex items-center gap-3">
                                      <img v-if="track.picture_url" :src="track.picture_url" class="w-10 h-10 rounded shadow object-cover bg-surface" />
                                      <div class="w-10 h-10 rounded bg-surface flex items-center justify-center" v-else>
                                          <svg class="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"></path></svg>
                                      </div>
                                      <div class="flex flex-col truncate pr-4 max-w-[200px] lg:max-w-xs">
                                          <span :class="['font-medium truncate', playerStore.currentTrack && playerStore.currentTrack.id === track.id ? 'text-accent' : 'text-text-primary']" :title="track.title">{{ track.title }}</span>
                                          <span class="text-xs text-text-muted hover:underline truncate" :title="track.artist">{{ track.artist }}</span>
                                      </div>
                                  </div>
                              </td>
                              <td class="py-3 hidden md:table-cell truncate pr-4 max-w-[150px] lg:max-w-[250px] hover:text-text-primary" :title="track.album">{{ track.album }}</td>
                              <td class="py-3 text-right pr-4 hidden md:table-cell">
                                  <div v-if="track.is_downloaded" class="flex items-center justify-end gap-2">
                                      <span class="px-2 py-0.5 rounded text-xs font-mono font-bold tracking-wider" 
                                          :class="getQualityClasses(track.quality)">
                                          {{ track.quality === 'HI_RES_LOSSLESS' ? 'MAX' : track.quality }}
                                      </span>
                                      <button @click.stop="confirmDeleteSingleTrack(track)" class="text-text-muted hover:text-danger transition-colors p-1 bg-surface hover:bg-surface-elevated rounded border border-border-strong" title="Delete this track">
                                          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                                      </button>
                                  </div>
                                  <div v-else class="flex items-center justify-end gap-2">
                                        <span class="text-xs text-danger-light border border-danger-30 bg-danger-darkest-20 px-2 py-0.5 rounded" title="Streams directly from Tidal">STREAM</span>
                                      <button @click.stop="downloadSingleTrack(track.id)" class="text-text-muted hover:text-accent transition-colors p-1 bg-surface hover:bg-surface-elevated rounded border border-border-strong" title="Download this track only">
                                          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                                      </button>
                                  </div>
                              </td>
                              <td class="py-3 text-right tabular-nums hidden md:table-cell">{{ formatTime(track.duration) }}</td>
                          </tr>
                          
                          <!-- Mobile Expanded Row -->
                          <tr v-if="expandedTrackId === track.id" class="md:hidden bg-surface-elevated border-b border-border-subtle-50">
                              <td colspan="5" class="py-3 px-4">
                                  <div class="flex justify-between items-center text-xs">
                                      <span class="text-text-muted">Duration: <span class="text-text-primary font-mono ml-1">{{ formatTime(track.duration) }}</span></span>
                                      <div class="flex items-center gap-2">
                                          <span class="text-text-muted">Quality:</span>
                                          <span v-if="track.is_downloaded" class="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold tracking-wider" 
                                              :class="getQualityClasses(track.quality)">
                                              {{ track.quality === 'HI_RES_LOSSLESS' ? 'MAX' : track.quality }}
                                          </span>
                                          <span v-else class="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold tracking-wider bg-danger-darkest-20 text-danger-light border border-danger-30">
                                              STREAM
                                          </span>
                                          
                                          <button v-if="track.is_downloaded" @click.stop="confirmDeleteSingleTrack(track)" class="text-text-muted hover:text-danger p-1 bg-surface rounded border border-border-strong" title="Delete this track">
                                              <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                                          </button>
                                          <button v-else @click.stop="mobileDownloadTrack = track; mobileDownloadModalOpen = true" class="text-text-muted hover:text-accent p-1 bg-surface rounded border border-border-strong" title="Download this track">
                                              <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                                          </button>
                                      </div>
                                  </div>
                              </td>
                          </tr>
                      </template>
                      <tr v-if="filteredTracks.length === 0">
                          <td colspan="5" class="py-12 text-center text-text-disabled">
                              No tracks found for "{{ searchQuery }}"
                          </td>
                      </tr>
                  </tbody>
              </table>
          </div>
      </template>

      <!-- Schedule Modal -->
      <div v-if="scheduleModalOpen" class="fixed inset-0 bg-black-base-base-base-80 flex items-center justify-center z-50 p-4">
        <div class="bg-surface rounded-xl shadow-2xl border border-border-strong w-full max-w-md overflow-hidden">
          <div class="bg-background p-4 border-b border-border-strong flex justify-between items-center">
            <h3 class="text-text-primary font-bold text-lg">Sync Schedule</h3>
            <button @click="scheduleModalOpen = false" class="text-text-muted hover:text-text-primary">
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>
          
          <div class="p-6">
            <p class="text-text-secondary text-sm mb-4">Set the synchronization schedule for <strong>{{ playlist.name }}</strong>.</p>
            
            <div class="space-y-4">
              <label class="block">
                <span class="text-text-muted text-sm">Preset Schedules</span>
                <select v-model="playlist.schedule" class="mt-1 block w-full bg-background border border-border-strong rounded-md text-text-primary px-3 py-2 focus:ring-accent focus:border-accent">
                  <option v-for="opt in commonSchedules" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                  <option value="custom">Custom Cron Expression</option>
                </select>
              </label>
              
              <label class="block" v-if="playlist.schedule && !commonSchedules.find(o => o.value === playlist.schedule)">
                <span class="text-text-muted text-sm">Custom Cron Expression</span>
                <input type="text" v-model="playlist.schedule" placeholder="* * * * *" class="mt-1 block w-full bg-background border border-border-strong rounded-md text-text-primary px-3 py-2 font-mono focus:ring-accent focus:border-accent">
                <p class="mt-1 text-xs text-text-disabled">Standard 5-part cron syntax.</p>
              </label>
            </div>
          </div>
          
          <div class="p-4 bg-background border-t border-border-strong flex justify-end gap-3">
            <button @click="scheduleModalOpen = false" class="px-4 py-2 text-sm text-text-muted hover:text-text-primary transition-colors">Cancel</button>
            <button @click="saveConfig(); scheduleModalOpen = false" class="px-4 py-2 bg-accent-dark hover:bg-accent text-text-primary rounded text-sm font-bold transition-colors">Save Schedule</button>
          </div>
        </div>
      </div>

      <!-- Sync Logs Modal -->
      <div v-if="syncModalOpen" class="fixed inset-0 bg-black-base-80 flex items-center justify-center z-50 p-4">
        <div class="bg-surface rounded-xl shadow-2xl border border-border-strong w-full max-w-3xl overflow-hidden flex flex-col h-[80vh]">
          <div class="bg-background p-4 border-b border-border-strong flex justify-between items-center">
            <h3 class="text-text-primary font-bold text-lg flex items-center gap-2">
              Sync Progress
              <span v-if="getSyncStatus.status === 'syncing'" class="text-xs bg-accent-dark-20 text-accent border border-accent-dark-50 px-2 py-0.5 rounded">RUNNING ({{ getSyncStatus.progress }}%)</span>
              <span v-else-if="getSyncStatus.status === 'paused'" class="text-xs bg-warning-20 text-warning border border-warning-30 px-2 py-0.5 rounded">PAUSED</span>
              <span v-else class="text-xs bg-surface-elevated text-text-muted border border-border-highlight px-2 py-0.5 rounded uppercase">{{ getSyncStatus.status }}</span>
            </h3>
            <button @click="syncModalOpen = false" class="text-text-muted hover:text-text-primary">
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>
          
          <div class="flex-grow p-4 bg-background overflow-y-auto font-mono text-xs text-text-secondary flex flex-col gap-1">
            <div v-for="(log, idx) in syncStore.syncLogs[playlist.tidal_id] || []" :key="idx" 
                 :class="{
                   'text-success': log.includes('SUCCESS'),
                   'text-danger-light': log.includes('FAILED') || log.includes('ERROR'),
                   'text-info-light': log.includes('Attempting')
                 }">
              {{ log }}
            </div>
            <div v-if="!(syncStore.syncLogs[playlist.tidal_id]?.length)" class="text-text-disabled italic">No logs available for this session.</div>
          </div>
          
          <div class="p-4 bg-background border-t border-border-strong flex justify-between gap-3">
            <div>
              <button v-if="getSyncStatus.status === 'syncing' || getSyncStatus.status === 'queued'" 
                      @click="syncStore.pauseSync(playlist.tidal_id)" 
                      class="px-4 py-2 bg-warning-dark-20 hover:bg-warning-dark-40 text-warning border border-warning-dark-50 rounded text-sm font-bold transition-colors">
                Pause
              </button>
              <button v-if="getSyncStatus.status === 'paused'" 
                      @click="syncStore.resumeSync(playlist.tidal_id)" 
                      class="px-4 py-2 bg-accent-dark-20 hover:bg-accent-dark-40 text-accent border border-accent-dark-50 rounded text-sm font-bold transition-colors">
                Resume
              </button>
              <a v-if="getSyncStatus.status === 'idle' || getSyncStatus.status === 'error'" 
                 :href="`/api/sync/report/latest/${playlist.tidal_id}`" target="_blank"
                 class="px-4 py-2 inline-block bg-info-dark-20 hover:bg-info-dark-40 text-info-light border border-info-dark-50 rounded text-sm font-bold transition-colors">
                Download Latest Log
              </a>
            </div>
            <div class="flex gap-3">
              <button v-if="getSyncStatus.status === 'syncing' || getSyncStatus.status === 'paused' || getSyncStatus.status === 'queued'" 
                      @click="syncStore.cancelSync(playlist.tidal_id)" 
                      class="px-4 py-2 bg-danger-dark/20 hover:bg-danger-dark/40 text-danger border border-red-600/50 rounded text-sm font-bold transition-colors">
                Stop Sync
              </button>
              <button @click="syncModalOpen = false" class="px-4 py-2 text-sm text-text-muted hover:text-text-primary bg-surface rounded transition-colors">Close</button>
            </div>
          </div>
        </div>
      </div>
      <!-- Delete Confirmation Modal -->
      <div v-if="deleteModalOpen" class="fixed inset-0 bg-black-base-80 flex items-center justify-center z-50 p-4">
        <div class="bg-surface rounded-xl shadow-2xl border border-danger-30 w-full max-w-md overflow-hidden">
          <div class="bg-background p-4 border-b border-border-strong flex justify-between items-center">
            <h3 class="text-danger font-bold text-lg">Confirm Deletion</h3>
            <button @click="deleteModalOpen = false" class="text-text-muted hover:text-text-primary">
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>
          <div class="p-6">
            <p class="text-text-primary font-medium mb-2">Are you sure you want to delete all downloaded files for <strong>{{ playlist.name }}</strong>?</p>
            <p class="text-text-secondary text-sm">This action cannot be undone. You will have to sync again to redownload the files.</p>
          </div>
          <div class="p-4 bg-background border-t border-border-strong flex justify-end gap-3">
            <button @click="deleteModalOpen = false" class="px-4 py-2 text-sm text-text-muted hover:text-text-primary transition-colors">Cancel</button>
            <button @click="deleteDownloads()" :disabled="isDeleting" class="px-4 py-2 bg-danger-dark hover:bg-danger text-text-primary rounded text-sm font-bold transition-colors disabled:opacity-50">
              {{ isDeleting ? 'Deleting...' : 'Yes, Delete' }}
            </button>
          </div>
        </div>
      </div>
      <!-- Mobile Download Modal -->
      <div v-if="mobileDownloadModalOpen" class="fixed inset-0 bg-black-base/80 flex items-center justify-center z-50 p-4 md:hidden">
        <div class="bg-surface rounded-xl shadow-2xl border border-border-strong w-full max-w-sm overflow-hidden text-center">
          <div class="p-6">
            <svg class="w-12 h-12 text-accent mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
            <h3 class="text-text-primary font-bold text-lg mb-2">Download Track?</h3>
            <p class="text-text-secondary text-sm mb-4">
              "{{ mobileDownloadTrack?.title }}" is not downloaded yet. Would you like to download it now?
            </p>
            <div class="flex gap-4">
              <button @click="mobileDownloadModalOpen = false" class="flex-1 bg-surface-elevated hover:bg-gray-600 text-text-primary font-bold py-2 rounded transition">Cancel</button>
              <button @click="handleMobileDownload" class="flex-1 bg-accent hover:bg-accent-light text-text-inverse font-bold py-2 rounded transition">Download</button>
            </div>
          </div>
        </div>
      </div>
      <!-- Single Track Delete Modal -->
      <div v-if="trackDeleteModalOpen" class="fixed inset-0 bg-black-base/80 flex items-center justify-center z-50 p-4">
        <div class="bg-surface rounded-xl shadow-2xl border border-border-strong w-full max-w-sm overflow-hidden text-center">
          <div class="p-6">
            <svg class="w-12 h-12 text-danger mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>
            <h3 class="text-text-primary font-bold text-lg mb-2">Delete Track?</h3>
            <p class="text-text-secondary text-sm mb-4">
              Are you sure you want to delete "{{ trackToDelete?.title }}" from disk?
            </p>
            <div class="flex gap-4">
              <button @click="trackDeleteModalOpen = false" class="flex-1 bg-surface-elevated hover:bg-gray-600 text-text-primary font-bold py-2 rounded transition">Cancel</button>
              <button @click="executeDeleteSingleTrack" class="flex-1 bg-danger hover:bg-danger-light text-text-inverse font-bold py-2 rounded transition">Delete</button>
            </div>
          </div>
        </div>
      </div>
  </div>
</template>
