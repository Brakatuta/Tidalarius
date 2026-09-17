<script setup>
import { ref, onMounted } from 'vue'

const emit = defineEmits(['close', 'logout'])

const streamQuality = ref('HIGH')

onMounted(() => {
    streamQuality.value = localStorage.getItem('streamQuality') || 'HIGH'
})

const applyStreamQuality = () => {
    localStorage.setItem('streamQuality', streamQuality.value)
    window.dispatchEvent(new CustomEvent('streamQualityChanged'))
}
</script>

<template>
    <div class="fixed inset-0 bg-black-base/80 flex items-center justify-center z-50 p-4" @click.self="$emit('close')">
        <div class="bg-surface rounded-xl shadow-2xl border border-border-strong w-full max-w-sm overflow-hidden">
            <div class="bg-background p-4 border-b border-border-strong flex justify-between items-center">
                <h3 class="text-text-primary font-bold text-lg flex items-center gap-2">
                    <svg class="w-5 h-5 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                    Settings
                </h3>
                <button @click="$emit('close')" class="text-text-muted hover:text-text-primary">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
                </button>
            </div>
            
            <div class="p-6 space-y-6">
                <!-- Tidal Connection -->
                <div class="flex items-center justify-between p-4 bg-background rounded-lg border border-border-strong">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-full bg-surface-elevated flex items-center justify-center text-text-primary">
                            <svg class="w-6 h-6" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 14.5v-9l6 4.5-6 4.5z"/></svg>
                        </div>
                        <div>
                            <h4 class="text-text-primary font-bold">Tidal Account</h4>
                            <span class="text-xs text-success flex items-center gap-1">
                                <svg class="w-2 h-2" fill="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/></svg>
                                Connected
                            </span>
                        </div>
                    </div>
                    <button @click="$emit('logout')" class="text-xs bg-danger-dark hover:bg-danger px-3 py-1.5 text-white font-bold rounded transition">
                        Logout
                    </button>
                </div>

                <!-- Stream Quality -->
                <div>
                    <h4 class="text-text-primary font-bold mb-2">Streaming Quality</h4>
                    <p class="text-xs text-text-secondary mb-3">Fallback will automatically step down if a quality is unavailable.</p>
                    <select v-model="streamQuality" @change="applyStreamQuality" class="w-full bg-background border border-border-strong text-text-primary rounded px-3 py-2 focus:outline-none focus:border-accent">
                        <option value="LOW">Low (96kbps)</option>
                        <option value="HIGH">High (320kbps)</option>
                        <option value="LOSSLESS">Lossless (CD Quality)</option>
                        <option value="MAX">Max (Hi-Res)</option>
                    </select>
                </div>
            </div>
        </div>
    </div>
</template>
