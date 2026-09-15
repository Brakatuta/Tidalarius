import { reactive } from 'vue'

export const syncStore = reactive({
  syncState: {}, // track progress per playlist
  syncLogs: {},  // track logs per playlist
  lastDownloadedTrack: null,
  trackDeleted: null,
  ws: null,
  
  connect() {
    if (this.ws) return
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/api/sync/ws`
    this.ws = new WebSocket(wsUrl)
    
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data)
      const pid = data.playlist_id
      
      if (!this.syncState[pid]) this.syncState[pid] = {}
      if (!this.syncLogs[pid]) this.syncLogs[pid] = []
      
      if (data.type === 'sync_started') {
        this.syncState[pid].status = 'syncing'
        this.syncState[pid].progress = 0
      } else if (data.type === 'sync_progress') {
        this.syncState[pid].status = 'syncing'
        this.syncState[pid].progress = data.progress
        this.syncState[pid].current_track = data.current_track
        this.syncState[pid].quality = data.attempting_quality
      } else if (data.type === 'sync_log') {
        this.syncLogs[pid].push(data.message)
      } else if (data.type === 'sync_finished') {
        this.syncState[pid].status = 'idle'
        this.syncState[pid].report_url = data.report_url
        this.syncLogs[pid].push("SYNC FINISHED.")
      } else if (data.type === 'sync_error') {
        this.syncState[pid].status = 'error'
        this.syncState[pid].error = data.error
        this.syncLogs[pid].push(`ERROR: ${data.error}`)
      } else if (data.type === 'track_downloaded') {
        this.lastDownloadedTrack = { playlist_id: pid, track_name: data.track_name, quality: data.quality, timestamp: Date.now() }
      } else if (data.type === 'track_deleted') {
        this.trackDeleted = { playlist_id: pid, track_id: data.track_id, timestamp: Date.now() }
      }
    }
    
    this.ws.onclose = () => {
      this.ws = null
      setTimeout(() => this.connect(), 5000)
    }
  },
  
  startManualSync(playlist_id) {
    fetch(`/api/sync/start/${playlist_id}`, { method: 'POST' })
      .then(async res => {
        const data = await res.json()
        if (!this.syncState[playlist_id]) this.syncState[playlist_id] = {}
        if (!this.syncLogs[playlist_id]) this.syncLogs[playlist_id] = []
        
        if (!res.ok) {
            this.syncState[playlist_id].status = 'error'
            this.syncLogs[playlist_id].push("ERROR: " + (data.detail || "Request failed"))
            return
        }

        if (data.status === "already running") {
            this.syncState[playlist_id].status = 'syncing'
        } else {
            this.syncState[playlist_id].status = 'queued'
            this.syncLogs[playlist_id].push("Job queued. Waiting for worker...")
        }
    }).catch(e => {
        console.error("Failed to start sync", e)
    })
  },

  async pauseSync(playlist_id) {
    await fetch(`/api/sync/pause/${playlist_id}`, { method: 'POST' })
    if (this.syncState[playlist_id]) this.syncState[playlist_id].status = 'paused'
  },

  async resumeSync(playlist_id) {
    await fetch(`/api/sync/resume/${playlist_id}`, { method: 'POST' })
    if (this.syncState[playlist_id]) this.syncState[playlist_id].status = 'syncing'
  },

  async cancelSync(playlist_id) {
    await fetch(`/api/sync/cancel/${playlist_id}`, { method: 'POST' })
    if (this.syncState[playlist_id]) this.syncState[playlist_id].status = 'idle'
  },

  async fetchStatus(playlist_id) {
    try {
        const res = await fetch(`/api/sync/status/${playlist_id}`)
        if (res.ok) {
            const data = await res.json()
            if (!this.syncState[playlist_id]) this.syncState[playlist_id] = {}
            this.syncState[playlist_id].status = data.status
            this.syncState[playlist_id].progress = data.progress
            this.syncLogs[playlist_id] = data.logs || []
        }
    } catch (e) {
        console.error("Failed to fetch sync status", e)
    }
  }
})

