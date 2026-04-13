<template>
  <div>
    <!-- Source selector -->
    <div class="card">
      <h2>Source</h2>
      <div class="inner-tabs">
        <button :class="['inner-tab', { active: sourceTab === 'library' }]" @click="switchSource('library')">Library</button>
        <button :class="['inner-tab', { active: sourceTab === 'upload' }]" @click="switchSource('upload')">Upload (max 1 GB)</button>
      </div>

      <!-- Library -->
      <template v-if="sourceTab === 'library'">
        <div class="field">
          <label>File from downloads folder</label>
          <select v-model="libraryFile" @change="onLibrarySelect">
            <option value="">— select a file —</option>
            <option v-for="f in libraryFiles" :key="f.name" :value="f.name">
              {{ f.name }} ({{ formatSize(f.size) }})
            </option>
          </select>
        </div>
        <button class="btn btn-secondary" style="margin-bottom:0.75rem" @click="loadLibrary">Refresh</button>
      </template>

      <!-- Upload -->
      <template v-else>
        <div class="field">
          <label>Upload a video or audio file</label>
          <input type="file" accept="video/*,audio/*" @change="onFileUpload" />
        </div>
      </template>

      <!-- Preview -->
      <template v-if="previewSrc">
        <video
          v-if="isVideoFile"
          ref="mediaEl"
          class="video-preview"
          controls
          :src="previewSrc"
          @loadedmetadata="onMetadata"
        ></video>
        <audio
          v-else
          ref="mediaEl"
          controls
          style="width:100%;margin-bottom:0.75rem"
          :src="previewSrc"
          @loadedmetadata="onMetadata"
        ></audio>

        <!-- Start / End controls -->
        <div class="time-row">
          <div class="field">
            <label>Start — {{ fmtTime(startTime) }}</label>
            <input type="range" v-model.number="startTime" min="0" :max="duration" step="0.1"
              @input="mediaEl && (mediaEl.currentTime = startTime)" />
            <button class="btn btn-secondary" style="margin-top:0.3rem;font-size:0.78rem" @click="setFromCurrent('start')">
              Set from current position
            </button>
          </div>
          <div class="field">
            <label>End — {{ fmtTime(endTime) }}</label>
            <input type="range" v-model.number="endTime" min="0" :max="duration" step="0.1"
              @input="mediaEl && (mediaEl.currentTime = endTime)" />
            <button class="btn btn-secondary" style="margin-top:0.3rem;font-size:0.78rem" @click="setFromCurrent('end')">
              Set from current position
            </button>
          </div>
        </div>
      </template>
    </div>

    <!-- Cut options -->
    <div class="card">
      <h2>Cut Options</h2>

      <div class="field">
        <label>Output filename (without extension)</label>
        <input type="text" v-model="outputName" placeholder="my-clip" />
      </div>

      <label class="check-row">
        <input type="checkbox" v-model="reencodeAudio" />
        Re-encode audio to MP3 320kbps
      </label>

      <div class="btn-row">
        <button class="btn btn-primary" @click="cut" :disabled="cutting || !previewSrc || !outputName">
          {{ cutting ? 'Cutting...' : 'Cut' }}
        </button>
      </div>
    </div>

    <!-- Progress -->
    <div class="card" v-if="cutting || cutMsg">
      <div class="progress-wrap" v-if="cutting">
        <div class="progress-bar-track">
          <div class="progress-bar-fill" :style="{ width: cutPercent + '%' }"></div>
        </div>
        <div class="progress-meta"><span>{{ cutPercent.toFixed(1) }}%</span></div>
      </div>
      <div v-if="cutMsg" :class="['msg', cutMsg.type === 'error' ? 'msg-error' : 'msg-success']">
        {{ cutMsg.text }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

const sourceTab = ref('library')
const libraryFiles = ref([])
const libraryFile = ref('')
const uploadedFile = ref(null)
const previewSrc = ref('')
const previewObjectUrl = ref('')
const mediaEl = ref(null)

const duration = ref(0)
const startTime = ref(0)
const endTime = ref(0)
const outputName = ref('')
const reencodeAudio = ref(false)

const cutting = ref(false)
const cutPercent = ref(0)
const cutMsg = ref(null)

const AUDIO_EXT = new Set(['.mp3', '.m4a', '.aac', '.opus', '.ogg', '.flac', '.wav'])

const isVideoFile = computed(() => {
  const name = libraryFile.value || uploadedFile.value?.name || ''
  const ext = name.slice(name.lastIndexOf('.')).toLowerCase()
  return !AUDIO_EXT.has(ext)
})

onMounted(loadLibrary)

async function loadLibrary() {
  try {
    const res = await axios.get('/api/library')
    libraryFiles.value = res.data
  } catch (_) {}
}

function switchSource(tab) {
  sourceTab.value = tab
  clearPreview()
}

function clearPreview() {
  if (previewObjectUrl.value) {
    URL.revokeObjectURL(previewObjectUrl.value)
    previewObjectUrl.value = ''
  }
  previewSrc.value = ''
  libraryFile.value = ''
  uploadedFile.value = null
  duration.value = 0
  startTime.value = 0
  endTime.value = 0
}

function onLibrarySelect() {
  if (!libraryFile.value) { clearPreview(); return }
  if (previewObjectUrl.value) { URL.revokeObjectURL(previewObjectUrl.value); previewObjectUrl.value = '' }
  previewSrc.value = `/api/library/stream/${encodeURIComponent(libraryFile.value)}`
}

function onFileUpload(event) {
  const file = event.target.files[0]
  if (!file) return
  if (file.size > 1 * 1024 * 1024 * 1024) {
    cutMsg.value = { type: 'error', text: 'File exceeds the 1 GB upload limit. Use the Library instead.' }
    event.target.value = ''
    return
  }
  cutMsg.value = null
  uploadedFile.value = file
  if (previewObjectUrl.value) URL.revokeObjectURL(previewObjectUrl.value)
  previewObjectUrl.value = URL.createObjectURL(file)
  previewSrc.value = previewObjectUrl.value
}

function onMetadata() {
  if (!mediaEl.value) return
  duration.value = mediaEl.value.duration || 0
  endTime.value = duration.value
}

function setFromCurrent(which) {
  if (!mediaEl.value) return
  const t = mediaEl.value.currentTime
  if (which === 'start') startTime.value = Math.min(t, endTime.value)
  else endTime.value = Math.max(t, startTime.value)
}

function fmtTime(s) {
  if (!isFinite(s)) return '0:00'
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60).toString().padStart(2, '0')
  return `${m}:${sec}`
}

