<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import PlaylistsDashboard from './components/PlaylistsDashboard.vue'
import WebPlayer from './components/WebPlayer.vue'
import { syncStore } from './syncStore.js'

const isLoggedIn = ref(false)
const isLoggingIn = ref(false)
const loginUrl = ref('')
const loginCode = ref('')
const loginError = ref(null)
let pollInterval = null

const checkStatus = async () => {
  try {
    const res = await fetch('/api/auth/status')
    const data = await res.json()
    isLoggedIn.value = data.logged_in
    isLoggingIn.value = data.is_logging_in
    loginError.value = data.error

    if (isLoggedIn.value) {
      stopPolling()
      syncStore.connect()
    }
  } catch (e) {
    console.error("Error checking status", e)
  }
}

const startPolling = () => {
  if (!pollInterval) {
    pollInterval = setInterval(checkStatus, 3000)
  }
}

const stopPolling = () => {
  if (pollInterval) {
    clearInterval(pollInterval)
    pollInterval = null
  }
}

const goHome = () => {
    window.dispatchEvent(new CustomEvent('navigate-home'))
    if (window.location.search) {
        history.pushState(null, '', window.location.pathname)
    }
}

const startLogin = async () => {
  try {
    const res = await fetch('/api/auth/device_login')
    const data = await res.json()
    
    if (data.status === 'waiting_for_user' || data.status === 'pending') {
      loginUrl.value = data.url
      loginCode.value = data.code
      isLoggingIn.value = true
      startPolling()
    } else if (data.status === 'already_logged_in') {
      isLoggedIn.value = true
      syncStore.connect()
    }
  } catch (e) {
    loginError.value = "Failed to initiate login"
    console.error(e)
  }
}

const logout = async () => {
  await fetch('/api/auth/logout', { method: 'POST' })
  isLoggedIn.value = false
  isLoggingIn.value = false
  loginUrl.value = ''
  loginCode.value = ''
}

onMounted(async () => {
  await checkStatus()
  if (isLoggingIn.value && !isLoggedIn.value) {
    await startLogin()
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>

<template>
  <div class="min-h-screen flex flex-col pb-24"> <!-- padding for bottom player -->
    <!-- Navbar -->
    <header class="bg-surface p-4 shadow-md flex justify-between items-center z-10 relative">
      <div class="flex items-center gap-2.5 md:gap-3 cursor-pointer select-none group" @click="goHome">
        <img src="/favicon.png" alt="Tidalarius Mascot" class="w-7 h-7 md:w-8 md:h-8 object-contain rounded-lg drop-shadow transition-transform group-hover:scale-105" />
        <h1 class="text-xl md:text-2xl font-bold text-accent group-hover:text-accent-light transition-colors">Tidalarius</h1>
      </div>
      <div v-if="isLoggedIn" class="flex items-center gap-2 md:gap-4">
        <span class="text-xs md:text-sm text-success flex items-center gap-1">
          <svg class="w-3 h-3" fill="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/></svg>
          <span class="hidden md:inline">Connected to Tidal</span>
        </span>
        <button @click="logout" class="text-xs md:text-sm bg-danger-dark hover:bg-danger px-2 md:px-3 py-1 rounded transition">Logout</button>
      </div>
    </header>

    <!-- Main Content -->
    <main class="flex-grow p-2 sm:p-4 md:p-6 flex justify-center items-start pt-6 md:pt-10">
      
      <!-- Login Section -->
      <div v-if="!isLoggedIn" class="w-full max-w-lg bg-surface p-8 rounded-xl shadow-2xl text-center border border-border-strong">
        <div class="mb-6 flex justify-center">
          <svg class="w-16 h-16 text-text-primary" viewBox="0 0 24 24" fill="currentColor">
            <!-- Simplified wave/music icon -->
            <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"/>
          </svg>
        </div>
        <h2 class="text-2xl font-bold mb-2">Connect to Tidal</h2>
        
        <div v-if="loginError" class="bg-red-900/50 border border-danger text-red-200 p-3 rounded mb-4">
          Error: {{ loginError }}
        </div>

        <div v-if="!isLoggingIn">
          <p class="mb-6 text-text-muted">Authorize Tidalarius to access your Tidal account to sync playlists and download music.</p>
          <button @click="startLogin" class="bg-text-primary hover:bg-text-secondary text-text-inverse font-bold py-3 px-8 rounded-full transition-colors w-full">
            Start Login Process
          </button>
        </div>
        
        <div v-else class="space-y-6">
          <p class="text-text-secondary">Please visit the following URL on any device to approve the login request:</p>
          
          <div class="bg-background p-4 rounded-lg flex flex-col items-center gap-2">
            <span class="text-sm text-text-muted uppercase tracking-wider">Your Login URL</span>
            <a :href="loginUrl" target="_blank" class="text-accent-light hover:text-green-300 font-mono break-all font-bold text-lg">
              {{ loginUrl }}
            </a>
          </div>
          
          <div v-if="loginCode" class="bg-background p-4 rounded-lg flex flex-col items-center gap-2">
            <span class="text-sm text-text-muted uppercase tracking-wider">Your Code</span>
            <span class="text-3xl font-mono tracking-widest font-bold text-text-primary">{{ loginCode }}</span>
          </div>

          <div class="flex items-center justify-center gap-3 text-text-muted mt-6">
            <svg class="animate-spin h-5 w-5 text-text-muted" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            <span>Waiting for you to authorize...</span>
          </div>
        </div>
      </div>
      
      <!-- Dashboard Section -->
      <div v-else class="w-full max-w-6xl">
        <PlaylistsDashboard />
      </div>
    </main>
    <WebPlayer v-if="isLoggedIn" />
  </div>
</template>
