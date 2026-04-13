<template>
  <div>
    <div class="section-header">
      <h1 class="section-title">Config</h1>
      <span class="section-sub">server-side settings</span>
    </div>

    <div class="panel">
      <div class="panel-label">Paths</div>

      <div class="field">
        <label class="field-label">Download path <span style="color:var(--muted);font-weight:400">(absolute, server-side)</span></label>
        <input type="text" v-model="cfg.download_path" placeholder="/app/downloads" />
      </div>

      <div class="field">
        <label class="field-label">Cookies.txt path <span style="color:var(--muted);font-weight:400">(optional)</span></label>
        <input type="text" v-model="cfg.cookies_path" placeholder="/app/cookies.txt" />
      </div>
    </div>

    <div class="panel">
      <div class="panel-label">Authentication</div>

      <div class="field">
        <label class="field-label">PO Token <span style="color:var(--muted);font-weight:400">(optional — bot-protected streams)</span></label>
        <input type="text" v-model="cfg.potoken" placeholder="Paste PO token here" autocomplete="off" />
      </div>
    </div>

    <div class="panel">
      <div class="btn-row">
        <button class="btn btn-primary" @click="save" :disabled="saving">
          <svg v-if="!saving" width="13" height="13" viewBox="0 0 13 13" fill="none">
            <path d="M2 2h7l2 2v7a1 1 0 0 1-1 1H2a1 1 0 0 1-1-1V3a1 1 0 0 1 1-1z" stroke="currentColor" stroke-width="1.3"/>
            <path d="M4 12V8h5v4M4 2v3h4V2" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          <span v-if="saving" class="spinner"></span>
          {{ saving ? 'Saving…' : 'Save Config' }}
        </button>
      </div>

      <div v-if="msg" :class="['msg', `msg-${msg.type}`]" style="margin-top:12px">
        {{ msg.text }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'

const cfg = ref({ download_path: '', cookies_path: '', potoken: '' })
const saving = ref(false)
const msg = ref(null)

onMounted(async () => {
  try {
    const res = await axios.get('/api/settings')
    cfg.value = res.data
  } catch (err) {
    msg.value = { type: 'error', text: 'Failed to load config.' }
  }
})

async function save() {
  saving.value = true
  msg.value = null
  try {
    await axios.post('/api/settings', cfg.value)
    msg.value = { type: 'success', text: 'Config saved.' }
  } catch (err) {
    msg.value = { type: 'error', text: err.response?.data?.detail ?? err.message }
  } finally {
    saving.value = false
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
