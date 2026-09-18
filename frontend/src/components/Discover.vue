<script setup>
import { ref } from 'vue'
import PlaylistDetail from './PlaylistDetail.vue'
import { playerStore } from '../playerStore.js'

const query = ref('')
const loading = ref(false)
const results = ref({ playlists: [], albums: [], tracks: [] })
const selectedItem = ref(null)

const PAGE_SIZE = 20
const pages = ref({ albums: 1, tracks: 1, playlists: 1 })
const totals = ref({ albums: 0, tracks: 0, playlists: 0 })
const categoryLoading = ref({ albums: false, tracks: false, playlists: false })

const totalPages = (category) => {
    const maxItems = Math.min(totals.value[category] || 0, 300)
    return Math.max(1, Math.ceil(maxItems / PAGE_SIZE))
}

const search = async () => {
    if (!query.value) return
    loading.value = true
    pages.value = { albums: 1, tracks: 1, playlists: 1 }
    try {
        const res = await fetch(`/api/music/search?query=${encodeURIComponent(query.value)}&limit=${PAGE_SIZE}&offset=0`)
        if (res.ok) {
            const data = await res.json()
            results.value = {
                playlists: data.playlists || [],
                albums: data.albums || [],
                tracks: data.tracks || []
            }
            if (data.totals) {
                totals.value = {
                    albums: data.totals.albums || 0,
                    tracks: data.totals.tracks || 0,
                    playlists: data.totals.playlists || 0
                }
            }
        }
    } catch (e) {
        console.error("Search failed", e)
    } finally {
        loading.value = false
    }
}

const changePage = async (category, newPage) => {
    if (categoryLoading.value[category] || !query.value) return
    const maxPage = totalPages(category)
    if (newPage < 1 || newPage > maxPage) return
    
    categoryLoading.value[category] = true
    const offset = (newPage - 1) * PAGE_SIZE
    try {
        const res = await fetch(`/api/music/search?query=${encodeURIComponent(query.value)}&category=${category}&offset=${offset}&limit=${PAGE_SIZE}`)
        if (res.ok) {
            const data = await res.json()
            results.value[category] = data[category] || []
            if (data.totals && data.totals[category] !== undefined) {
                totals.value[category] = data.totals[category]
            }
            pages.value[category] = newPage
        }
    } catch (e) {
        console.error(`Page change for ${category} failed`, e)
    } finally {
        categoryLoading.value[category] = false
    }
}

const openItem = (item) => {
    selectedItem.value = item
}

const playTrack = (track) => {
    if (playerStore.currentPlaylistId === `track_${track.tidal_id}`) {
        playerStore.togglePlayPause()
        return
    }
    // Determine quality from localStorage
    const streamQuality = localStorage.getItem('streamQuality') || 'HIGH'
    
    // Play immediately
    const trackToPlay = {
        id: track.tidal_id,
        tidal_id: track.tidal_id,
        title: track.title || track.name,
        artist: track.artist || track.artist_name || 'Unknown',
        album: track.album || 'Unknown',
        duration: track.duration,
        picture_url: track.picture_url,
        is_downloaded: false,
        quality: streamQuality,
        stream_url: `/api/music/stream/${track.tidal_id}?quality=${streamQuality}`
    }
    
    playerStore.playPlaylist(`track_${track.tidal_id}`, "Discover", [trackToPlay], 0)
}

