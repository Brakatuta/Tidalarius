<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const playlists = ref([])
const loading = ref(true)
const error = ref(null)
const saving = ref(false)

const syncState = ref({}) // track progress per playlist
const syncLogs = ref({})  // track logs per playlist
const activeMonitorId = ref(null) // ID of playlist currently viewed in modal
const scheduleModalPlaylist = ref(null) // Playlist object for schedule modal
let ws = null

const qualityOptions = ['LOW', 'HIGH', 'LOSSLESS', 'HI_RES_LOSSLESS']
const commonSchedules = [
  { label: 'Never (Manual Only)', value: null },
  { label: 'Every hour', value: '0 * * * *' },
  { label: 'Every 6 hours', value: '0 */6 * * *' },
  { label: 'Daily at midnight', value: '0 0 * * *' },
  { label: 'Daily at 3 AM', value: '0 3 * * *' },
  { label: 'Weekly (Sunday midnight)', value: '0 0 * * 0' }
]

const connectWebSocket = () => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  // For dev we proxy ws via vite if possible, or directly use 8000
  // Here we use current host (handled by Vite proxy / backend serve)
  const wsUrl = `${protocol}//${window.location.host}/api/sync/ws`
  ws = new WebSocket(wsUrl)
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.type === 'sync_started') {
      if (!syncState.value[data.playlist_id]) syncState.value[data.playlist_id] = {}
      if (!syncLogs.value[data.playlist_id]) syncLogs.value[data.playlist_id] = []
      syncState.value[data.playlist_id].status = 'syncing'
      syncState.value[data.playlist_id].progress = 0
    } else if (data.type === 'sync_progress') {
      if (!syncState.value[data.playlist_id]) syncState.value[data.playlist_id] = {}
      syncState.value[data.playlist_id].progress = data.progress
      syncState.value[data.playlist_id].current_track = data.current_track
      syncState.value[data.playlist_id].quality = data.attempting_quality
    } else if (data.type === 'sync_log') {
      if (!syncLogs.value[data.playlist_id]) syncLogs.value[data.playlist_id] = []
      syncLogs.value[data.playlist_id].push(data.message)
      setTimeout(() => {
        const el = document.getElementById('terminal-logs')
        if (el) el.scrollTop = el.scrollHeight
      }, 50)
    } else if (data.type === 'sync_finished') {
      if (syncState.value[data.playlist_id]) {
        syncState.value[data.playlist_id].status = 'idle'
        syncState.value[data.playlist_id].report_url = data.report_url
      }
      if (!syncLogs.value[data.playlist_id]) syncLogs.value[data.playlist_id] = []
      syncLogs.value[data.playlist_id].push("SYNC FINISHED.")
      fetchPlaylists() // refresh DB status
    } else if (data.type === 'sync_error') {
      if (syncState.value[data.playlist_id]) {
        syncState.value[data.playlist_id].status = 'error'
        syncState.value[data.playlist_id].error = data.error
      }
      if (!syncLogs.value[data.playlist_id]) syncLogs.value[data.playlist_id] = []
      syncLogs.value[data.playlist_id].push(`ERROR: ${data.error}`)
    }
  }
  
  ws.onclose = () => {
    setTimeout(connectWebSocket, 5000) // Reconnect on close
  }
}

