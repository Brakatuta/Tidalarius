<script setup>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { playerStore } from '../playerStore.js'
import { syncStore } from '../syncStore.js'
import MarqueeText from './MarqueeText.vue'

const props = defineProps({
    playlist: {
        type: Object,
        required: true
    },
    isDiscover: {
        type: Boolean,
        default: false
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

const onQualityChanged = () => {
    streamQuality.value = localStorage.getItem('streamQuality') || 'HIGH'
    applyStreamQuality()
}

const weekDays = [
  { id: 1, label: 'Mo' },
  { id: 2, label: 'Di' },
  { id: 3, label: 'Mi' },
  { id: 4, label: 'Do' },
  { id: 5, label: 'Fr' },
  { id: 6, label: 'Sa' },
  { id: 0, label: 'So' }
]

const modalSyncEnabled = ref(false)
const scheduleMode = ref('time')
const scheduleTime = ref('03:00')
const scheduleDays = ref([1, 2, 3, 4, 5, 6, 0])
const scheduleInterval = ref(6)

const toggleDay = (dayId) => {
  if (scheduleDays.value.includes(dayId)) {
    if (scheduleDays.value.length > 1) {
      scheduleDays.value = scheduleDays.value.filter(d => d !== dayId)
    }
  } else {
    scheduleDays.value.push(dayId)
  }
}

const selectAllDays = () => {
  scheduleDays.value = [1, 2, 3, 4, 5, 6, 0]
}

const selectWeekdays = () => {
  scheduleDays.value = [1, 2, 3, 4, 5]
}

const selectWeekend = () => {
  scheduleDays.value = [6, 0]
}

const scheduleSummary = computed(() => {
  if (!modalSyncEnabled.value) {
    return 'Auto-Sync ist deaktiviert'
  }
  if (scheduleMode.value === 'interval') {
    return `Synchronisiert alle ${scheduleInterval.value} Stunde${scheduleInterval.value > 1 ? 'n' : ''}`
  }
  const timeStr = scheduleTime.value || '03:00'
  if (scheduleDays.value.length === 7) {
    return `Täglich um ${timeStr} Uhr`
  }
  const daySet = new Set(scheduleDays.value)
  if (daySet.size === 5 && [1, 2, 3, 4, 5].every(d => daySet.has(d))) {
    return `Montag bis Freitag um ${timeStr} Uhr`
  }
  if (daySet.size === 2 && daySet.has(6) && daySet.has(0)) {
    return `Am Wochenende (Sa, So) um ${timeStr} Uhr`
  }
  const dayNames = weekDays.filter(d => daySet.has(d.id)).map(d => d.label).join(', ')
  return `Jeden ${dayNames} um ${timeStr} Uhr`
})

const openScheduleModal = () => {
  modalSyncEnabled.value = !!props.playlist.sync_enabled
  const sched = props.playlist.schedule
  if (sched && sched !== 'custom') {
    const intervalMatch = sched.match(/^0 \*\/(\d+) \* \* \*$/)
    if (intervalMatch) {
      scheduleMode.value = 'interval'
      scheduleInterval.value = parseInt(intervalMatch[1], 10)
    } else if (sched === '0 * * * *') {
      scheduleMode.value = 'interval'
      scheduleInterval.value = 1
    } else {
      const parts = sched.trim().split(/\s+/)
      if (parts.length === 5) {
        scheduleMode.value = 'time'
        const min = parts[0].padStart(2, '0')
        const hr = parts[1].padStart(2, '0')
        scheduleTime.value = `${hr}:${min}`
        if (parts[4] === '*') {
          scheduleDays.value = [1, 2, 3, 4, 5, 6, 0]
        } else {
          const parsedDays = parts[4].split(',').map(d => parseInt(d, 10)).filter(d => !isNaN(d))
          scheduleDays.value = parsedDays.length > 0 ? parsedDays : [1, 2, 3, 4, 5, 6, 0]
        }
      } else {
        scheduleMode.value = 'time'
        scheduleTime.value = '03:00'
        scheduleDays.value = [1, 2, 3, 4, 5, 6, 0]
      }
    }
  } else {
    scheduleMode.value = 'time'
    scheduleTime.value = '03:00'
    scheduleDays.value = [1, 2, 3, 4, 5, 6, 0]
  }
  scheduleModalOpen.value = true
}

const saveScheduleModal = async () => {
  let cron = null
  if (scheduleMode.value === 'interval') {
    if (Number(scheduleInterval.value) === 1) {
      cron = '0 * * * *'
    } else if (Number(scheduleInterval.value) === 24) {
      cron = '0 0 * * *'
    } else {
      cron = `0 */${scheduleInterval.value} * * *`
    }
  } else {
    const [h, m] = (scheduleTime.value || '03:00').split(':')
    const minute = parseInt(m, 10) || 0
    const hour = parseInt(h, 10) || 0
    if (scheduleDays.value.length === 7 || scheduleDays.value.length === 0) {
      cron = `${minute} ${hour} * * *`
    } else {
      const sortedDays = [...scheduleDays.value].sort((a, b) => a - b).join(',')
      cron = `${minute} ${hour} * * ${sortedDays}`
    }
  }
  props.playlist.schedule = cron
  props.playlist.sync_enabled = modalSyncEnabled.value
  await saveConfig()
  scheduleModalOpen.value = false
}

const isInLibrary = ref(false)

const checkLibrary = async () => {
    try {
        const res = await fetch('/api/playlists/')
        if (res.ok) {
            const list = await res.json()
            const targetId = String(props.playlist.tidal_id || props.playlist.id || '')
            isInLibrary.value = list.some(item => String(item.tidal_id) === targetId)
        }
    } catch (e) {
        console.error("Failed to check library", e)
    }
}

const addToLibrary = async () => {
    try {
        const payload = {
            item_type: props.playlist.item_type || 'playlist',
            name: playlistData.value?.name || props.playlist.name,
            artist_name: playlistData.value?.artist || props.playlist.artist_name || props.playlist.artist,
            picture_url: playlistData.value?.picture_url || props.playlist.picture_url,
            sync_enabled: false,
            qualities: (props.playlist.qualities && props.playlist.qualities.length > 0) ? props.playlist.qualities : ["HIGH"]
        }
        const res = await fetch(`/api/playlists/${props.playlist.tidal_id}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        if (res.ok) {
            isInLibrary.value = true
        }
    } catch (e) {
        console.error("Failed to add to library", e)
    }
}

const removeFromLibrary = async () => {
    if (!confirm(`Remove ${props.playlist.name || playlistData.value?.name} from Library and delete downloaded files?`)) return
    try {
        await fetch(`/api/sync/delete/${props.playlist.tidal_id}`, { method: 'DELETE' }).catch(() => {})
        const res = await fetch(`/api/playlists/${props.playlist.tidal_id}`, { method: 'DELETE' })
        if (res.ok) {
            isInLibrary.value = false
            fetchDetailsSilent()
        }
    } catch (e) {
        console.error("Failed to remove from library", e)
    }
}

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

const downloadModalTrack = ref(null)

const openDownloadModal = (track) => {
    downloadModalTrack.value = track
}

const confirmDownloadTrack = (quality) => {
    if (downloadModalTrack.value) {
        downloadSingleTrack(downloadModalTrack.value.id, quality)
    }
    downloadModalTrack.value = null
}

const downloadSingleTrack = async (trackId, quality = 'HIGH') => {
    try {
        await fetch(`/api/sync/track/${props.playlist.tidal_id}/${trackId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify([quality])
        })
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
            if (playlistData.value && playlistData.value.tracks) {
                const tr = playlistData.value.tracks.find(t => t.id === trackId)
                if (tr) {
                    tr.is_downloaded = false
                    tr.stream_url = `/api/music/stream/${trackId}`
                    tr.quality = streamQuality.value
                }
            }
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
            if (!t.is_downloaded) {
                if (t.stream_url && t.stream_url.includes('/api/music/stream/')) {
                    const baseUrl = t.stream_url.split('?')[0]
                    t.stream_url = `${baseUrl}?quality=${streamQuality.value}`
                }
                if (!t.quality || t.quality === 'TIDAL') {
                    t.quality = streamQuality.value
                }
            }
        })
    }
}

const fetchDetails = async () => {
    loading.value = true
    error.value = null
    try {
        const endpoint = props.playlist.item_type === 'album' ? `/api/music/album/${props.playlist.tidal_id}` : `/api/music/playlist/${props.playlist.tidal_id}`
        const res = await fetch(endpoint)
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

const onLibraryUpdated = () => {
    checkLibrary()
    fetchDetailsSilent()
}

onMounted(() => {
    fetchDetails()
    checkLibrary()
    window.addEventListener('streamQualityChanged', onQualityChanged)
    window.addEventListener('library-updated', onLibraryUpdated)
})

onUnmounted(() => {
    window.removeEventListener('streamQualityChanged', onQualityChanged)
    window.removeEventListener('library-updated', onLibraryUpdated)
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

const playTrack = (track) => {
    const isMobile = window.innerWidth < 768;
    
    if (isMobile) {
        expandedTrackId.value = expandedTrackId.value === track.id ? null : track.id;
    }

    if (!track.stream_url) return
    const idx = playlistData.value.tracks.findIndex(t => t.id === track.id)
    if (!track.is_downloaded && (!track.quality || track.quality === 'TIDAL')) {
        track.quality = streamQuality.value
    }
    playerStore.playPlaylist(props.playlist.tidal_id, playlistData.value.name, playlistData.value.tracks, idx)
}

const togglePlayPlaylist = () => {
    if (playerStore.currentPlaylistId === props.playlist.tidal_id) {
        playerStore.togglePlayPause()
    } else {
        if (playlistData.value && playlistData.value.tracks.length > 0) {
            playTrack(playlistData.value.tracks[0])
        }
    }
}

const saveConfig = async () => {
  saving.value = true
  try {
    let nameToSave = playlistData.value?.name
    if (!nameToSave || ['Unknown', 'Unknown Item', 'Unknown Playlist'].includes(nameToSave)) {
      nameToSave = (props.playlist.name && !['Unknown', 'Unknown Item', 'Unknown Playlist'].includes(props.playlist.name)) ? props.playlist.name : undefined
    }
    const payload = {
      item_type: props.playlist.item_type || 'playlist',
      name: nameToSave,
      artist_name: playlistData.value?.artist || props.playlist.artist_name || props.playlist.artist,
      picture_url: playlistData.value?.picture_url || props.playlist.picture_url,
      sync_enabled: !!props.playlist.sync_enabled,
      qualities: (props.playlist.qualities && props.playlist.qualities.length > 0) ? props.playlist.qualities : ['HIGH'],
      schedule: props.playlist.schedule || null
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

watch(() => syncStore.playlistDownloadsDeleted, (delEvent) => {
    if (delEvent && delEvent.playlist_id === props.playlist.tidal_id) {
        fetchDetailsSilent()
    }
})

const fetchDetailsSilent = async () => {
    try {
        const endpoint = props.playlist.item_type === 'album' ? `/api/music/album/${props.playlist.tidal_id}` : `/api/music/playlist/${props.playlist.tidal_id}`
        const res = await fetch(endpoint)
        if (res.ok) {
            playlistData.value = await res.json()
            applyStreamQuality()
            syncStore.fetchStatus(props.playlist.tidal_id)
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
              
              <button @click="emit('back')" class="absolute top-4 left-4 p-3 bg-black/60 hover:bg-black/90 text-white rounded-full transition-colors backdrop-blur-md shadow-2xl border border-white/20 z-50">
                <svg class="w-6 h-6 drop-shadow-md" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M10 19l-7-7m0 0l7-7m-7 7h18"></path></svg>
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
                              <span v-if="isDiscover">
                                  <span v-if="isInLibrary">
                                      <span class="font-semibold text-accent">{{ playlistData.tracks.filter(t => t.is_downloaded).length }} tracks</span> downloaded of {{ playlistData.tracks.length }} total
                                  </span>
                                  <span v-else>{{ playlistData.tracks.length }} tracks</span>
                              </span>
                              <span v-else>
                                  <span class="font-semibold">{{ playlistData.tracks.filter(t => t.is_downloaded).length }} tracks</span> downloaded of {{ playlistData.tracks.length }} total
                              </span>
                          </p>
                      </div>
                  </div>
                  
                  <!-- Add / Remove from Library (Discover mode only) -->
                  <div v-if="isDiscover" class="flex items-center justify-between gap-4 bg-surface-80 p-3 rounded-lg border border-border-highlight w-full backdrop-blur shadow-inner">
                      <div>
                          <p v-if="isInLibrary" class="text-sm text-text-secondary">
                              <span class="font-semibold text-accent">{{ playlistData.tracks.filter(t => t.is_downloaded).length }}</span> of {{ playlistData.tracks.length }} tracks downloaded
                          </p>
                          <p v-else class="text-sm text-text-secondary">
                              {{ playlistData.tracks.length }} tracks
                          </p>
                      </div>
                      <div class="flex items-center gap-2">
                          <button v-if="!isInLibrary" @click="addToLibrary" class="px-4 py-2 bg-accent hover:bg-accent-light text-text-inverse rounded-lg text-sm font-bold transition-colors flex items-center gap-2 shadow">
                              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path></svg>
                              Add to Library
                          </button>
                          <button v-else @click="removeFromLibrary" class="px-4 py-2 bg-danger hover:bg-danger-light text-text-primary rounded-lg text-sm font-bold transition-colors flex items-center gap-2 shadow">
                              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                              Remove from Library
                          </button>
                      </div>
                  </div>
                  <!-- Sync Configuration inside Header (Library mode only) -->
                  <div v-if="!isDiscover" class="flex flex-col xl:flex-row items-start xl:items-center justify-between gap-4 flex-wrap bg-surface-80 p-3 rounded-lg border border-border-highlight w-full backdrop-blur shadow-inner">
                    <div class="flex flex-col md:flex-row flex-wrap gap-4">
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
                      

                    </div>
                    
                    <div class="flex items-center gap-2 ml-auto">
                      <!-- 1. Delete (Mülleimer) -->
                      <button @click="deleteModalOpen = true" 
                              :disabled="getSyncStatus.status !== 'idle'" 
                              class="bg-danger hover:bg-danger-light text-text-primary border border-danger-30 text-xs px-2.5 py-1.5 rounded font-bold transition disabled:opacity-50 flex items-center justify-center" 
                              title="Delete Downloaded Files">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                      </button>

                      <!-- 2. Logs -->
                      <button @click="syncModalOpen = true" 
                              class="bg-surface hover:bg-surface-elevated text-text-muted hover:text-text-primary border border-border-strong text-xs px-3 py-1.5 rounded font-bold transition">
                        Logs
                      </button>

                      <!-- 3. Sync Now -->
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

                      <!-- 4. Sync Settings (Zahnrad) -->
                      <button @click="openScheduleModal()" 
                              class="p-1.5 bg-surface hover:bg-surface-elevated border border-border-strong rounded text-text-secondary hover:text-text-primary transition-colors flex items-center justify-center"
                              title="Sync Settings">
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                      </button>
                    </div>
                  </div>
                  <!-- Progress Bar -->
                  <div v-if="!isDiscover && getSyncStatus.status === 'syncing'" class="mt-2 h-1.5 w-full bg-surface-elevated rounded-full overflow-hidden">
                      <div class="h-full bg-accent transition-all duration-300" :style="`width: ${getSyncStatus.progress}%`"></div>
                  </div>
              </div>
          </div>
          
          <!-- Controls & Search -->
          <div class="p-6 bg-background flex justify-between items-center sticky top-0 z-10 border-b border-border-subtle-50 backdrop-blur bg-opacity-90">
              <button 
                  @click="togglePlayPlaylist()"
                  class="w-14 h-14 shrink-0 aspect-square bg-accent rounded-full flex items-center justify-center text-text-inverse hover:bg-accent-light hover:scale-105 transition-all shadow-lg"
              >
                  <svg v-if="playerStore.currentPlaylistId === playlist.tidal_id && playerStore.isPlaying" class="w-7 h-7 shrink-0" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                  <svg v-else class="w-7 h-7 shrink-0 translate-x-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
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
                                      <img v-if="track.picture_url" :src="track.picture_url" class="w-10 h-10 rounded shadow object-cover bg-surface flex-shrink-0" />
                                      <div class="w-10 h-10 rounded bg-surface flex items-center justify-center flex-shrink-0" v-else>
                                          <svg class="w-5 h-5 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"></path></svg>
                                      </div>
                                      <div class="flex flex-col pr-4 max-w-[170px] sm:max-w-[220px] md:max-w-[240px] lg:max-w-xs overflow-hidden">
                                          <MarqueeText 
                                              :text="track.title" 
                                              :class="['font-medium text-sm', playerStore.currentTrack && playerStore.currentTrack.id === track.id ? 'text-accent' : 'text-text-primary']" 
                                          />
                                          <span class="text-xs text-text-muted hover:underline truncate" :title="track.artist">{{ track.artist }}</span>
                                      </div>
                                  </div>
                              </td>
                              <td class="py-3 hidden md:table-cell pr-4 max-w-[140px] lg:max-w-[220px] overflow-hidden hover:text-text-primary">
                                  <MarqueeText :text="track.album || ''" class="text-sm text-text-secondary hover:text-text-primary" />
                              </td>
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
                                      <button v-if="!isDiscover" @click.stop="openDownloadModal(track)" class="text-text-muted hover:text-accent transition-colors p-1 bg-surface hover:bg-surface-elevated rounded border border-border-strong" title="Download this track only">
                                          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                                      </button>
                                  </div>
                              </td>
                              <td class="py-3 text-right tabular-nums hidden md:table-cell">{{ formatTime(track.duration) }}</td>
                          </tr>
                          
                          <!-- Mobile Expanded Row -->
                          <tr v-if="expandedTrackId === track.id" class="md:hidden bg-surface-elevated border-b border-border-subtle-50">
                              <td colspan="5" class="py-3 px-4">
                                  <div class="flex flex-col gap-2 text-xs">
                                      <div v-if="track.album" class="flex items-center gap-2 overflow-hidden">
                                          <span class="text-text-muted shrink-0">Album:</span>
                                          <div class="flex-1 overflow-hidden">
                                              <MarqueeText :text="track.album" class="text-text-secondary" />
                                          </div>
                                      </div>
                                      <div class="flex justify-between items-center text-xs">
                                          <span class="text-text-muted">Duration: <span class="text-text-primary font-mono ml-1">{{ formatTime(track.duration) }}</span></span>
                                          <div class="flex items-center gap-2">
                                              <span class="text-text-muted">Quality:</span>
                                              <span v-if="track.is_downloaded" class="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold tracking-wider" 
                                                  :class="getQualityClasses(track.quality)">
                                                  {{ track.quality === 'HI_RES_LOSSLESS' ? 'MAX' : track.quality }}
                                              </span>
                                              <span v-else class="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold tracking-wider"
                                                  :class="getQualityClasses(track.quality && track.quality !== 'TIDAL' ? track.quality : streamQuality)">
                                                  {{ (track.quality && track.quality !== 'TIDAL' ? track.quality : streamQuality) === 'HI_RES_LOSSLESS' ? 'MAX' : (track.quality && track.quality !== 'TIDAL' ? track.quality : streamQuality) }}
                                              </span>
                                              
                                              <button v-if="track.is_downloaded" @click.stop="confirmDeleteSingleTrack(track)" class="text-text-muted hover:text-danger p-1 bg-surface rounded border border-border-strong" title="Delete this track">
                                                  <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                                              </button>
                                              <button v-else-if="!isDiscover" @click.stop="openDownloadModal(track)" class="text-text-muted hover:text-accent p-1 bg-surface rounded border border-border-strong" title="Download this track">
                                                  <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                                              </button>
                                          </div>
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
      <div v-if="scheduleModalOpen" class="fixed inset-0 bg-black-base-80 flex items-center justify-center z-50 p-4">
        <div class="bg-surface rounded-xl shadow-2xl border border-border-strong w-full max-w-md overflow-hidden">
          <div class="bg-background p-4 border-b border-border-strong flex justify-between items-center">
            <h3 class="text-text-primary font-bold text-lg">Sync Settings</h3>
            <button @click="scheduleModalOpen = false" class="text-text-muted hover:text-text-primary">
              <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
          </div>
          
          <div class="p-6 space-y-5">
            <!-- Auto Sync Toggle inside modal -->
            <div class="flex items-center justify-between p-3 bg-background rounded-lg border border-border-strong">
              <div>
                <div class="text-text-primary text-sm font-semibold">Enable Auto-Sync</div>
                <div class="text-text-secondary text-xs">Run automatic background syncs</div>
              </div>
              <button type="button" @click="modalSyncEnabled = !modalSyncEnabled" 
                      class="relative inline-flex items-center h-6 rounded-full w-11 transition-colors focus:outline-none cursor-pointer"
                      :class="modalSyncEnabled ? 'bg-accent' : 'bg-gray-600'">
                <span class="inline-block w-4 h-4 transform bg-white-base rounded-full transition-transform"
                      :class="modalSyncEnabled ? 'translate-x-6' : 'translate-x-1'"></span>
              </button>
            </div>

            <!-- Schedule Type Tabs -->
            <div class="flex rounded-lg bg-background p-1 border border-border-strong text-xs font-semibold">
              <button type="button" 
                      @click="scheduleMode = 'time'" 
                      :class="scheduleMode === 'time' ? 'bg-surface-elevated text-text-primary shadow-sm' : 'text-text-muted hover:text-text-secondary'"
                      class="flex-1 py-1.5 rounded-md transition-all cursor-pointer">
                Specific Time & Days
              </button>
              <button type="button" 
                      @click="scheduleMode = 'interval'" 
                      :class="scheduleMode === 'interval' ? 'bg-surface-elevated text-text-primary shadow-sm' : 'text-text-muted hover:text-text-secondary'"
                      class="flex-1 py-1.5 rounded-md transition-all cursor-pointer">
                Hourly Interval
              </button>
            </div>

            <!-- Specific Time & Days Mode -->
            <div v-if="scheduleMode === 'time'" class="space-y-4">
              <!-- Sync Time -->
              <div>
                <label class="block text-xs text-text-muted uppercase tracking-wider mb-1.5">Sync Time (Uhrzeit)</label>
                <input type="time" v-model="scheduleTime" 
                       class="w-full bg-background border border-border-strong rounded-lg px-3 py-2 text-text-primary text-sm focus:outline-none focus:border-accent">
              </div>

              <!-- Weekdays -->
              <div>
                <div class="flex items-center justify-between mb-1.5">
                  <label class="text-xs text-text-muted uppercase tracking-wider">Days of Week (Wochentage)</label>
                  <div class="flex gap-1">
                    <button type="button" @click="selectAllDays" class="text-[10px] text-accent hover:underline cursor-pointer">All</button>
                    <span class="text-text-disabled text-[10px]">•</span>
                    <button type="button" @click="selectWeekdays" class="text-[10px] text-accent hover:underline cursor-pointer">Mo–Fr</button>
                    <span class="text-text-disabled text-[10px]">•</span>
                    <button type="button" @click="selectWeekend" class="text-[10px] text-accent hover:underline cursor-pointer">Sa–So</button>
                  </div>
                </div>
                
                <div class="grid grid-cols-7 gap-1.5">
                  <button type="button" v-for="d in weekDays" :key="d.id" 
                          @click="toggleDay(d.id)"
                          :class="scheduleDays.includes(d.id) 
                            ? 'bg-accent text-text-inverse font-bold border-accent shadow-sm' 
                            : 'bg-background hover:bg-surface-elevated text-text-secondary border-border-strong'"
                          class="h-9 rounded-lg border text-xs font-semibold flex items-center justify-center transition-all cursor-pointer">
                    {{ d.label }}
                  </button>
                </div>
              </div>
            </div>

            <!-- Hourly Interval Mode -->
            <div v-else class="space-y-2">
              <label class="block text-xs text-text-muted uppercase tracking-wider">Sync Interval</label>
              <select v-model="scheduleInterval" class="w-full bg-background border border-border-strong rounded-lg px-3 py-2 text-text-primary text-sm focus:outline-none focus:border-accent">
                <option :value="1">Every 1 hour</option>
                <option :value="2">Every 2 hours</option>
                <option :value="3">Every 3 hours</option>
                <option :value="6">Every 6 hours</option>
                <option :value="12">Every 12 hours</option>
                <option :value="24">Every 24 hours (Daily)</option>
              </select>
            </div>

            <!-- Live Summary Box -->
            <div class="p-3 bg-surface-elevated/40 rounded-lg border border-border-strong/60 flex items-center gap-2.5">
              <svg class="w-4 h-4 text-accent shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
              <span class="text-xs text-text-secondary font-medium">{{ scheduleSummary }}</span>
            </div>
          </div>
          
          <div class="p-4 bg-background border-t border-border-strong flex justify-end gap-3">
            <button @click="scheduleModalOpen = false" class="px-4 py-2 text-sm text-text-muted hover:text-text-primary transition-colors">Cancel</button>
            <button @click="saveScheduleModal()" class="px-4 py-2 bg-accent hover:bg-accent-light text-text-inverse rounded text-sm font-bold transition-colors">Save Settings</button>
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
      <!-- Single Track Download Quality Modal -->
      <div v-if="downloadModalTrack" class="fixed inset-0 bg-black/80 z-[100] flex items-center justify-center p-4 backdrop-blur-sm" @click.stop="downloadModalTrack = null">
          <div class="bg-surface rounded-xl shadow-2xl w-full max-w-xs border border-border-strong overflow-hidden" @click.stop="">
              <div class="p-4 border-b border-border-strong flex justify-between items-center bg-background">
                  <div>
                      <h3 class="font-bold text-text-primary text-sm">Download Quality</h3>
                      <p class="text-xs text-text-muted truncate max-w-[200px]">{{ downloadModalTrack.title || downloadModalTrack.name }}</p>
                  </div>
                  <button @click.stop="downloadModalTrack = null" class="text-text-muted hover:text-text-primary p-1">
                      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                  </button>
              </div>
              <div class="flex flex-col p-3 gap-2 bg-background">
                  <button @click.stop="confirmDownloadTrack('HI_RES_LOSSLESS')" class="flex items-center justify-between py-2.5 px-3 bg-surface hover:bg-surface-elevated rounded-lg border border-purple-500/30 text-purple-400 font-bold text-sm transition-all hover:scale-[1.02]">
                      <span>MAX</span>
                      <span class="text-[10px] font-normal text-text-muted">Hi-Res Flac</span>
                  </button>
                  <button @click.stop="confirmDownloadTrack('LOSSLESS')" class="flex items-center justify-between py-2.5 px-3 bg-surface hover:bg-surface-elevated rounded-lg border border-warning-30 text-warning font-bold text-sm transition-all hover:scale-[1.02]">
                      <span>LOSSLESS</span>
                      <span class="text-[10px] font-normal text-text-muted">Flac (16-bit)</span>
                  </button>
                  <button @click.stop="confirmDownloadTrack('HIGH')" class="flex items-center justify-between py-2.5 px-3 bg-surface hover:bg-surface-elevated rounded-lg border border-info-30 text-info-light font-bold text-sm transition-all hover:scale-[1.02]">
                      <span>HIGH</span>
                      <span class="text-[10px] font-normal text-text-muted">AAC 320kbps</span>
                  </button>
                  <button @click.stop="confirmDownloadTrack('LOW')" class="flex items-center justify-between py-2.5 px-3 bg-surface hover:bg-surface-elevated rounded-lg border border-green-700/30 text-green-400 font-bold text-sm transition-all hover:scale-[1.02]">
                      <span>LOW</span>
                      <span class="text-[10px] font-normal text-text-muted">AAC 96kbps</span>
                  </button>
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
