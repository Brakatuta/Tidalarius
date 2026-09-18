<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { playerStore } from '../playerStore.js'
import { syncStore } from '../syncStore.js'
import PlaylistDetail from './PlaylistDetail.vue'

const playlists = ref([])
const loading = ref(true)
const selectedPlaylist = ref(null)

const trackDownloadToDelete = ref(null)

const confirmDeleteTrackDownload = (playlist) => {
    trackDownloadToDelete.value = playlist
}

const executeDeleteTrackDownload = async () => {
    if (!trackDownloadToDelete.value) return
    const target = trackDownloadToDelete.value
    try {
        await fetch(`/api/sync/delete/${target.tidal_id}`, { method: 'DELETE' })
        target.last_synced = null
        if (syncStore.syncState[target.tidal_id]) {
            syncStore.syncState[target.tidal_id].last_synced = null
            delete syncStore.syncState[target.tidal_id].last_synced
        }
        await fetchPlaylists()
        const p = playlists.value.find(item => item.tidal_id === target.tidal_id)
        if (p) p.last_synced = null
    } catch (e) {
        console.error("Failed to delete track download", e)
    } finally {
        trackDownloadToDelete.value = null
    }
}

watch(() => syncStore.lastDownloadedTrack, (newTrack) => {
    if (newTrack) {
        const p = playlists.value.find(item => item.tidal_id === newTrack.playlist_id)
        if (p) {
            p.last_synced = new Date().toISOString()
            p.qualities = [newTrack.quality]
            if (!syncStore.syncState[p.tidal_id]) syncStore.syncState[p.tidal_id] = {}
            syncStore.syncState[p.tidal_id].last_synced = new Date().toISOString()
            syncStore.syncState[p.tidal_id].quality = newTrack.quality
            safeSetCache(CACHE_KEY_LIBRARY, JSON.stringify(playlists.value))
        }
    }
})

watch(() => syncStore.trackDeleted, (delEvent) => {
    if (delEvent) {
        const p = playlists.value.find(item => item.tidal_id === delEvent.playlist_id)
        if (p) {
            p.last_synced = null
        }
        if (syncStore.syncState[delEvent.playlist_id]) {
            syncStore.syncState[delEvent.playlist_id].last_synced = null
            delete syncStore.syncState[delEvent.playlist_id].last_synced
        }
        fetchPlaylists()
    }
})

watch(() => syncStore.playlistDownloadsDeleted, (delEvent) => {
    if (delEvent) {
        fetchPlaylists()
    }
})

const deleteItem = async (playlist) => {
    if (!confirm(`Remove ${playlist.name} from Library and delete downloaded files?`)) return;
    try {
        await fetch(`/api/sync/delete/${playlist.tidal_id}`, { method: 'DELETE' }).catch(e => console.error(e));
        await fetch(`/api/playlists/${playlist.tidal_id}`, { method: 'DELETE' });
        await fetchPlaylists();
    } catch (e) {
        console.error(e);
    }
}

