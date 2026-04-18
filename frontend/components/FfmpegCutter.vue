<template>
  <div>
    <div class="section-header">
      <h1 class="section-title">Cutter</h1>
      <span class="section-sub">ffmpeg · stream copy</span>
    </div>

    <!-- Source panel -->
    <div class="panel">
      <div class="panel-label">Source</div>

      <div class="source-tabs">
        <button :class="['source-tab', { active: sourceTab === 'library' }]" @click="switchSource('library')" :disabled="cutting">Library</button>
        <button :class="['source-tab', { active: sourceTab === 'upload' }]" @click="switchSource('upload')" :disabled="cutting">Upload · max 1 GB</button>
      </div>

      <!-- Library picker -->
      <template v-if="sourceTab === 'library'">
        <div class="field">
          <label class="field-label">File from library</label>
          <select v-model="libraryFile" @change="onLibrarySelect" :disabled="cutting">
            <option value="">— select a file —</option>
            <option v-for="f in libraryFiles" :key="f.path" :value="f.path">
              [{{ f.folder }}] {{ f.name }}  ({{ formatSize(f.size) }})
            </option>
          </select>
        </div>
        <button class="btn btn-ghost" style="font-size:11px;padding:6px 12px" @click="loadLibrary" :disabled="cutting">
          <svg width="11" height="11" viewBox="0 0 11 11" fill="none"><path d="M10 5.5A4.5 4.5 0 1 1 5.5 1" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/><path d="M10 1v4H6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          Refresh
        </button>
        <div v-if="libraryFiles.length === 0" class="library-empty" style="margin-top:10px">
          No files in library yet
        </div>
      </template>

      <!-- Upload -->
      <template v-else>
        <div class="file-drop" :style="{ opacity: cutting ? 0.5 : 1, pointerEvents: cutting ? 'none' : 'auto' }">
          <input type="file" accept="video/*,audio/*" @change="onFileUpload" :disabled="cutting" />
          <div class="file-drop-text">
            <strong>Click to select a file</strong>
            video or audio · max 1 GB
          </div>
        </div>
      </template>

      <!-- Media preview -->
      <template v-if="previewSrc">
        <div class="preview-wrap" style="margin-top:14px">
          <video
            v-if="isVideoFile"
            ref="mediaEl"
            controls
            :src="previewSrc"
            @loadedmetadata="onMetadata"
          ></video>
          <audio
            v-else
            ref="mediaEl"
            controls
            style="width:100%;padding:12px"
            :src="previewSrc"
            @loadedmetadata="onMetadata"
          ></audio>
        </div>

        <!-- Scrubbers -->
        <div class="scrubbers" :style="{ opacity: cutting ? 0.5 : 1, pointerEvents: cutting ? 'none' : 'auto' }">
          <div>
            <div class="scrubber-label">
              <span>Start</span>
              <span class="scrubber-time">{{ fmtTime(finalStartTime) }}</span>
            </div>
            <input
              type="range"
              v-model.number="startTime"
              min="0"
              :max="duration"
              step="0.1"
              @input="seekMedia(finalStartTime)"
              :disabled="cutting"
            />
            <div v-if="settings.high_precision_cutter" class="fine-tune-cs">
              <input type="range" v-model.number="startTimeCs" min="0" max="99" step="1" @input="seekMedia(finalStartTime)" :disabled="cutting" />
              <span class="cs-label">.{{ startTimeCs.toString().padStart(2, '0') }}</span>
            </div>
            <button class="btn btn-ghost" style="font-size:11px;padding:5px 10px;margin-top:4px" @click="setFromCurrent('start')" :disabled="cutting">
              Set from playhead
            </button>
          </div>
          <div>
            <div class="scrubber-label">
              <span>End</span>
              <span class="scrubber-time">{{ fmtTime(finalEndTime) }}</span>
            </div>
            <input
              type="range"
              v-model.number="endTime"
              min="0"
              :max="duration"
              step="0.1"
              @input="seekMedia(finalEndTime)"
              :disabled="cutting"
            />
            <div v-if="settings.high_precision_cutter" class="fine-tune-cs">
              <input type="range" v-model.number="endTimeCs" min="0" max="99" step="1" @input="seekMedia(finalEndTime)" :disabled="cutting" />
              <span class="cs-label">.{{ endTimeCs.toString().padStart(2, '0') }}</span>
            </div>
            <button class="btn btn-ghost" style="font-size:11px;padding:5px 10px;margin-top:4px" @click="setFromCurrent('end')" :disabled="cutting">
              Set from playhead
            </button>
          </div>
        </div>

        <!-- Duration callout -->
        <div v-if="clipDuration > 0" style="font-size:11px;color:var(--muted);margin-bottom:4px">
          Clip duration: <span style="color:var(--accent)">{{ fmtTime(clipDuration) }}</span>
        </div>
      </template>
    </div>

    <!-- Cut options panel -->
    <div class="panel">
      <div class="panel-label">Output</div>

      <div class="field">
        <label class="field-label">Output filename <span style="color:var(--muted);font-weight:400">(without extension)</span></label>
        <input type="text" v-model="outputName" placeholder="my-clip" :disabled="cutting" />
      </div>

      <div class="field">
        <label
          :class="['toggle-row', { checked: reencodeFull }]"
          @click="reencodeFull = !reencodeFull"
        >
          <div class="toggle-box">
            <svg class="toggle-check" viewBox="0 0 8 8" fill="none">
              <path d="M1 4l2 2 4-4" stroke="#0a0a0b" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          Full Re-encode (Slow, for better compatibility)
        </label>
      </div>

      <div class="btn-row">
        <button
          class="btn btn-primary"
          @click="cut"
          :disabled="cutting || !previewSrc || !outputName.trim()"
        >
          <svg v-if="!cutting" width="13" height="13" viewBox="0 0 13 13" fill="none">
            <circle cx="3" cy="3" r="1.5" stroke="currentColor" stroke-width="1.3"/>
            <circle cx="3" cy="10" r="1.5" stroke="currentColor" stroke-width="1.3"/>
            <path d="M4.5 3.5L12 9M4.5 9.5l2-1.4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/>
          </svg>
          <span v-if="cutting" class="spinner"></span>
          {{ cutting ? 'Cutting…' : 'Cut' }}
        </button>

        <button
          v-if="cutting"
          class="btn btn-danger"
          @click="cancelCut"
        >
          <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
            <rect x="2" y="2" width="8" height="8" rx="1" stroke="currentColor" stroke-width="1.5"/>
          </svg>
          Cancel Cut
        </button>
      </div>

      <!-- Progress -->
      <div class="progress-block" v-if="cutting || cutMsg">
        <template v-if="cutting">
          <div class="progress-header">
            <div class="progress-pct">{{ cutPercent.toFixed(1) }}<span style="font-size:14px;font-weight:400;color:var(--muted)">%</span></div>
          </div>
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: cutPercent + '%' }"></div>
          </div>
        </template>

        <div v-if="cutMsg" :class="['msg', `msg-${cutMsg.type}`]">
          {{ cutMsg.text }}
        </div>
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

