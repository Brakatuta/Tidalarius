import { reactive } from 'vue'

export const playerStore = reactive({
  currentPlaylistId: null,
  currentPlaylistName: null,
  currentTrackIndex: -1,
  tracks: [], // list of track objects
  isPlaying: false,
  isShuffle: false,
  shuffledIndices: [],
  currentTrack: null, // the actual track object being played
  
  playPlaylist(playlistId, playlistName, tracks, startIndex = 0) {
    this.currentPlaylistId = playlistId
    this.currentPlaylistName = playlistName
    
    // Filter to only playable tracks
    this.tracks = tracks.filter(t => t.stream_url)
    
    if (this.tracks.length === 0) return
    
    // Find the actual index in the filtered playable tracks
    const originalTrack = tracks[startIndex]
    let playableIndex = 0
    if (originalTrack) {
        const found = this.tracks.findIndex(t => t.id === originalTrack.id)
        if (found !== -1) playableIndex = found
    }
    
    if (this.isShuffle) {
        this.generateShuffle()
        const shufflePos = this.shuffledIndices.indexOf(playableIndex)
        // Swap so the clicked track is first in shuffle queue
        if (shufflePos !== -1 && shufflePos !== 0) {
            const temp = this.shuffledIndices[0]
            this.shuffledIndices[0] = this.shuffledIndices[shufflePos]
            this.shuffledIndices[shufflePos] = temp
        }
    }
    
    this.currentTrackIndex = playableIndex
    this.updateCurrentTrack()
    this.isPlaying = true
  },
  
  toggleShuffle() {
      this.isShuffle = !this.isShuffle
      if (this.isShuffle && this.tracks.length > 0) {
          this.generateShuffle()
          // Ensure current track is first in new shuffle sequence
          if (this.currentTrackIndex !== -1) {
              const shufflePos = this.shuffledIndices.indexOf(this.currentTrackIndex)
              if (shufflePos !== -1 && shufflePos !== 0) {
                  const temp = this.shuffledIndices[0]
                  this.shuffledIndices[0] = this.shuffledIndices[shufflePos]
                  this.shuffledIndices[shufflePos] = temp
              }
          }
      }
  },
  
  generateShuffle() {
      const indices = Array.from(Array(this.tracks.length).keys())
      for (let i = indices.length - 1; i > 0; i--) {
          const j = Math.floor(Math.random() * (i + 1));
          [indices[i], indices[j]] = [indices[j], indices[i]]
      }
      this.shuffledIndices = indices
  },
  
  next() {
    if (this.tracks.length === 0) return
    
    if (this.isShuffle) {
        const currentIndexInShuffle = this.shuffledIndices.indexOf(this.currentTrackIndex)
        const nextIndexInShuffle = (currentIndexInShuffle + 1) % this.shuffledIndices.length
        this.currentTrackIndex = this.shuffledIndices[nextIndexInShuffle]
    } else {
        this.currentTrackIndex = (this.currentTrackIndex + 1) % this.tracks.length
    }
    this.updateCurrentTrack()
    this.isPlaying = true
  },
  
  previous() {
    if (this.tracks.length === 0) return
    
    if (this.isShuffle) {
        const currentIndexInShuffle = this.shuffledIndices.indexOf(this.currentTrackIndex)
        const prevIndexInShuffle = (currentIndexInShuffle - 1 + this.shuffledIndices.length) % this.shuffledIndices.length
        this.currentTrackIndex = this.shuffledIndices[prevIndexInShuffle]
    } else {
        this.currentTrackIndex = (this.currentTrackIndex - 1 + this.tracks.length) % this.tracks.length
    }
    this.updateCurrentTrack()
    this.isPlaying = true
  },
  
  updateCurrentTrack() {
    if (this.currentTrackIndex >= 0 && this.currentTrackIndex < this.tracks.length) {
        this.currentTrack = this.tracks[this.currentTrackIndex]
    } else {
        this.currentTrack = null
    }
  },
  
  togglePlayPause() {
      if (this.currentTrack) {
          this.isPlaying = !this.isPlaying
      }
  },
  
  removeTrack(trackId) {
      if (this.tracks.length === 0) return;
      
      const indexToRemove = this.tracks.findIndex(t => t.id === trackId);
      if (indexToRemove === -1) return;
      
      if (this.currentTrack && this.currentTrack.id === trackId) {
          this.isPlaying = false;
      }
      
      this.tracks.splice(indexToRemove, 1);
      
      if (this.tracks.length === 0) {
          this.currentTrack = null;
          this.currentTrackIndex = -1;
          this.isPlaying = false;
          return;
      }
      
      if (indexToRemove < this.currentTrackIndex) {
          this.currentTrackIndex--;
      } else if (indexToRemove === this.currentTrackIndex) {
          if (this.currentTrackIndex >= this.tracks.length) {
              this.currentTrackIndex = 0;
          }
      }
      
      if (this.isShuffle) {
          this.generateShuffle();
      }
      
      this.updateCurrentTrack();
  }
})

