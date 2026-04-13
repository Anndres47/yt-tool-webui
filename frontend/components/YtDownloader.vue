<template>
  <div>
    <div class="section-header">
      <h1 class="section-title">Download</h1>
      <span class="section-sub">yt-dlp · ytarchive</span>
    </div>

    <!-- URL + Mode -->
    <div class="panel" :style="{ opacity: activeTasks.length >= 5 ? 0.5 : 1 }">
      <div class="panel-label">Source</div>

      <div class="field">
        <label class="field-label">Mode</label>
        <div class="mode-pills">
          <button
            v-for="m in modes"
            :key="m.value"
            :class="['mode-pill', { active: mode === m.value }]"
            :disabled="submitting || activeTasks.length >= 5"
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
            :disabled="submitting || activeTasks.length >= 5"
            @click="quality = q.value"
          >{{ q.label }}</button>
        </div>
      </div>

      <div class="field" v-if="mode === 'audio'">
        <label
          :class="['toggle-row', { checked: reencodeAudio }]"
          @click="!(submitting || activeTasks.length >= 5) && (reencodeAudio = !reencodeAudio)"
        >
          <div class="toggle-box">
            <svg class="toggle-check" viewBox="0 0 8 8" fill="none">
              <path d="M1 4l2 2 4-4" stroke="#0a0a0b" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          Re-encode to MP3 320kbps via ffmpeg
        </label>
      </div>

      <div class="field">
        <label class="field-label">YouTube URL</label>
        <input
          type="url"
          v-model="url"
          placeholder="https://www.youtube.com/watch?v=..."
          :disabled="submitting || activeTasks.length >= 5"
          @keyup.enter="startDownload"
        />
      </div>
    </div>

    <!-- Actions & Limit Disclaimer -->
    <div class="panel">
      <div v-if="activeTasks.length >= 5" class="msg msg-info" style="margin-bottom:16px">
        <div style="margin-bottom:4px"><strong>Maximum Limit Reached</strong></div>
        <div>Maximum concurrent downloads (5) reached. Please wait or cancel an active download to start a new one.</div>
      </div>

      <div class="btn-row">
        <button 
          class="btn btn-primary" 
          @click="startDownload" 
          :disabled="submitting || !url.trim() || activeTasks.length >= 5"
        >
          <svg v-if="!submitting" width="13" height="13" viewBox="0 0 13 13" fill="none">
            <path d="M6.5 1v7.5M3 6l3.5 3.5L10 6M1 11.5h11" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span v-if="submitting" class="spinner"></span>
          {{ submitting ? 'Starting…' : 'Download' }}
        </button>
      </div>
    </div>

    <!-- Active Task List -->
    <div v-if="activeTasks.length > 0" style="margin-top:24px">
      <div class="panel-label">Active Downloads</div>
      
      <div v-for="task in activeTasks" :key="task.id" class="panel task-card" :class="{ 'task-done': task.done }">
        <div class="task-header">
          <div class="task-info">
            <span class="task-mode-badge">{{ task.mode }}</span>
            <div v-if="task.title" class="task-title">{{ task.title }}</div>
            <span class="task-url">{{ task.url }}</span>
          </div>
          <button 
            v-if="!task.done && !task.showCancelConfirm" 
            class="btn btn-danger btn-sm" 
            @click="promptCancel(task)"
          >
            <svg width="10" height="10" viewBox="0 0 12 12" fill="none">
              <rect x="2" y="2" width="8" height="8" rx="1" stroke="currentColor" stroke-width="1.5"/>
            </svg>
            {{ task.mode === 'livestream' ? 'Abort' : 'Cancel' }}
          </button>
        </div>

        <!-- Inline Cancel Confirmation -->
        <div v-if="task.showCancelConfirm" class="msg msg-info task-cancel-dialog">
          <template v-if="task.mode === 'livestream'">
            <div class="cancel-row">
              <span class="cancel-text">Keep &amp; Mux or Delete All?</span>
              <div class="btn-row-right">
                <button class="btn btn-primary btn-xs" @click="cancelTask(task, false)">Keep &amp; Mux</button>
                <button class="btn btn-danger btn-xs" @click="cancelTask(task, true)">Delete All</button>
                <button class="btn btn-ghost btn-xs" @click="clearCancelTimer(task); task.showCancelConfirm = false">Back</button>
              </div>
            </div>
          </template>
          <template v-else>
            <div class="cancel-row">
              <span class="cancel-text">Are you sure you want to cancel?</span>
              <div class="btn-row-right">
                <button class="btn btn-danger btn-xs" @click="cancelTask(task, true)">Yes, Cancel</button>
                <button class="btn btn-ghost btn-xs" @click="clearCancelTimer(task); task.showCancelConfirm = false">No</button>
              </div>
            </div>
          </template>
        </div>

        <!-- Task Progress -->
        <div class="task-progress-area">
          <div class="progress-header">
            <div>
              <div v-if="task.mode === 'livestream' || task.isLive" class="live-badge">
                <div class="live-dot"></div>
                <span v-if="task.isLive">Live — {{ task.segments }} segments</span>
                <span v-else>Catching up — {{ task.segments }} segments</span>
              </div>
              <div v-else class="progress-pct">{{ task.percent.toFixed(1) }}<span style="font-size:11px;opacity:0.6">%</span></div>
            </div>
            <div class="progress-meta">
              <span v-if="task.speed && !task.isLive">{{ task.speed }}</span>
              <span v-if="task.eta && !task.isLive">{{ task.eta }}</span>
            </div>
          </div>
          <div class="progress-track">
            <div
              class="progress-fill"
              :class="{ indeterminate: task.mode === 'livestream' && !task.done }"
              :style="{ width: (task.mode === 'livestream' && !task.done) ? '' : task.percent + '%' }"
            ></div>
          </div>
        </div>

        <!-- Task Specific Messages -->
        <div v-if="task.msg" :class="['msg', `msg-${task.msg.type}`]" style="margin-top:10px;padding:6px 10px;font-size:11px">
          {{ task.msg.text }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
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

const submitting = ref(false)
const activeTasks = ref([])

onMounted(async () => {
  try {
    // Load existing running jobs
    const jobsRes = await axios.get('/api/jobs')
    const jobs = jobsRes.data
    for (const [id, job] of Object.entries(jobs)) {
      if (job.type === 'download' && job.status === 'running') {
        addTaskFromJob(id, job)
      }
    }
  } catch (_) {}
})

function addTaskFromJob(id, job) {
  const task = {
    id,
    url: job.url || 'Unknown source',
    title: job.title || '',
    mode: job.mode || 'video',
    percent: job.percent || 0,
    speed: '',
    eta: '',
    isLive: !!job.is_live,
    segments: job.segments || 0,
    msg: null,
    showCancelConfirm: false,
    cancelTimer: null, // Timer for auto-dismiss
    eventSource: null,
    done: false
  }
  activeTasks.value.push(task)
  listenToJob(task)
}

function promptCancel(task) {
  task.showCancelConfirm = true
  startCancelTimer(task)
}

function startCancelTimer(task) {
  clearCancelTimer(task)
  task.cancelTimer = setTimeout(() => {
    task.showCancelConfirm = false
    task.cancelTimer = null
  }, 10000) // 10 seconds
}

function clearCancelTimer(task) {
  if (task.cancelTimer) {
    clearTimeout(task.cancelTimer)
    task.cancelTimer = null
  }
}

const startDownload = async () => {
  if (!url.value.trim() || activeTasks.value.length >= 5) return

  submitting.value = true
  const taskUrl = url.value
  const taskMode = mode.value

  try {
    const form = new FormData()
    form.append('url', taskUrl)
    form.append('mode', taskMode)
    form.append('quality', quality.value)
    form.append('reencode_audio', reencodeAudio.value ? 'true' : 'false')

    const res = await axios.post('/api/download', form)
    const jobId = res.data.job_id
    
    const task = {
      id: jobId,
      url: taskUrl,
      title: '', // Will be updated via the jobs API on next refresh
      mode: taskMode,
      percent: 0,
      speed: '',
      eta: '',
      isLive: false,
      segments: 0,
      msg: null,
      showCancelConfirm: false,
      cancelTimer: null,
      eventSource: null,
      done: false
    }
    
    activeTasks.value.push(task)
    url.value = '' // Clear for next download
    listenToJob(task)
  } catch (err) {
    // Show error in a temporary msg if submission fails
    alert(err.response?.data?.detail ?? err.message)
  } finally {
    submitting.value = false
  }
}

function listenToJob(task) {
  if (task.eventSource) task.eventSource.close()
  
  const es = new EventSource(`/api/download/progress/${task.id}`)
  task.eventSource = es

  es.onmessage = (e) => {
    const data = JSON.parse(e.data)

    if (data.error) {
      task.msg = { type: 'error', text: data.error }
      cleanupTask(task)
      // Only auto-hide if it's a fatal termination error
      if (!data.retry) {
        setTimeout(() => {
          removeTask(task.id)
        }, 5000)
      }
      return
    }
    if (data.done) {
      task.percent = 100
      task.done = true
      task.msg = { type: 'success', text: 'Download complete!' }
      cleanupTask(task)
      // Auto-hide success after 5 seconds
      setTimeout(() => {
        removeTask(task.id)
      }, 5000)
      return
    }
    if (data.mode === 'livestream') {
      task.isLive = !!data.live
      task.segments = data.segments || 0
      return
    }
    if (data.percent !== undefined) {
      task.percent = data.percent
      task.speed = data.speed || ''
      task.eta = data.eta || ''
    }
  }

  es.onerror = () => {
    if (!task.done && !task.msg) {
      task.msg = { type: 'error', text: 'Connection lost. Refresh to reconnect.' }
      cleanupTask(task)
      // WE NO LONGER removeTask here. This prevents the card from disappearing
      // while the background process is actually still running.
    }
  }
}

const cancelTask = async (task, deleteTemp = false) => {
  clearCancelTimer(task)
  task.showCancelConfirm = false
  try { 
    const form = new FormData()
    form.append('delete', deleteTemp.toString())
    await axios.post(`/api/download/cancel/${task.id}`, form)
    if (deleteTemp) {
      removeTask(task.id)
    }
  } catch (_) {}
}

function cleanupTask(task) {
  task.eventSource?.close()
  task.eventSource = null
}

function removeTask(id) {
  const idx = activeTasks.value.findIndex(t => t.id === id)
  if (idx !== -1) {
    activeTasks.value[idx].eventSource?.close()
    activeTasks.value.splice(idx, 1)
  }
}
</script>

<style scoped>
.task-card {
  margin-bottom: 8px;
  padding: 12px 16px;
  border-left: 2px solid var(--border);
  transition: all 0.3s ease;
}
.task-card.task-done {
  border-left-color: var(--green);
  opacity: 0.8;
}
.task-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 10px;
}
.task-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 80%;
}
.task-mode-badge {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
  color: var(--accent);
  font-weight: 700;
}
.task-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--fg);
  line-height: 1.2;
}
.task-url {
  font-size: 12px;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--font-mono);
}
.task-progress-area {
  margin-top: 8px;
}
.progress-pct {
  font-size: 18px;
  font-weight: 700;
  color: var(--accent);
  line-height: 1;
}
.progress-meta {
  font-size: 10px;
  color: var(--muted);
}
.task-cancel-dialog {
  margin: 10px 0;
  padding: 6px 12px;
}
.cancel-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}
.cancel-text {
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}
.btn-row-right {
  display: flex;
  gap: 6px;
}
.btn-xs {
  padding: 4px 8px;
  font-size: 10px;
}
.btn-sm {
  padding: 6px 10px;
  font-size: 11px;
}
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