const settings = ref({ high_precision_cutter: false })
const duration = ref(0)
const startTime = ref(0)
const endTime = ref(0)
const startTimeCs = ref(0)
const endTimeCs = ref(0)
const outputName = ref('')
const reencodeFull = ref(false)

const cutting = ref(false)
const cutPercent = ref(0)
const cutMsg = ref(null)
let activeJobId = null
let eventSource = null

const AUDIO_EXT = new Set(['.mp3', '.m4a', '.aac', '.opus', '.ogg', '.flac', '.wav'])

const isVideoFile = computed(() => {
  const name = libraryFile.value || uploadedFile.value?.name || ''
  const ext = name.slice(name.lastIndexOf('.')).toLowerCase()
  return !AUDIO_EXT.has(ext)
})

const finalStartTime = computed(() => startTime.value + (startTimeCs.value / 100))
const finalEndTime = computed(() => endTime.value + (endTimeCs.value / 100))
const clipDuration = computed(() => {
  const d = finalEndTime.value - finalStartTime.value
  return d > 0 ? d : 0
})

onMounted(async () => {
  loadLibrary()
  try {
    const [jobsRes, settingsRes] = await Promise.all([
      axios.get('/api/jobs'),
      axios.get('/api/settings')
    ])
    settings.value = settingsRes.data
    const jobs = jobsRes.data
    for (const [id, job] of Object.entries(jobs)) {
      if (job.type === 'ffmpeg' && job.status === 'running') {
        activeJobId = id
        cutting.value = true
        cutPercent.value = job.percent || 0
        listenToCut(id)
        break
      }
    }
  } catch (_) {}
})

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
  startTimeCs.value = 0
  endTimeCs.value = 0
}

function onLibrarySelect() {
  if (!libraryFile.value) { clearPreview(); return }
  if (previewObjectUrl.value) { URL.revokeObjectURL(previewObjectUrl.value); previewObjectUrl.value = '' }
  previewSrc.value = `/api/library/stream/${libraryFile.value}`
  const fname = libraryFile.value.split('/').pop()
  outputName.value = fname.slice(0, fname.lastIndexOf('.')) + '_clip'
}

function onFileUpload(event) {
  const file = event.target.files[0]
  if (!file) return
  if (file.size > 1 * 1024 * 1024 * 1024) {
    cutMsg.value = { type: 'error', text: 'File exceeds the 1 GB upload limit. Select it from the Library instead.' }
    event.target.value = ''
    return
  }
  cutMsg.value = null
  uploadedFile.value = file
  if (previewObjectUrl.value) URL.revokeObjectURL(previewObjectUrl.value)
  previewObjectUrl.value = URL.createObjectURL(file)
  previewSrc.value = previewObjectUrl.value
  outputName.value = file.name.slice(0, file.name.lastIndexOf('.')) + '_clip'
}

