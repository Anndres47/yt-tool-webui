<template>
  <div>
    <div class="section-header">
      <h1 class="section-title">Download</h1>
      <span class="section-sub">yt-dlp · ytarchive</span>
    </div>

    <!-- URL + Mode -->
    <div class="panel">
      <div class="panel-label">Source</div>

      <div class="field">
        <label class="field-label">YouTube URL</label>
        <input
          type="url"
          v-model="url"
          placeholder="https://www.youtube.com/watch?v=..."
          :disabled="running"
        />
      </div>

      <div class="field">
        <label class="field-label">Mode</label>
        <div class="mode-pills">
          <button
            v-for="m in modes"
            :key="m.value"
            :class="['mode-pill', { active: mode === m.value }]"
            :disabled="running"
            @click="mode = m.value"
          >{{ m.label }}</button>
        </div>
      </div>

      <div class="field" v-if="mode !== 'audio'">
        <label class="field-label">Quality</label>
        <div class="quality-pills">
          <button
            v-for="q in qualities"
            :key="q.value"
            :class="['q-pill', { active: quality === q.value }]"
            :disabled="running"
            @click="quality = q.value"
          >{{ q.label }}</button>
        </div>
      </div>

      <div class="field" v-if="mode === 'audio'">
        <label
          :class="['toggle-row', { checked: reencodeAudio }]"
          @click="!running && (reencodeAudio = !reencodeAudio)"
        >
          <div class="toggle-box">
            <svg class="toggle-check" viewBox="0 0 8 8" fill="none">
              <path d="M1 4l2 2 4-4" stroke="#0a0a0b" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          Re-encode to MP3 320kbps via ffmpeg
        </label>
      </div>
    </div>

    <!-- Actions -->
    <div class="panel">
      <div class="btn-row">
        <button class="btn btn-primary" @click="startDownload" :disabled="running || !url.trim()">
          <svg v-if="!running" width="13" height="13" viewBox="0 0 13 13" fill="none">
            <path d="M6.5 1v7.5M3 6l3.5 3.5L10 6M1 11.5h11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span v-if="running" class="spinner"></span>
          {{ running ? 'Downloading…' : 'Download' }}
        </button>

        <button
          v-if="running && mode !== 'livestream'"
          class="btn btn-danger"
          @click="cancel"
        >Cancel</button>

        <button
          v-if="running && mode === 'livestream'"
          class="btn btn-danger"
          @click="cancel"
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <rect x="2" y="2" width="8" height="8" rx="1" stroke="currentColor" stroke-width="1.5"/>
          </svg>
          Abort &amp; Save
        </button>
      </div>

      <!-- Progress -->
      <div class="progress-block" v-if="running || progressMsg">
        <template v-if="running">
          <div class="progress-header">
            <div>
              <div v-if="isLive" class="live-badge">
                <div class="live-dot"></div>
                Live — In progress
              </div>
              <div v-else class="progress-pct">{{ percent.toFixed(1) }}<span style="font-size:14px;font-weight:400;color:var(--muted)">%</span></div>
            </div>
            <div class="progress-meta">
              <span v-if="speed && !isLive">{{ speed }}</span>
              <span v-if="eta && !isLive">ETA {{ eta }}</span>
            </div>
          </div>
          <div class="progress-track">
            <div
              class="progress-fill"
              :class="{ indeterminate: isLive }"
              :style="{ width: isLive ? '' : percent + '%' }"
            ></div>
          </div>
        </template>

        <div v-if="progressMsg" :class="['msg', `msg-${progressMsg.type}`]">
          {{ progressMsg.text }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'

const modes = [
  { value: 'video', label: 'Video' },
  { value: 'livestream', label: 'Livestream' },
  { value: 'audio', label: 'Audio' },
]

const qualities = [
  { value: 'best', label: 'Best' },
  { value: '1080p', label: '1080p' },
  { value: '720p', label: '720p' },
  { value: '480p', label: '480p' },
  { value: '360p', label: '360p' },
]

const url = ref('')
const mode = ref('video')
const quality = ref('best')
const reencodeAudio = ref(false)

const running = ref(false)
const percent = ref(0)
const speed = ref('')
const eta = ref('')
const isLive = ref(false)
const progressMsg = ref(null)

let currentJobId = null
let eventSource = null

const startDownload = async () => {
  if (!url.value.trim()) return

  running.value = true
  percent.value = 0
  speed.value = ''
  eta.value = ''
  isLive.value = false
  progressMsg.value = null

  try {
    const form = new FormData()
    form.append('url', url.value)
    form.append('mode', mode.value)
    form.append('quality', quality.value)
    form.append('reencode_audio', reencodeAudio.value ? 'true' : 'false')

    const res = await axios.post('/api/download', form)
    currentJobId = res.data.job_id

    eventSource = new EventSource(`/api/download/progress/${currentJobId}`)

    eventSource.onmessage = (e) => {
      const data = JSON.parse(e.data)

      if (data.error) {
        progressMsg.value = { type: 'error', text: data.error }
        finish()
        return
      }
      if (data.done) {
        percent.value = 100
        progressMsg.value = { type: 'success', text: 'Download complete!' }
        finish()
        return
      }
      if (data.live) {
        isLive.value = true
        return
      }
      if (data.percent !== undefined) {
        percent.value = data.percent
        speed.value = data.speed || ''
        eta.value = data.eta || ''
      }
    }

    eventSource.onerror = () => {
      progressMsg.value = { type: 'error', text: 'Connection to server lost.' }
      finish()
    }
  } catch (err) {
    progressMsg.value = { type: 'error', text: err.response?.data?.detail ?? err.message }
    running.value = false
  }
}

const cancel = async () => {
  if (!currentJobId) return
  try { await axios.post(`/api/download/cancel/${currentJobId}`) } catch (_) {}
}

const finish = () => {
  eventSource?.close()
  eventSource = null
  currentJobId = null
  running.value = false
}
</script>

<style scoped>
.spinner {
  display: inline-block;
  width: 11px;
  height: 11px;
  border: 1.5px solid rgba(0,0,0,0.3);
  border-top-color: #0a0a0b;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