const downloadTrack = async (playlist, quality = 'HIGH') => {
    try {
        await fetch(`/api/sync/start/${playlist.tidal_id}?item_type=${playlist.item_type || 'playlist'}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify([quality])
        });
        syncStore.fetchStatus(playlist.tidal_id);
    } catch (e) {
        console.error(e);
    }
}

const CACHE_KEY_LIBRARY = 'tidalarius_cache_library_playlists'

const safeSetCache = (key, value) => {
    try {
        localStorage.setItem(key, value)
    } catch (e) {
        if (e.name === 'QuotaExceededError' || e.code === 22) {
            try {
                const keysToRemove = []
                for (let i = 0; i < localStorage.length; i++) {
                    const k = localStorage.key(i)
                    if (k && k.startsWith('tidalarius_cache_detail_')) {
                        keysToRemove.push(k)
                    }
                }
                keysToRemove.forEach(k => localStorage.removeItem(k))
                localStorage.setItem(key, value)
            } catch (err) {}
        }
    }
}

const fetchPlaylists = async () => {
    // 1. Instant Cache Render: load from local cache if available
    const cached = localStorage.getItem(CACHE_KEY_LIBRARY)
    if (cached) {
        try {
            const parsed = JSON.parse(cached)
            if (Array.isArray(parsed) && parsed.length > 0) {
                playlists.value = parsed
                loading.value = false // render immediately without spinner!
                
                const urlParams = new URLSearchParams(window.location.search)
                const playlistId = urlParams.get('playlist')
                if (playlistId) {
                    const p = playlists.value.find(x => x.tidal_id === playlistId)
                    if (p) selectedPlaylist.value = p
                }
            }
        } catch (e) {
            console.warn("Failed to parse cached library", e)
        }
    } else if (!playlists.value.length) {
        loading.value = true
    }

    // 2. Revalidate in background from server
    try {
        const res = await fetch('/api/playlists/')
        if (res.ok) {
            const data = await res.json()
            playlists.value = data
            safeSetCache(CACHE_KEY_LIBRARY, JSON.stringify(data))
            
            // Check URL parameters for direct playlist navigation
            const urlParams = new URLSearchParams(window.location.search)
            const playlistId = urlParams.get('playlist')
            if (playlistId) {
                const p = playlists.value.find(x => x.tidal_id === playlistId)
                if (p) selectedPlaylist.value = p
            }
        }
    } catch (e) {
        console.error("Failed to fetch music playlists", e)
    } finally {
        loading.value = false
    }
}

onMounted(() => {
    fetchPlaylists()
    
    // Listen for browser back/forward navigation
    window.addEventListener('popstate', (e) => {
        if (e.state && e.state.playlistId) {
            const p = playlists.value.find(x => x.tidal_id === e.state.playlistId)
            if (p) selectedPlaylist.value = p
        } else {
            // Check URL as fallback or if state is empty
            const urlParams = new URLSearchParams(window.location.search)
            const playlistId = urlParams.get('playlist')
            if (playlistId) {
                const p = playlists.value.find(x => x.tidal_id === playlistId)
                if (p) selectedPlaylist.value = p
            } else {
                selectedPlaylist.value = null
            }
        }
    })
    
    // Listen for logo clicks from App.vue
    window.addEventListener('navigate-home', () => {
        selectedPlaylist.value = null
    })

    const onLibraryUpdated = () => {
        fetchPlaylists()
    }
    window.addEventListener('library-updated', onLibraryUpdated)

    onUnmounted(() => {
        window.removeEventListener('library-updated', onLibraryUpdated)
    })
})


const formatQuality = (quality) => {
    if (!quality) return 'HIGH'
    if (quality === 'HI_RES_LOSSLESS') return 'MAX'
    return quality
}

const getQualityClasses = (quality) => {
    const normalized = (quality === 'HI_RES_LOSSLESS') ? 'MAX' : quality
    switch (normalized) {
        case 'LOW': return 'bg-green-900/40 text-green-400 border border-green-700/50'
        case 'HIGH': return 'bg-info-20 text-info-light border border-info-30'
        case 'LOSSLESS': return 'bg-warning-20 text-warning border border-warning-30'
        case 'MAX': return 'bg-purple-900/40 text-purple-400 border border-purple-500/50'
        case 'YOUTUBE': return 'bg-pink-900/40 text-pink-400 border border-pink-500/50'
        default: return 'bg-surface-elevated text-text-secondary border border-border-strong'
    }
}

const getTrackQuality = (playlist) => {
    return syncStore.syncState[playlist.tidal_id]?.quality || playlist.qualities?.[0] || 'HIGH'
}

const playTrack = (track) => {
    if (playerStore.currentPlaylistId === `track_${track.tidal_id}`) {
        playerStore.togglePlayPause()
        return
    }
    const isDownloaded = !!(syncStore.syncState[track.tidal_id]?.last_synced || track.last_synced)
    const trackQuality = getTrackQuality(track)
    const streamQuality = localStorage.getItem('streamQuality') || 'HIGH'
    const trackToPlay = {
        id: track.tidal_id,
        title: track.name,
        artist: track.artist_name || 'Unknown',
        picture_url: track.picture_url,
        is_downloaded: isDownloaded,
        quality: isDownloaded ? trackQuality : streamQuality,
        stream_url: `/api/music/stream/${track.tidal_id}?quality=${isDownloaded ? trackQuality : streamQuality}`
    }
    playerStore.playPlaylist(`track_${track.tidal_id}`, "Library Track", [trackToPlay], 0)
}

const openPlaylist = (playlist) => {
    if (playlist.item_type === 'track') return playTrack(playlist)

    selectedPlaylist.value = playlist
    history.pushState({ playlistId: playlist.tidal_id }, '', `?playlist=${playlist.tidal_id}`)
}

const closePlaylist = () => {
    selectedPlaylist.value = null
    history.pushState(null, '', window.location.pathname)
}

const downloadModalTrack = ref(null)
const openDownloadModal = (playlist) => {
    downloadModalTrack.value = playlist
}
const confirmDownloadTrack = (quality) => {
    if (downloadModalTrack.value) {
        downloadTrack(downloadModalTrack.value, quality)
    }
    downloadModalTrack.value = null
}
</script>

<template>
  <div class="relative w-full h-full min-h-[500px]">
    
    <div v-if="!selectedPlaylist" class="w-full">
        <h2 class="text-3xl font-bold text-text-primary mb-8 border-b border-border-strong pb-4">Your Music Library</h2>
        
        <div v-if="loading" class="flex justify-center my-12">
            <svg class="animate-spin h-10 w-10 text-accent" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
        </div>
        
        <div v-else-if="playlists.length === 0" class="text-center text-text-muted py-12 bg-surface-50 rounded-xl">
            <svg class="w-16 h-16 mx-auto mb-4 text-gray-600" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"></path></svg>
            <p class="text-xl font-semibold text-text-secondary">No playlists found.</p>
            <p class="mt-2 text-sm text-text-disabled">Create a playlist on Tidal to get started.</p>
        </div>
        
        <div v-else class="wood-shelf-bg w-full rounded-lg shadow-2xl border-4 overflow-hidden" style="border-color: var(--wood-border);">
            
                <div class="grid w-full" style="grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); grid-auto-rows: 280px;">
                    <div v-for="playlist in playlists" :key="playlist.tidal_id" 
                         @click="openPlaylist(playlist)"
                         class="flex flex-col items-center justify-end pb-[55px] group cursor-pointer relative z-10">

                        <!-- Receiver Action UI -->
                        <div class="absolute top-2 left-1/2 -translate-x-1/2 w-[85%] h-12 bg-gradient-to-b from-surface-elevated to-surface border border-border-strong rounded-md shadow-[inset_0_2px_4px_rgba(255,255,255,0.05),_0_15px_25px_rgba(0,0,0,0.6)] z-50 flex items-center justify-around opacity-0 group-hover:opacity-100 transition-all group-hover:-translate-y-2 duration-300 before:absolute before:inset-x-2 before:bottom-1 before:h-px before:bg-black/40" @click.stop="">
                            
                            <!-- Power LED -->
                            <div class="w-1.5 h-1.5 rounded-full bg-accent animate-pulse shadow-[0_0_8px_rgba(var(--color-accent),0.8)] absolute left-3"></div>
                            
                            <!-- Buttons -->
                            <div class="flex items-center gap-3 pl-4">
                                <button v-if="!playlist.is_remote" @click.stop="deleteItem(playlist)" class="text-danger hover:text-danger-light hover:scale-110 transition-transform flex flex-col items-center gap-0.5 group/btn" title="Remove from Library">
                                    <svg class="w-4 h-4 shrink-0 drop-shadow-md" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                                    <span class="text-[8px] uppercase tracking-wider text-text-disabled group-hover/btn:text-text-muted">Remove</span>
                                </button>
                                
                                <div class="w-px h-6 bg-border-strong mx-1" v-if="!playlist.is_remote && playlist.item_type === 'track'"></div>

                                <button v-if="playlist.item_type === 'track' && (syncStore.syncState[playlist.tidal_id]?.status === 'syncing' || syncStore.syncState[playlist.tidal_id]?.status === 'queued')" @click.stop="" class="text-accent cursor-default flex flex-col items-center gap-0.5">
                                    <svg class="w-4 h-4 shrink-0 animate-spin drop-shadow-md" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                                    <span class="text-[8px] uppercase tracking-wider text-accent">Syncing</span>
                                </button>
                                
                                <div v-if="playlist.item_type === 'track' && syncStore.syncState[playlist.tidal_id]?.status !== 'syncing' && syncStore.syncState[playlist.tidal_id]?.status !== 'queued' && (syncStore.syncState[playlist.tidal_id]?.last_synced || playlist.last_synced)" class="flex items-center gap-1.5">
                                    <span class="text-[10px] font-bold px-1.5 py-0.5 rounded shadow-sm transition-colors" :class="getQualityClasses(getTrackQuality(playlist))">
                                        {{ formatQuality(getTrackQuality(playlist)) }}
                                    </span>
                                    <button @click.stop="confirmDeleteTrackDownload(playlist)" class="text-accent hover:text-danger hover:scale-110 transition-transform flex flex-col items-center gap-0.5 group/btn" title="Downloaded (Click to delete file)">
                                        <svg class="w-4 h-4 shrink-0 drop-shadow-md" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 00-9.78 2.096A4.001 4.001 0 003 15z"/></svg>
                                        <span class="text-[8px] uppercase tracking-wider text-accent group-hover/btn:text-danger">Cloud</span>
                                    </button>
                                </div>
                                
                                <div v-if="playlist.item_type === 'track' && !((syncStore.syncState[playlist.tidal_id]?.last_synced || playlist.last_synced) || syncStore.syncState[playlist.tidal_id]?.status === 'syncing' || syncStore.syncState[playlist.tidal_id]?.status === 'queued')">
                                    <button @click.stop="openDownloadModal(playlist)" class="text-info hover:text-info-light hover:scale-110 transition-transform flex flex-col items-center gap-0.5 group/btn" title="Download">
                                        <svg class="w-4 h-4 shrink-0 drop-shadow-md" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                                        <span class="text-[8px] uppercase tracking-wider text-text-disabled group-hover/btn:text-text-muted">Save</span>
                                    </button>
                                </div>
                            </div>
                        </div>
                        
                        <div v-if="playlist.item_type === 'track'" class="relative w-40 h-40 transition-transform duration-500 ease-out -translate-y-8 rotate-0" style="transform: perspective(800px) rotateX(15deg) translateY(-20px); filter: drop-shadow(0 15px 10px rgba(0,0,0,0.6));">
                            <div class="absolute inset-0 bg-black-base rounded-full shadow-[0_20px_30px_rgba(0,0,0,0.8)] border border-border-subtle flex items-center justify-center overflow-hidden rotate-180 translate-x-12 z-20">
                                <div class="absolute inset-1 rounded-full border border-border-subtle-50"></div>
                                <div class="absolute inset-3 rounded-full border border-border-subtle-50"></div>
                                <div class="relative w-16 h-16 rounded-full overflow-hidden shadow-inner border border-border-dark bg-background z-10">
                                    <img v-if="playlist.picture_url" :src="playlist.picture_url" class="w-full h-full object-cover opacity-90" />
                                    <div class="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-2 h-2 bg-black-base rounded-full border border-border-strong"></div>
                                </div>
                            </div>
                            <div class="absolute top-0 right-0 w-40 h-40 bg-surface rounded shadow-xl border border-border-strong overflow-hidden z-30 -translate-x-10 rotate-[-8deg]">
                                <img v-if="playlist.picture_url" :src="playlist.picture_url" class="w-full h-full object-cover" />
                            </div>
                            <div class="absolute inset-0 z-40 flex items-center justify-center transition-opacity"
                                 :class="(playerStore.currentPlaylistId === `track_${playlist.tidal_id}` && playerStore.isPlaying) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'">
                                <div class="w-14 h-14 rounded-full flex items-center justify-center shrink-0 aspect-square bg-black/60 hover:bg-black/80 hover:scale-110 transition-all backdrop-blur-sm shadow-2xl cursor-pointer"
                                     style="transform: rotateX(-15deg);"
                                     @click.stop="openPlaylist(playlist)">
                                    <svg v-if="playerStore.currentPlaylistId === `track_${playlist.tidal_id}` && playerStore.isPlaying" class="w-7 h-7 text-white drop-shadow-lg shrink-0" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                                    <svg v-else class="w-7 h-7 text-white drop-shadow-lg shrink-0 translate-x-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Vinyl Disc Design Leaning on Shelf -->
                        <div v-else class="relative w-40 h-40 transition-transform duration-500 ease-out group-hover:-translate-y-8 group-hover:rotate-0" 
                             style="transform: perspective(800px) rotateX(15deg) translateY(10px); transform-origin: bottom center; filter: drop-shadow(0 15px 10px rgba(0,0,0,0.6));">
                            
                            <!-- Black Vinyl -->
                            <div class="absolute inset-0 bg-black-base rounded-full shadow-[0_5px_15px_rgba(0,0,0,0.8)] border border-border-subtle flex items-center justify-center overflow-hidden transition-all duration-700 group-hover:rotate-180 group-hover:shadow-[0_20px_30px_rgba(0,0,0,0.8)]">
                                <!-- Vinyl Grooves -->
                                <div class="absolute inset-1 rounded-full border border-border-subtle-50"></div>
                                <div class="absolute inset-3 rounded-full border border-border-subtle-50"></div>
                                <div class="absolute inset-5 rounded-full border border-border-subtle-50"></div>
                                <div class="absolute inset-7 rounded-full border border-border-subtle-50"></div>
                                <div class="absolute inset-9 rounded-full border border-border-subtle-50"></div>
                                
                                <!-- Vinyl Center Label -->
                                <div class="relative w-16 h-16 rounded-full overflow-hidden shadow-inner border border-border-dark bg-background z-10">
                                    <img v-if="playlist.picture_url" :src="playlist.picture_url" class="w-full h-full object-cover opacity-90" />
                                    <div class="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-2 h-2 bg-black-base rounded-full border border-border-strong"></div>
                                </div>
                                
                                <div class="absolute inset-0 bg-gradient-to-tr from-transparent via-white/5 to-transparent rounded-full z-20 pointer-events-none"></div>
                                <div class="absolute inset-0 bg-gradient-to-br from-white/10 via-transparent to-transparent rounded-full z-20 pointer-events-none"></div>
                            </div>
                            
                            <!-- Cover Sleeve -->
                            <div class="absolute top-0 right-0 w-40 h-40 bg-surface rounded shadow-xl border border-border-strong overflow-hidden z-30 transition-transform duration-500 ease-out group-hover:-translate-x-10 group-hover:rotate-[-8deg]">
                                <img v-if="playlist.picture_url" :src="playlist.picture_url" class="w-full h-full object-cover" />
                                <div v-else class="w-full h-full flex items-center justify-center bg-surface-elevated text-text-disabled">
                                     <svg class="w-12 h-12" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19V6l12-3v13M9 19c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zm12-3c0 1.105-1.343 2-3 2s-3-.895-3-2 1.343-2 3-2 3 .895 3 2zM9 10l12-3"></path></svg>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Brass Title Plate on Shelf Edge -->
                        <div class="absolute bottom-[24px] left-1/2 transform -translate-x-1/2 w-36 text-center z-20 pointer-events-none transition-transform duration-300 group-hover:scale-110">
                            <div class="text-[10px] font-bold px-2 py-1 rounded shadow-[0_2px_4px_rgba(0,0,0,0.5)] truncate uppercase tracking-wider"
                                 style="background: linear-gradient(to bottom, var(--brass-grad-top), var(--brass-grad-bottom)); color: var(--brass-text); border: 1px solid var(--brass-border);">
                                {{ playlist.name }}
                            </div>
                            <!-- Plate Screws -->
                            <div class="absolute top-1/2 left-1 transform -translate-y-1/2 w-1 h-1 rounded-full" style="background-color: var(--brass-screw);"></div>
                            <div class="absolute top-1/2 right-1 transform -translate-y-1/2 w-1 h-1 rounded-full" style="background-color: var(--brass-screw);"></div>
                        </div>
                    </div>
                </div>
          </div>
      </div>
      
    <!-- Playlist Detail Overlay -->
    <div v-else class="w-full">
        <PlaylistDetail :playlist="selectedPlaylist" @back="closePlaylist" />
    </div>

    <!-- Single Track Download Quality Modal -->
    <div v-if="downloadModalTrack" class="fixed inset-0 bg-black/80 z-[100] flex items-center justify-center p-4 backdrop-blur-sm" @click.stop="downloadModalTrack = null">
        <div class="bg-surface rounded-xl shadow-2xl w-full max-w-xs border border-border-strong overflow-hidden" @click.stop="">
            <div class="p-4 border-b border-border-strong flex justify-between items-center bg-background">
                <div>
                    <h3 class="font-bold text-text-primary text-sm">Download Quality</h3>
                    <p class="text-xs text-text-muted truncate max-w-[200px]">{{ downloadModalTrack.name }}</p>
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

    <!-- Single Track Delete Download Modal -->
    <div v-if="trackDownloadToDelete" class="fixed inset-0 bg-black/80 z-[100] flex items-center justify-center p-4 backdrop-blur-sm" @click.stop="trackDownloadToDelete = null">
        <div class="bg-surface rounded-xl shadow-2xl w-full max-w-sm border border-border-strong overflow-hidden" @click.stop="">
            <div class="p-4 border-b border-border-strong flex justify-between items-center bg-background">
                <h3 class="font-bold text-text-primary text-base">Delete Local Download</h3>
                <button @click.stop="trackDownloadToDelete = null" class="text-text-muted hover:text-text-primary p-1">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
            </div>
            <div class="p-5 bg-background">
                <p class="text-text-secondary text-sm mb-2">
                    Are you sure you want to delete the downloaded file for <strong class="text-text-primary">"{{ trackDownloadToDelete.name }}"</strong>?
                </p>
                <p class="text-xs text-text-muted">
                    The file will be deleted from your disk, but the track will stay in your library and can still be streamed or downloaded again later.
                </p>
            </div>
            <div class="p-4 bg-background border-t border-border-strong flex justify-end gap-3">
                <button @click.stop="trackDownloadToDelete = null" class="px-4 py-2 text-sm text-text-muted hover:text-text-primary transition-colors">
                    Cancel
                </button>
                <button @click.stop="executeDeleteTrackDownload()" class="px-4 py-2 bg-danger hover:bg-danger-light text-white rounded text-sm font-bold transition-colors shadow">
                    Delete File
                </button>
            </div>
        </div>
    </div>

  </div>
</template>

