<template>
  <div class="app">
    <header class="app-header">
      <h1>YT WebUI</h1>
      <nav class="tabs">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          :class="['tab-btn', { active: activeTab === tab.id }]"
          @click="activeTab = tab.id"
        >{{ tab.label }}</button>
      </nav>
    </header>

    <main class="app-body">
      <YtDownloader v-if="activeTab === 'download'" />
      <FfmpegCutter v-else-if="activeTab === 'ffmpeg'" />
      <Settings v-else-if="activeTab === 'settings'" />
    </main>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import YtDownloader from './components/YtDownloader.vue'
import FfmpegCutter from './components/FfmpegCutter.vue'
import Settings from './components/Settings.vue'

const activeTab = ref('download')
const tabs = [
  { id: 'download', label: 'Download' },
  { id: 'ffmpeg', label: 'FFmpeg Cutter' },
  { id: 'settings', label: 'Settings' },
]
</script>

<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Inter', system-ui, sans-serif;
  background: #0f0f13;
  color: #e2e2e8;
  min-height: 100vh;
}

.app {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.app-header {
  display: flex;
  align-items: center;
  gap: 2rem;
  padding: 1rem 2rem;
  background: #18181f;
  border-bottom: 1px solid #2a2a38;
}

.app-header h1 {
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  color: #fff;
  white-space: nowrap;
}

.tabs {
  display: flex;
  gap: 0.25rem;
}

.tab-btn {
  padding: 0.4rem 1rem;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: #888;
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.15s;
}

.tab-btn:hover { color: #e2e2e8; background: #2a2a38; }
.tab-btn.active { background: #2563eb; color: #fff; border-color: #2563eb; }

.app-body {
  flex: 1;
  padding: 2rem;
  max-width: 860px;
  width: 100%;
  margin: 0 auto;
}

/* Shared form styles */
.card {
  background: #18181f;
  border: 1px solid #2a2a38;
  border-radius: 12px;
  padding: 1.5rem;
  margin-bottom: 1rem;
}

.card h2 {
  font-size: 0.95rem;
  font-weight: 600;
  color: #a0a0b0;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 1rem;
}

.field { display: flex; flex-direction: column; gap: 0.35rem; margin-bottom: 0.85rem; }
.field label { font-size: 0.8rem; color: #888; }

input[type="text"],
input[type="url"],
select,
textarea {
  background: #0f0f13;
  border: 1px solid #2a2a38;
  border-radius: 6px;
  color: #e2e2e8;
  font-size: 0.9rem;
  padding: 0.5rem 0.75rem;
  outline: none;
  width: 100%;
  transition: border-color 0.15s;
}

input[type="text"]:focus,
input[type="url"]:focus,
select:focus { border-color: #2563eb; }

select option { background: #18181f; }

.btn {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.5rem 1.2rem;
  border: none;
  border-radius: 6px;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-primary { background: #2563eb; color: #fff; }
.btn-primary:hover:not(:disabled) { background: #1d4ed8; }
.btn-danger { background: #dc2626; color: #fff; }
.btn-danger:hover:not(:disabled) { background: #b91c1c; }
.btn-secondary { background: #2a2a38; color: #e2e2e8; }
.btn-secondary:hover:not(:disabled) { background: #38384a; }

.btn-row { display: flex; gap: 0.5rem; flex-wrap: wrap; }

/* Progress */
.progress-wrap { margin-top: 1rem; }

.progress-bar-track {
  height: 6px;
  background: #2a2a38;
  border-radius: 99px;
  overflow: hidden;
  margin-bottom: 0.4rem;
}

.progress-bar-fill {
  height: 100%;
  background: #2563eb;
  border-radius: 99px;
  transition: width 0.3s ease;
}

.progress-bar-fill.indeterminate {
  width: 40% !important;
  animation: slide 1.4s ease-in-out infinite;
}

@keyframes slide {
  0% { transform: translateX(-200%); }
  100% { transform: translateX(350%); }
}

.progress-meta {
  font-size: 0.75rem;
  color: #888;
  display: flex;
  gap: 1rem;
}

.msg { font-size: 0.85rem; margin-top: 0.75rem; padding: 0.5rem 0.75rem; border-radius: 6px; }
.msg-error { background: #2d1111; color: #f87171; border: 1px solid #7f1d1d; }
.msg-success { background: #0d2011; color: #4ade80; border: 1px solid #14532d; }
.msg-info { background: #0f172a; color: #93c5fd; border: 1px solid #1e3a5f; }

/* Checkbox */
.check-row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: #ccc;
  cursor: pointer;
  margin-bottom: 0.85rem;
}
.check-row input[type="checkbox"] { width: 15px; height: 15px; cursor: pointer; accent-color: #2563eb; }

/* Tabs inside a card */
.inner-tabs { display: flex; gap: 0.25rem; margin-bottom: 1rem; }
.inner-tab {
  padding: 0.3rem 0.85rem;
  border: 1px solid #2a2a38;
  border-radius: 6px;
  background: transparent;
  color: #888;
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s;
}
.inner-tab:hover { color: #e2e2e8; }
.inner-tab.active { background: #2a2a38; color: #fff; border-color: #38384a; }

/* Video preview */
.video-preview {
  width: 100%;
  max-height: 320px;
  border-radius: 8px;
  background: #000;
  margin-bottom: 0.75rem;
  display: block;
}

.time-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
  margin-bottom: 0.85rem;
}
</style>