function formatSize(bytes) {
  if (bytes > 1e9) return (bytes / 1e9).toFixed(1) + ' GB'
  if (bytes > 1e6) return (bytes / 1e6).toFixed(1) + ' MB'
  return (bytes / 1e3).toFixed(0) + ' KB'
}

async function cut() {
  if (!previewSrc.value || !outputName.value) return
  if (startTime.value >= endTime.value) {
    cutMsg.value = { type: 'error', text: 'Start time must be less than end time.' }
    return
  }

  cutting.value = true
  cutPercent.value = 0
  cutMsg.value = null

  const cutDuration = endTime.value - startTime.value

  try {
    const form = new FormData()
    form.append('start', startTime.value.toString())
    form.append('end', endTime.value.toString())
    form.append('name', outputName.value)
    form.append('reencode_audio', reencodeAudio.value ? 'true' : 'false')
    form.append('duration_s', cutDuration.toString())

    if (sourceTab.value === 'library') {
      form.append('library_path', libraryFile.value)
    } else {
      form.append('video', uploadedFile.value)
    }

    const res = await axios.post('/api/ffmpeg/cut', form)
    const jobId = res.data.job_id

    const es = new EventSource(`/api/ffmpeg/progress/${jobId}`)
    es.onmessage = (e) => {
      const data = JSON.parse(e.data)
      if (data.error) {
        cutMsg.value = { type: 'error', text: data.error }
        cutting.value = false
        es.close()
        return
      }
      if (data.done) {
        cutPercent.value = 100
        cutMsg.value = { type: 'success', text: `Done! Saved to: ${data.output}` }
        cutting.value = false
        es.close()
        loadLibrary()
        return
      }
      if (data.percent !== undefined) cutPercent.value = data.percent
    }
    es.onerror = () => {
      cutMsg.value = { type: 'error', text: 'Connection to server lost.' }
      cutting.value = false
      es.close()
    }
  } catch (err) {
    cutMsg.value = { type: 'error', text: err.response?.data?.detail ?? err.message }
    cutting.value = false
  }
}
</script>
