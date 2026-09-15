<script setup>
import { ref, onMounted } from 'vue'
import PlaylistDetail from './PlaylistDetail.vue'

const playlists = ref([])
const loading = ref(true)
const selectedPlaylist = ref(null)

const fetchPlaylists = async () => {
    loading.value = true
    try {
        const res = await fetch('/api/playlists/')
        if (res.ok) {
            playlists.value = await res.json()
            
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
})

const openPlaylist = (playlist) => {
    selectedPlaylist.value = playlist
    history.pushState({ playlistId: playlist.tidal_id }, '', `?playlist=${playlist.tidal_id}`)
}

const closePlaylist = () => {
    selectedPlaylist.value = null
    history.pushState(null, '', window.location.pathname)
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
                    
                    <!-- Vinyl Disc Design Leaning on Shelf -->
                    <div class="relative w-40 h-40 transition-transform duration-500 ease-out group-hover:-translate-y-8 group-hover:rotate-0" 
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

  </div>
</template>

