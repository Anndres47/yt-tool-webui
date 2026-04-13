<template>
  <div>
    <div class="card">
      <h2>Download</h2>

      <div class="field">
        <label>YouTube URL</label>
        <input type="url" v-model="url" placeholder="https://www.youtube.com/watch?v=..." :disabled="running" />
      </div>

      <div class="field">
        <label>Mode</label>
        <select v-model="mode" :disabled="running">
          <option value="video">Video</option>
          <option value="livestream">Livestream</option>
          <option value="audio">Audio</option>
        </select>
      </div>

      <div class="field" v-if="mode !== 'audio'">
        <label>Quality</label>
        <select v-model="quality" :disabled="running">
          <option value="best">Best (default)</option>
          <option value="1080p">1080p</option>
          <option value="720p">720p</option>
          <option value="480p">480p</option>
          <option value="360p">360p</option>
        </select>
      </div>

      <label v-if="mode === 'audio'" class="check-row">
        <input type="checkbox" v-model="reencodeAudio" :disabled="running" />
        Re-encode to MP3 320kbps (via ffmpeg)
      </label>

      <div class="btn-row">
        <button class="btn btn-primary" @click="startDownload" :disabled="running || !url">
          {{ running ? 'Downloading...' : 'Download' }}
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
        >Abort &amp; Save</button>
      </div>
    </div>

    <!-- Progress -->
    <div class="card" v-if="running || progressMsg">
      <div class="progress-wrap">
        <div class="progress-bar-track">
          <div
            class="progress-bar-fill"
            :class="{ indeterminate: isLive }"
            :style="{ width: isLive ? '' : percent + '%' }"
          ></div>
        </div>
        <div class="progress-meta">
          <span v-if="isLive">Live — In progress...</span>
          <template v-else>
            <span>{{ percent.toFixed(1) }}%</span>
            <span v-if="speed">{{ speed }}</span>
            <span v-if="eta">ETA {{ eta }}</span>
          </template>
        </div>
      </div>
      <div v-if="progressMsg" :class="['msg', progressMsg.type === 'error' ? 'msg-error' : progressMsg.type === 'success' ? 'msg-success' : 'msg-info']">
        {{ progressMsg.text }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import axios from 'axios'

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
  if (!url.value) return

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
