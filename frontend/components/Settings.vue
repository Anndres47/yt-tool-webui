<template>
  <div>
    <div class="card">
      <h2>Settings</h2>

      <div class="field">
        <label>Download Path (server-side absolute path)</label>
        <input type="text" v-model="cfg.download_path" placeholder="/app/downloads" />
      </div>

      <div class="field">
        <label>Cookies.txt Path (optional)</label>
        <input type="text" v-model="cfg.cookies_path" placeholder="/app/cookies.txt" />
      </div>

      <div class="field">
        <label>PO Token (optional, for bot-protected streams)</label>
        <input type="text" v-model="cfg.potoken" placeholder="Paste PO token here" />
      </div>

      <div class="btn-row">
        <button class="btn btn-primary" @click="save" :disabled="saving">
          {{ saving ? 'Saving...' : 'Save Settings' }}
        </button>
      </div>

      <div v-if="msg" :class="['msg', msg.type === 'error' ? 'msg-error' : 'msg-success']" style="margin-top:0.75rem">
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
    msg.value = { type: 'error', text: 'Failed to load settings.' }
  }
})

async function save() {
  saving.value = true
  msg.value = null
  try {
    await axios.post('/api/settings', cfg.value)
    msg.value = { type: 'success', text: 'Settings saved.' }
  } catch (err) {
    msg.value = { type: 'error', text: err.response?.data?.detail ?? err.message }
  } finally {
    saving.value = false
  }
}
</script>