const addToLibrary = async (item, event) => {
    event.stopPropagation() // Prevent opening
    try {
        const payload = {
            item_type: item.item_type || 'track',
            name: item.name || item.title,
            artist_name: item.artist_name || item.artist,
            picture_url: item.picture_url,
            sync_enabled: false,
            qualities: ["HIGH"]
        }
        const res = await fetch(`/api/playlists/${item.tidal_id}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        if (res.ok) {
            alert('Added to Library!')
        }
    } catch (e) {
        console.error(e)
    }
}

</script>

<template>
    <div class="relative w-full h-full min-h-[500px]">
        <div v-if="!selectedItem" class="w-full">
            <h2 class="text-3xl font-bold text-text-primary mb-6 border-b border-border-strong pb-4">Discover on Tidal</h2>
            
            <div class="mb-8 flex gap-2">
                <input v-model="query" @keyup.enter="search" type="text" placeholder="Search for tracks, albums, or playlists..." class="flex-grow bg-surface-elevated border border-border-highlight rounded-lg px-4 py-3 text-text-primary focus:outline-none focus:border-accent text-lg" />
                <button @click="search" class="bg-accent hover:bg-accent-light text-white font-bold px-6 py-3 rounded-lg transition">Search</button>
            </div>
            
            <div v-if="loading" class="flex justify-center my-12">
                <svg class="animate-spin h-10 w-10 text-accent" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
            </div>
            
            <div v-else-if="results.tracks.length || results.albums.length || results.playlists.length" class="space-y-12">
                
                <!-- Albums -->
                <div v-if="results.albums.length">
                    <div class="flex items-center justify-between mb-4">
                        <div class="flex items-center gap-3">
                            <h3 class="text-xl font-bold text-text-secondary">Albums</h3>
                            <span v-if="totals.albums" class="text-xs font-semibold px-2 py-0.5 rounded-full bg-surface-elevated text-text-muted border border-border-strong">
                                {{ totals.albums }} {{ totals.albums === 1 ? 'Album' : 'Albums' }}
                            </span>
                        </div>
                        <div v-if="totalPages('albums') > 1" class="flex items-center gap-2">
                            <button 
                                @click="changePage('albums', pages.albums - 1)" 
                                :disabled="pages.albums <= 1 || categoryLoading.albums"
                                class="px-3 py-1 text-xs font-semibold rounded bg-surface-elevated hover:bg-surface-elevated/80 disabled:opacity-30 disabled:cursor-not-allowed border border-border-strong text-text-primary transition flex items-center gap-1">
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
                                <span>Last</span>
                            </button>
                            <span class="text-xs text-text-muted font-medium px-1">
                                Page {{ pages.albums }} / {{ totalPages('albums') }}
                            </span>
                            <button 
                                @click="changePage('albums', pages.albums + 1)" 
                                :disabled="pages.albums >= totalPages('albums') || categoryLoading.albums"
                                class="px-3 py-1 text-xs font-semibold rounded bg-surface-elevated hover:bg-surface-elevated/80 disabled:opacity-30 disabled:cursor-not-allowed border border-border-strong text-text-primary transition flex items-center gap-1">
                                <span>Next</span>
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
                            </button>
                        </div>
                    </div>

                    <div class="wood-shelf-bg w-full rounded-lg shadow-2xl border-4 overflow-hidden relative" style="border-color: var(--wood-border);">
                        <!-- Loading Overlay -->
                        <div v-if="categoryLoading.albums" class="absolute inset-0 bg-black/40 backdrop-blur-[2px] z-50 flex items-center justify-center">
                            <svg class="animate-spin h-8 w-8 text-accent" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                        </div>

                        <div class="grid w-full" style="grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); grid-auto-rows: 280px;">
                            <div v-for="item in results.albums" :key="item.tidal_id" @click="openItem(item)" class="flex flex-col items-center justify-end pb-[55px] group cursor-pointer relative z-10">
                                
                                <div class="relative w-40 h-40 transition-transform duration-500 ease-out group-hover:-translate-y-8 group-hover:rotate-0" style="transform: perspective(800px) rotateX(15deg) translateY(10px); transform-origin: bottom center; filter: drop-shadow(0 15px 10px rgba(0,0,0,0.6));">
                                    <div class="absolute inset-0 bg-black-base rounded-full shadow-[0_5px_15px_rgba(0,0,0,0.8)] border border-border-subtle flex items-center justify-center overflow-hidden transition-all duration-700 group-hover:rotate-180 group-hover:shadow-[0_20px_30px_rgba(0,0,0,0.8)]">
                                        <div class="absolute inset-1 rounded-full border border-border-subtle-50"></div>
                                        <div class="absolute inset-3 rounded-full border border-border-subtle-50"></div>
                                        <div class="relative w-16 h-16 rounded-full overflow-hidden shadow-inner border border-border-dark bg-background z-10">
                                            <img v-if="item.picture_url" :src="item.picture_url" class="w-full h-full object-cover opacity-90" />
                                            <div class="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-2 h-2 bg-black-base rounded-full border border-border-strong"></div>
                                        </div>
                                    </div>
                                    <div class="absolute top-0 right-0 w-40 h-40 bg-surface rounded shadow-xl border border-border-strong overflow-hidden z-30 transition-transform duration-500 ease-out group-hover:-translate-x-10 group-hover:rotate-[-8deg]">
                                        <img v-if="item.picture_url" :src="item.picture_url" class="w-full h-full object-cover" />
                                    </div>
                                </div>
                                
                                <div class="absolute bottom-[24px] left-1/2 transform -translate-x-1/2 w-36 text-center z-20 pointer-events-none transition-transform duration-300 group-hover:scale-110">
                                    <div class="text-[10px] font-bold px-2 py-1 rounded shadow-[0_2px_4px_rgba(0,0,0,0.5)] truncate uppercase tracking-wider flex justify-between items-center"
                                         style="background: linear-gradient(to bottom, var(--brass-grad-top), var(--brass-grad-bottom)); color: var(--brass-text); border: 1px solid var(--brass-border);">
                                        <span class="truncate flex-grow text-left">{{ item.name }}</span>
                                        <button @click="addToLibrary(item, $event)" class="ml-1 pointer-events-auto hover:text-white" title="Add to Library">
                                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Bottom Pagination for Albums -->
                    <div v-if="totalPages('albums') > 1" class="flex justify-end items-center gap-2 mt-3">
                        <button 
                            @click="changePage('albums', pages.albums - 1)" 
                            :disabled="pages.albums <= 1 || categoryLoading.albums"
                            class="px-3 py-1 text-xs font-semibold rounded bg-surface-elevated hover:bg-surface-elevated/80 disabled:opacity-30 disabled:cursor-not-allowed border border-border-strong text-text-primary transition flex items-center gap-1">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
                            <span>Last</span>
                        </button>
                        <span class="text-xs text-text-muted font-medium px-1">
                            Page {{ pages.albums }} / {{ totalPages('albums') }}
                        </span>
                        <button 
                            @click="changePage('albums', pages.albums + 1)" 
                            :disabled="pages.albums >= totalPages('albums') || categoryLoading.albums"
                            class="px-3 py-1 text-xs font-semibold rounded bg-surface-elevated hover:bg-surface-elevated/80 disabled:opacity-30 disabled:cursor-not-allowed border border-border-strong text-text-primary transition flex items-center gap-1">
                            <span>Next</span>
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
                        </button>
                    </div>
                </div>

                <!-- Tracks (Permanently Open) -->
                <div v-if="results.tracks.length">
                    <div class="flex items-center justify-between mb-4">
                        <div class="flex items-center gap-3">
                            <h3 class="text-xl font-bold text-text-secondary">Tracks</h3>
                            <span v-if="totals.tracks" class="text-xs font-semibold px-2 py-0.5 rounded-full bg-surface-elevated text-text-muted border border-border-strong">
                                {{ totals.tracks }} {{ totals.tracks === 1 ? 'Track' : 'Tracks' }}
                            </span>
                        </div>
                        <div v-if="totalPages('tracks') > 1" class="flex items-center gap-2">
                            <button 
                                @click="changePage('tracks', pages.tracks - 1)" 
                                :disabled="pages.tracks <= 1 || categoryLoading.tracks"
                                class="px-3 py-1 text-xs font-semibold rounded bg-surface-elevated hover:bg-surface-elevated/80 disabled:opacity-30 disabled:cursor-not-allowed border border-border-strong text-text-primary transition flex items-center gap-1">
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
                                <span>Last</span>
                            </button>
                            <span class="text-xs text-text-muted font-medium px-1">
                                Page {{ pages.tracks }} / {{ totalPages('tracks') }}
                            </span>
                            <button 
                                @click="changePage('tracks', pages.tracks + 1)" 
                                :disabled="pages.tracks >= totalPages('tracks') || categoryLoading.tracks"
                                class="px-3 py-1 text-xs font-semibold rounded bg-surface-elevated hover:bg-surface-elevated/80 disabled:opacity-30 disabled:cursor-not-allowed border border-border-strong text-text-primary transition flex items-center gap-1">
                                <span>Next</span>
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
                            </button>
                        </div>
                    </div>

                    <div class="wood-shelf-bg w-full rounded-lg shadow-2xl border-4 overflow-hidden relative" style="border-color: var(--wood-border);">
                        <!-- Loading Overlay -->
                        <div v-if="categoryLoading.tracks" class="absolute inset-0 bg-black/40 backdrop-blur-[2px] z-50 flex items-center justify-center">
                            <svg class="animate-spin h-8 w-8 text-accent" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                        </div>

                        <div class="grid w-full" style="grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); grid-auto-rows: 280px;">
                            <div v-for="item in results.tracks" :key="item.tidal_id" @click="playTrack(item)" class="flex flex-col items-center justify-end pb-[55px] group cursor-pointer relative z-10">
                                
                                <div class="relative w-40 h-40 transition-transform duration-500 ease-out -translate-y-8 rotate-0" style="transform: perspective(800px) rotateX(15deg) translateY(-20px); filter: drop-shadow(0 15px 10px rgba(0,0,0,0.6));">
                                    <!-- Vinyl (shifted out) -->
                                    <div class="absolute inset-0 bg-black-base rounded-full shadow-[0_20px_30px_rgba(0,0,0,0.8)] border border-border-subtle flex items-center justify-center overflow-hidden rotate-180 translate-x-12 z-20">
                                        <div class="absolute inset-1 rounded-full border border-border-subtle-50"></div>
                                        <div class="absolute inset-3 rounded-full border border-border-subtle-50"></div>
                                        <div class="relative w-16 h-16 rounded-full overflow-hidden shadow-inner border border-border-dark bg-background z-10">
                                            <img v-if="item.picture_url" :src="item.picture_url" class="w-full h-full object-cover opacity-90" />
                                            <div class="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-2 h-2 bg-black-base rounded-full border border-border-strong"></div>
                                        </div>
                                    </div>
                                    <!-- Sleeve (shifted left) -->
                                    <div class="absolute top-0 right-0 w-40 h-40 bg-surface rounded shadow-xl border border-border-strong overflow-hidden z-30 -translate-x-10 rotate-[-8deg]">
                                        <img v-if="item.picture_url" :src="item.picture_url" class="w-full h-full object-cover" />
                                    </div>
                                    <!-- Play Overlay -->
                                    <div class="absolute inset-0 z-40 flex items-center justify-center transition-opacity"
                                         :class="(playerStore.currentPlaylistId === `track_${item.tidal_id}` && playerStore.isPlaying) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'">
                                        <div class="w-14 h-14 rounded-full flex items-center justify-center shrink-0 aspect-square bg-black/60 hover:bg-black/80 hover:scale-110 transition-all backdrop-blur-sm shadow-2xl cursor-pointer"
                                             style="transform: rotateX(-15deg);"
                                             @click.stop="playTrack(item)">
                                            <svg v-if="playerStore.currentPlaylistId === `track_${item.tidal_id}` && playerStore.isPlaying" class="w-7 h-7 text-white drop-shadow-lg shrink-0" fill="currentColor" viewBox="0 0 24 24"><path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z"/></svg>
                                            <svg v-else class="w-7 h-7 text-white drop-shadow-lg shrink-0 translate-x-0.5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>
                                        </div>
                                    </div>
                                </div>
                                
                                <div class="absolute bottom-[24px] left-1/2 transform -translate-x-1/2 w-36 text-center z-20 pointer-events-none transition-transform duration-300 group-hover:scale-110">
                                    <div class="text-[10px] font-bold px-2 py-1 rounded shadow-[0_2px_4px_rgba(0,0,0,0.5)] truncate uppercase tracking-wider flex justify-between items-center"
                                         style="background: linear-gradient(to bottom, var(--brass-grad-top), var(--brass-grad-bottom)); color: var(--brass-text); border: 1px solid var(--brass-border);">
                                        <span class="truncate flex-grow text-left">{{ item.title }}</span>
                                        <button @click="addToLibrary(item, $event)" class="ml-1 pointer-events-auto hover:text-white" title="Add to Library">
                                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Bottom Pagination for Tracks -->
                    <div v-if="totalPages('tracks') > 1" class="flex justify-end items-center gap-2 mt-3">
                        <button 
                            @click="changePage('tracks', pages.tracks - 1)" 
                            :disabled="pages.tracks <= 1 || categoryLoading.tracks"
                            class="px-3 py-1 text-xs font-semibold rounded bg-surface-elevated hover:bg-surface-elevated/80 disabled:opacity-30 disabled:cursor-not-allowed border border-border-strong text-text-primary transition flex items-center gap-1">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
                            <span>Last</span>
                        </button>
                        <span class="text-xs text-text-muted font-medium px-1">
                            Page {{ pages.tracks }} / {{ totalPages('tracks') }}
                        </span>
                        <button 
                            @click="changePage('tracks', pages.tracks + 1)" 
                            :disabled="pages.tracks >= totalPages('tracks') || categoryLoading.tracks"
                            class="px-3 py-1 text-xs font-semibold rounded bg-surface-elevated hover:bg-surface-elevated/80 disabled:opacity-30 disabled:cursor-not-allowed border border-border-strong text-text-primary transition flex items-center gap-1">
                            <span>Next</span>
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
                        </button>
                    </div>
                </div>

                <!-- Playlists -->
                <div v-if="results.playlists.length">
                    <div class="flex items-center justify-between mb-4">
                        <div class="flex items-center gap-3">
                            <h3 class="text-xl font-bold text-text-secondary">Playlists</h3>
                            <span v-if="totals.playlists" class="text-xs font-semibold px-2 py-0.5 rounded-full bg-surface-elevated text-text-muted border border-border-strong">
                                {{ totals.playlists }} {{ totals.playlists === 1 ? 'Playlist' : 'Playlists' }}
                            </span>
                        </div>
                        <div v-if="totalPages('playlists') > 1" class="flex items-center gap-2">
                            <button 
                                @click="changePage('playlists', pages.playlists - 1)" 
                                :disabled="pages.playlists <= 1 || categoryLoading.playlists"
                                class="px-3 py-1 text-xs font-semibold rounded bg-surface-elevated hover:bg-surface-elevated/80 disabled:opacity-30 disabled:cursor-not-allowed border border-border-strong text-text-primary transition flex items-center gap-1">
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
                                <span>Last</span>
                            </button>
                            <span class="text-xs text-text-muted font-medium px-1">
                                Page {{ pages.playlists }} / {{ totalPages('playlists') }}
                            </span>
                            <button 
                                @click="changePage('playlists', pages.playlists + 1)" 
                                :disabled="pages.playlists >= totalPages('playlists') || categoryLoading.playlists"
                                class="px-3 py-1 text-xs font-semibold rounded bg-surface-elevated hover:bg-surface-elevated/80 disabled:opacity-30 disabled:cursor-not-allowed border border-border-strong text-text-primary transition flex items-center gap-1">
                                <span>Next</span>
                                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
                            </button>
                        </div>
                    </div>

                    <div class="wood-shelf-bg w-full rounded-lg shadow-2xl border-4 overflow-hidden relative" style="border-color: var(--wood-border);">
                        <!-- Loading Overlay -->
                        <div v-if="categoryLoading.playlists" class="absolute inset-0 bg-black/40 backdrop-blur-[2px] z-50 flex items-center justify-center">
                            <svg class="animate-spin h-8 w-8 text-accent" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                        </div>

                        <div class="grid w-full" style="grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); grid-auto-rows: 280px;">
                            <div v-for="item in results.playlists" :key="item.tidal_id" @click="openItem(item)" class="flex flex-col items-center justify-end pb-[55px] group cursor-pointer relative z-10">
                                
                                <div class="relative w-40 h-40 transition-transform duration-500 ease-out group-hover:-translate-y-8 group-hover:rotate-0" style="transform: perspective(800px) rotateX(15deg) translateY(10px); filter: drop-shadow(0 15px 10px rgba(0,0,0,0.6));">
                                    <div class="absolute inset-0 bg-black-base rounded-full shadow-[0_5px_15px_rgba(0,0,0,0.8)] border border-border-subtle flex items-center justify-center overflow-hidden transition-all duration-700 group-hover:rotate-180 group-hover:shadow-[0_20px_30px_rgba(0,0,0,0.8)]">
                                        <div class="absolute inset-1 rounded-full border border-border-subtle-50"></div>
                                        <div class="absolute inset-3 rounded-full border border-border-subtle-50"></div>
                                        <div class="relative w-16 h-16 rounded-full overflow-hidden shadow-inner border border-border-dark bg-background z-10">
                                            <img v-if="item.picture_url" :src="item.picture_url" class="w-full h-full object-cover opacity-90" />
                                            <div class="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-2 h-2 bg-black-base rounded-full border border-border-strong"></div>
                                        </div>
                                    </div>
                                    <div class="absolute top-0 right-0 w-40 h-40 bg-surface rounded shadow-xl border border-border-strong overflow-hidden z-30 transition-transform duration-500 ease-out group-hover:-translate-x-10 group-hover:rotate-[-8deg]">
                                        <img v-if="item.picture_url" :src="item.picture_url" class="w-full h-full object-cover" />
                                    </div>
                                </div>
                                
                                <div class="absolute bottom-[24px] left-1/2 transform -translate-x-1/2 w-36 text-center z-20 pointer-events-none transition-transform duration-300 group-hover:scale-110">
                                    <div class="text-[10px] font-bold px-2 py-1 rounded shadow-[0_2px_4px_rgba(0,0,0,0.5)] truncate uppercase tracking-wider flex justify-between items-center"
                                         style="background: linear-gradient(to bottom, var(--brass-grad-top), var(--brass-grad-bottom)); color: var(--brass-text); border: 1px solid var(--brass-border);">
                                        <span class="truncate flex-grow text-left">{{ item.name }}</span>
                                        <button @click="addToLibrary(item, $event)" class="ml-1 pointer-events-auto hover:text-white" title="Add to Library">
                                            <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"></path></svg>
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Bottom Pagination for Playlists -->
                    <div v-if="totalPages('playlists') > 1" class="flex justify-end items-center gap-2 mt-3">
                        <button 
                            @click="changePage('playlists', pages.playlists - 1)" 
                            :disabled="pages.playlists <= 1 || categoryLoading.playlists"
                            class="px-3 py-1 text-xs font-semibold rounded bg-surface-elevated hover:bg-surface-elevated/80 disabled:opacity-30 disabled:cursor-not-allowed border border-border-strong text-text-primary transition flex items-center gap-1">
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"/></svg>
                            <span>Last</span>
                        </button>
                        <span class="text-xs text-text-muted font-medium px-1">
                            Page {{ pages.playlists }} / {{ totalPages('playlists') }}
                        </span>
                        <button 
                            @click="changePage('playlists', pages.playlists + 1)" 
                            :disabled="pages.playlists >= totalPages('playlists') || categoryLoading.playlists"
                            class="px-3 py-1 text-xs font-semibold rounded bg-surface-elevated hover:bg-surface-elevated/80 disabled:opacity-30 disabled:cursor-not-allowed border border-border-strong text-text-primary transition flex items-center gap-1">
                            <span>Next</span>
                            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/></svg>
                        </button>
                    </div>
                </div>
            </div>
            <div v-else-if="query && !loading" class="text-center text-text-muted mt-12">
                No results found.
            </div>
        </div>
        
        <div v-else class="w-full">
            <PlaylistDetail :playlist="selectedItem" @back="selectedItem = null" :is-discover="true" />
        </div>
    </div>
</template>