function onMetadata() {
  if (!mediaEl.value) return
  duration.value = mediaEl.value.duration || 0
  endTime.value = duration.value
}

function seekMedia(t) {
  if (mediaEl.value) mediaEl.value.currentTime = t
}

function setFromCurrent(which) {
  if (!mediaEl.value) return
  const t = mediaEl.value.currentTime
  if (which === 'start') {
    startTime.value = Math.floor(t)
    startTimeCs.value = Math.round((t - Math.floor(t)) * 100)
    // If start moves past end, push end forward by 10s to keep selection valid
    if (finalStartTime.value >= finalEndTime.value) {
      const newEnd = Math.min(finalStartTime.value + 10, duration.value)
      endTime.value = Math.floor(newEnd)
      endTimeCs.value = Math.round((newEnd - Math.floor(newEnd)) * 100)
    }
  } else {
    // Allow setting End (B) freely anywhere. 
    // Validation in cut() will handle A > B cases.
    endTime.value = Math.floor(t)
    endTimeCs.value = Math.round((t - Math.floor(t)) * 100)
  }
}

function toTimestamp(s) {
  const h = Math.floor(s / 3600).toString().padStart(2, '0')
  const m = Math.floor((s % 3600) / 60).toString().padStart(2, '0')
  const sec = Math.floor(s % 60).toString().padStart(2, '0')
  const cs = Math.round((s - Math.floor(s)) * 100).toString().padStart(2, '0')
  return `${h}:${m}:${sec}.${cs}`
}

function fmtTime(s) {
  if (!isFinite(s) || s < 0) return settings.value.high_precision_cutter ? '0:00.00' : '0:00'
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60).toString().padStart(2, '0')
  const base = h > 0 ? `${h}:${m.toString().padStart(2,'0')}:${sec}` : `${m}:${sec}`
  
  if (settings.value.high_precision_cutter) {
    const cs = Math.round((s - Math.floor(s)) * 100).toString().padStart(2, '0')
    return `${base}.${cs}`
  }
  return base
}

function formatSize(bytes) {
  if (bytes > 1e9) return (bytes / 1e9).toFixed(1) + ' GB'
  if (bytes > 1e6) return (bytes / 1e6).toFixed(1) + ' MB'
  return (bytes / 1e3).toFixed(0) + ' KB'
}

async function cancelCut() {
  if (!activeJobId) return
  try {
    eventSource?.close()
    eventSource = null
    await axios.post(`/api/ffmpeg/cancel/${activeJobId}`)
    cutMsg.value = { type: 'info', text: 'Cut cancelled by user.' }
    cutting.value = false
  } catch (_) {}
}

async function cut() {
  if (!previewSrc.value || !outputName.value.trim()) return
  if (finalStartTime.value >= finalEndTime.value) {
    cutMsg.value = { type: 'error', text: 'Start time must be less than end time.' }
    return
  }

  cutting.value = true
  cutPercent.value = 0
  cutMsg.value = null

  try {
    const form = new FormData()
    let startVal = finalStartTime.value
    let endVal = finalEndTime.value

    if (settings.value.high_precision_cutter) {
      startVal = toTimestamp(startVal)
      endVal = toTimestamp(endVal)
    }

    form.append('start', startVal.toString())
    form.append('end', endVal.toString())
    form.append('name', outputName.value)
    form.append('reencode_full', reencodeFull.value ? 'true' : 'false')
    form.append('duration_s', clipDuration.value.toString())

    if (sourceTab.value === 'library') {
      form.append('library_path', libraryFile.value)
    } else {
      form.append('video', uploadedFile.value)
    }

    const res = await axios.post('/api/ffmpeg/cut', form)
    const jobId = res.data.job_id
    activeJobId = jobId
    listenToCut(jobId)
  } catch (err) {
    cutMsg.value = { type: 'error', text: err.response?.data?.detail ?? err.message }
    cutting.value = false
  }
}

function listenToCut(jobId) {
  eventSource = new EventSource(`/api/ffmpeg/progress/${jobId}`)
  eventSource.onmessage = (e) => {
    const data = JSON.parse(e.data)
    if (data.error) {
      cutMsg.value = { type: 'error', text: data.error }
      cutting.value = false
      eventSource?.close()
      eventSource = null
      return
    }
    if (data.done) {
      cutPercent.value = 100
      cutMsg.value = { type: 'success', text: `Saved to: ${data.output}` }
      cutting.value = false
      eventSource?.close()
      eventSource = null
      loadLibrary()
      return
    }
    if (data.percent !== undefined) cutPercent.value = data.percent
  }
  eventSource.onerror = () => {
    if (cutting.value) {
      cutMsg.value = { type: 'error', text: 'Connection to server lost.' }
      cutting.value = false
      eventSource?.close()
      eventSource = null
    }
  }
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