const fetchPlaylists = async () => {
  loading.value = true
  error.value = null
  try {
    const res = await fetch('/api/playlists/')
    if (!res.ok) throw new Error("Failed to fetch playlists")
    playlists.value = await res.json()
    // Initialize sync state from db
    playlists.value.forEach(p => {
      if (!syncState.value[p.tidal_id]) {
        syncState.value[p.tidal_id] = { status: p.sync_status || 'idle' }
      }
    })
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

const toggleSync = async (playlist) => {
  playlist.sync_enabled = !playlist.sync_enabled
  await saveConfig(playlist)
}

const saveConfig = async (playlist) => {
  saving.value = true
  try {
    const payload = {
      sync_enabled: playlist.sync_enabled,
      qualities: playlist.qualities,
      schedule: playlist.schedule
    }
    
    const res = await fetch(`/api/playlists/${playlist.tidal_id}/config`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
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

const startManualSync = async (playlist_id) => {
  try {
    await fetch(`/api/sync/start/${playlist_id}`, { method: 'POST' })
    if (!syncState.value[playlist_id]) syncState.value[playlist_id] = {}
    if (!syncLogs.value[playlist_id]) syncLogs.value[playlist_id] = []
    syncState.value[playlist_id].status = 'queued'
    syncLogs.value[playlist_id].push("Job queued. Waiting for worker...")
    activeMonitorId.value = playlist_id
  } catch(e) {
    alert("Failed to start sync")
  }
}

const controlSync = async (action, playlist_id) => {
  try {
    const res = await fetch(`/api/sync/${action}/${playlist_id}`, { method: 'POST' })
    const data = await res.json()
    if (data.status === action || data.status === `${action}d`) {
      if (action === 'pause') syncState.value[playlist_id].status = 'paused'
      if (action === 'resume') syncState.value[playlist_id].status = 'syncing'
      if (action === 'cancel') syncState.value[playlist_id].status = 'idle'
      
      syncLogs.value[playlist_id].push(`[USER ACTION] Sync ${action}d`)
      setTimeout(() => {
        const el = document.getElementById('terminal-logs')
        if (el) el.scrollTop = el.scrollHeight
      }, 50)
    }
  } catch(e) {
    console.error(`Failed to ${action} sync`, e)
  }
}

onMounted(() => {
  fetchPlaylists()
  connectWebSocket()
})

onUnmounted(() => {
  if (ws) ws.close()
})
</script>

<template>
  <div class="bg-gray-800 rounded-xl shadow-lg border border-gray-700 overflow-hidden">
    <div class="p-6 border-b border-gray-700 flex justify-between items-center bg-gray-800 sticky top-0 z-10">
      <div>
        <h2 class="text-2xl font-bold">Your Playlists</h2>
        <p class="text-gray-400 text-sm">Select playlists to synchronize</p>
      </div>
      <button @click="fetchPlaylists" class="bg-gray-700 hover:bg-gray-600 px-4 py-2 rounded transition flex items-center gap-2">
        <svg v-if="loading" class="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <svg v-else class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
        Refresh
      </button>
    </div>
    
    <div v-if="error" class="p-6 text-red-400 bg-red-900/20">
      Error: {{ error }}
    </div>

    <div v-else-if="loading && playlists.length === 0" class="p-12 text-center text-gray-500">
      Loading your playlists...
    </div>

    <div v-else class="divide-y divide-gray-700 max-h-[70vh] overflow-y-auto">
      <div v-for="playlist in playlists" :key="playlist.tidal_id" class="p-4 hover:bg-gray-750 transition flex flex-col md:flex-row gap-4 items-start md:items-center">
        
        <!-- Cover & Title -->
        <div class="flex items-center gap-4 flex-1">
          <img v-if="playlist.picture_url" :src="playlist.picture_url" class="w-16 h-16 rounded object-cover shadow" />
          <div v-else class="w-16 h-16 rounded bg-gray-700 flex items-center justify-center text-gray-500 shadow">
            <svg class="w-8 h-8" fill="currentColor" viewBox="0 0 20 20"><path d="M18 3a1 1 0 00-1.196-.98l-10 2A1 1 0 006 5v9.114A4.369 4.369 0 005 14c-1.657 0-3 .895-3 2s1.343 2 3 2 3-.895 3-2V7.236l8-1.6V11.114A4.369 4.369 0 0015 11c-1.657 0-3 .895-3 2s1.343 2 3 2 3-.895 3-2V3z"></path></svg>
          </div>
          
          <div>
            <h3 class="font-bold text-lg text-white">{{ playlist.name }}</h3>
            <p class="text-sm text-gray-400">{{ playlist.num_tracks }} tracks</p>
          </div>
        </div>
        
        <!-- Config & Sync Controls -->
        <div class="flex flex-col flex-1 gap-3">
          
          <div class="flex flex-col xl:flex-row items-start xl:items-center justify-between gap-4 bg-gray-900/50 p-3 rounded-lg border border-gray-700 w-full">
            <!-- Quality Select -->
            <div class="flex flex-col">
              <label class="text-xs text-gray-500 mb-1 uppercase tracking-wide">Quality Priority (Fallback Order)</label>
              <div class="flex gap-2">
                <label v-for="q in qualityOptions" :key="q" class="flex items-center gap-1 text-sm cursor-pointer text-gray-300">
                  <input type="checkbox" :value="q" v-model="playlist.qualities" @change="saveConfig(playlist)" class="accent-green-500 bg-gray-800 border-gray-600 rounded">
                  {{ q === 'HI_RES_LOSSLESS' ? 'MAX' : q }}
                </label>
              </div>
            </div>
            
            <div class="flex items-center gap-4 ml-auto">
              <!-- Sync Now Button -->
              <div class="flex gap-2">
                <button v-if="syncState[playlist.tidal_id]?.status === 'syncing' || syncState[playlist.tidal_id]?.status === 'queued'"
                        @click="activeMonitorId = playlist.tidal_id"
                        class="bg-gray-700 hover:bg-gray-600 text-xs px-3 py-1.5 rounded text-white font-bold transition flex items-center gap-2">
                  <span class="flex h-2 w-2 relative">
                    <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                    <span class="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                  </span>
                  View Progress
                </button>
                <button v-else @click="startManualSync(playlist.tidal_id)"
                        class="bg-blue-600 hover:bg-blue-500 text-xs px-3 py-1.5 rounded text-white font-bold transition">
                  Sync Now
                </button>
              </div>
              
              <!-- Sync Toggle & Settings -->
              <div class="flex items-center gap-2">
                <span class="text-xs text-gray-400">Auto-Sync</span>
                <button @click="toggleSync(playlist)" 
                        class="relative inline-flex items-center h-6 rounded-full w-11 transition-colors focus:outline-none"
                        :class="playlist.sync_enabled ? 'bg-green-500' : 'bg-gray-600'">
                  <span class="inline-block w-4 h-4 transform bg-white rounded-full transition-transform"
                        :class="playlist.sync_enabled ? 'translate-x-6' : 'translate-x-1'"></span>
                </button>
                <button @click="scheduleModalPlaylist = playlist" 
                        class="p-1 text-gray-400 hover:text-white transition-colors"
                        title="Sync Schedule Settings">
                  <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                </button>
              </div>
            </div>
          </div>
          
          <!-- Live Feed / Progress Bar -->
          <div v-if="syncState[playlist.tidal_id]?.status === 'syncing'" class="bg-gray-900 rounded p-3 text-xs w-full">
            <div class="flex justify-between text-gray-400 mb-1">
              <span>Downloading: <span class="text-white">{{ syncState[playlist.tidal_id]?.current_track }}</span></span>
              <span>{{ syncState[playlist.tidal_id]?.progress || 0 }}%</span>
            </div>
            <div class="w-full bg-gray-700 rounded-full h-1.5 mb-1">
              <div class="bg-blue-500 h-1.5 rounded-full transition-all duration-300" :style="`width: ${syncState[playlist.tidal_id]?.progress || 0}%`"></div>
            </div>
            <div class="text-gray-500">Trying quality: {{ syncState[playlist.tidal_id]?.quality }}</div>
          </div>
          
          <!-- Report Link -->
          <div v-if="syncState[playlist.tidal_id]?.report_url" class="text-xs">
            <a :href="syncState[playlist.tidal_id].report_url" target="_blank" class="text-blue-400 hover:underline">Download Sync Report (.log)</a>
          </div>

        </div>
      </div>
    </div>
    
    <!-- Live Monitor Modal -->
    <div v-if="activeMonitorId" class="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div class="bg-gray-900 border border-gray-700 rounded-xl shadow-2xl w-full max-w-4xl flex flex-col h-[80vh]">
        <!-- Header -->
        <div class="p-4 border-b border-gray-700 flex justify-between items-center bg-gray-800 rounded-t-xl">
          <div class="flex items-center gap-3">
            <h3 class="font-bold text-lg text-white">Live Sync Monitor</h3>
            <span v-if="syncState[activeMonitorId]?.status === 'syncing'" class="flex h-3 w-3 relative">
              <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
              <span class="relative inline-flex rounded-full h-3 w-3 bg-green-500"></span>
            </span>
          </div>
          <button @click="activeMonitorId = null" class="text-gray-400 hover:text-white transition">
            <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
          </button>
        </div>
        
        <!-- Progress Bar Summary -->
        <div v-if="syncState[activeMonitorId]?.status === 'syncing'" class="p-4 bg-gray-800/50 border-b border-gray-700">
          <div class="flex justify-between text-sm text-gray-300 mb-2">
            <span>{{ syncState[activeMonitorId]?.current_track || 'Preparing...' }}</span>
            <span>{{ syncState[activeMonitorId]?.progress || 0 }}%</span>
          </div>
          <div class="w-full bg-gray-700 rounded-full h-2">
            <div class="bg-green-500 h-2 rounded-full transition-all duration-300" :style="`width: ${syncState[activeMonitorId]?.progress || 0}%`"></div>
          </div>
        </div>
        
        <!-- Terminal Logs -->
        <div class="flex-1 overflow-y-auto p-4 font-mono text-sm bg-black text-green-400 flex flex-col gap-1" id="terminal-logs">
          <div v-for="(log, idx) in (syncLogs[activeMonitorId] || [])" :key="idx" :class="{'text-red-400': log.includes('FAILED') || log.includes('ERROR'), 'text-blue-400': log.includes('SUCCESS')}">
            <span class="text-gray-600 mr-2">></span> {{ log }}
          </div>
          <div v-if="syncState[activeMonitorId]?.status === 'syncing'" class="animate-pulse mt-2">_</div>
        </div>
        
        <!-- Footer -->
        <div class="p-4 border-t border-gray-700 flex justify-between gap-3 bg-gray-800 rounded-b-xl">
          <div class="flex gap-2" v-if="syncState[activeMonitorId]?.status === 'syncing' || syncState[activeMonitorId]?.status === 'paused'">
            <button v-if="syncState[activeMonitorId]?.status === 'syncing'" @click="controlSync('pause', activeMonitorId)" class="bg-yellow-600 hover:bg-yellow-500 text-white px-4 py-2 rounded text-sm transition font-bold">
              Pause
            </button>
            <button v-if="syncState[activeMonitorId]?.status === 'paused'" @click="controlSync('resume', activeMonitorId)" class="bg-green-600 hover:bg-green-500 text-white px-4 py-2 rounded text-sm transition font-bold">
              Resume
            </button>
            <button @click="controlSync('cancel', activeMonitorId)" class="bg-red-600 hover:bg-red-500 text-white px-4 py-2 rounded text-sm transition font-bold">
              Cancel
            </button>
          </div>
          <div v-else></div>

          <div class="flex gap-2">
            <a v-if="syncState[activeMonitorId]?.report_url" :href="syncState[activeMonitorId].report_url" target="_blank" class="bg-blue-600 hover:bg-blue-500 text-white px-4 py-2 rounded text-sm transition">
              Download Report
            </a>
            <button @click="activeMonitorId = null" class="bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded text-sm transition">
              Close Monitor
            </button>
          </div>
        </div>
      </div>
    </div>
    
    <!-- Schedule Modal -->
    <div v-if="scheduleModalPlaylist" class="fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
      <div class="bg-gray-800 rounded-xl shadow-2xl border border-gray-700 w-full max-w-md overflow-hidden">
        <div class="bg-gray-900 p-4 border-b border-gray-700 flex justify-between items-center">
          <h3 class="text-white font-bold text-lg">Sync Schedule</h3>
          <button @click="scheduleModalPlaylist = null" class="text-gray-400 hover:text-white">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
          </button>
        </div>
        
        <div class="p-6">
          <p class="text-gray-300 text-sm mb-4">Set the synchronization schedule for <strong>{{ scheduleModalPlaylist.name }}</strong>.</p>
          
          <div class="space-y-4">
            <label class="block">
              <span class="text-gray-400 text-sm">Preset Schedules</span>
              <select v-model="scheduleModalPlaylist.schedule" class="mt-1 block w-full bg-gray-900 border border-gray-700 rounded-md text-white px-3 py-2 focus:ring-green-500 focus:border-green-500">
                <option v-for="opt in commonSchedules" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
                <option value="custom">Custom Cron Expression</option>
              </select>
            </label>
            
            <label class="block" v-if="scheduleModalPlaylist.schedule && !commonSchedules.find(o => o.value === scheduleModalPlaylist.schedule)">
              <span class="text-gray-400 text-sm">Custom Cron Expression</span>
              <input type="text" v-model="scheduleModalPlaylist.schedule" placeholder="* * * * *" class="mt-1 block w-full bg-gray-900 border border-gray-700 rounded-md text-white px-3 py-2 font-mono focus:ring-green-500 focus:border-green-500">
              <p class="mt-1 text-xs text-gray-500">Standard 5-part cron syntax.</p>
            </label>
          </div>
        </div>
        
        <div class="p-4 bg-gray-900 border-t border-gray-700 flex justify-end gap-3">
          <button @click="scheduleModalPlaylist = null" class="px-4 py-2 text-sm text-gray-400 hover:text-white transition-colors">Cancel</button>
          <button @click="saveConfig(scheduleModalPlaylist); scheduleModalPlaylist = null" class="px-4 py-2 bg-green-600 hover:bg-green-500 text-white rounded text-sm font-bold transition-colors">Save Schedule</button>
        </div>
      </div>
    </div>

  </div>
</template>

<style>
.hover\:bg-gray-750:hover {
  background-color: rgba(55, 65, 81, 0.5);
}
</style>

