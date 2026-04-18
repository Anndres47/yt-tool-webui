<template>
  <div class="app">
    <!-- Grid background -->
    <div class="bg-grid" aria-hidden="true"></div>

    <!-- Sidebar nav -->
    <aside class="sidebar">
      <div class="sidebar-logo">
        <span class="logo-mark">▶</span>
        <div class="logo-text">
          <div>YT</div>
          <div>TOOL</div>
          <div class="logo-subtext">WEB-UI</div>
        </div>
      </div>

      <nav class="sidebar-nav">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          :class="['nav-item', { active: activeTab === tab.id }]"
          @click="activeTab = tab.id"
        >
          <span class="nav-icon" v-html="tab.icon"></span>
          <span class="nav-label">{{ tab.label }}</span>
          <span class="nav-indicator" v-if="activeTab === tab.id"></span>
        </button>
      </nav>

      <div class="sidebar-footer">
        <span class="version-tag">v1.7.0-beta</span>
      </div>
    </aside>

    <!-- Main content -->
    <main class="main-content">
      <div class="content-inner">
        <Transition name="panel" mode="out-in">
          <KeepAlive>
            <YtDownloader v-if="activeTab === 'download'" />
            <FfmpegCutter v-else-if="activeTab === 'ffmpeg'" />
            <Settings v-else-if="activeTab === 'settings'" />
          </KeepAlive>
        </Transition>
      </div>
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
  {
    id: 'download',
    label: 'Download',
    icon: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 1v9M4 7l4 4 4-4M2 13h12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`
  },
  {
    id: 'ffmpeg',
    label: 'Cutter',
    icon: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><circle cx="4" cy="4" r="2" stroke="currentColor" stroke-width="1.5"/><circle cx="4" cy="12" r="2" stroke="currentColor" stroke-width="1.5"/><path d="M6 4.5l8 6M6 11.5l8-6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`
  },
  {
    id: 'settings',
    label: 'Settings',
    icon: `<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M8 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5z" stroke="currentColor" stroke-width="1.5"/><path d="M7 1.5h2l.5 2.2.8.3 2-1.3 1.4 1.4-1.3 2 .3.8 2.2.5v2l-2.2.5-.3.8 1.3 2-1.4 1.4-2-1.3-.8.3-.5 2.2H7l-.5-2.2-.8-.3-2 1.3-1.4-1.4 1.3-2-.3-.8-2.2-.5v-2l2.2-.5.3-.8-1.3-2 1.4-1.4 2 1.3.8-.3.5-2.2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>`
  },
]
</script>

<style>
/* ── Reset ─────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

/* ── Tokens ────────────────────────────────────────── */
:root {
  --bg:        #0a0a0b;
  --surface:   #111113;
  --surface2:  #18181c;
  --border:    rgba(255,255,255,0.07);
  --border2:   rgba(255,255,255,0.12);
  --text:      #e8e8ea;
  --muted:     #5a5a6a;
  --muted2:    #3a3a48;
  --accent:    #f0a500;
  --accent-dim: rgba(240,165,0,0.12);
  --accent-glow: rgba(240,165,0,0.25);
  --red:       #e05252;
  --red-dim:   rgba(224,82,82,0.12);
  --green:     #4ecb71;
  --green-dim: rgba(78,203,113,0.10);
  --blue:      #5b9cf6;
  --blue-dim:  rgba(91,156,246,0.10);
  --font-ui:   'Syne', sans-serif;
  --font-mono: 'DM Mono', monospace;
  --sidebar-w: 200px;
  --radius:    4px;
}

/* ── Base ──────────────────────────────────────────── */
html, body { height: 100%; }

body {
  font-family: var(--font-mono);
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  overflow: hidden;
}

/* ── Grid background ───────────────────────────────── */
.bg-grid {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  background-image:
    linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.025) 1px, transparent 1px);
  background-size: 40px 40px;
}

/* ── App shell ─────────────────────────────────────── */
.app {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: var(--sidebar-w) 1fr;
  height: 100vh;
}

/* ── Sidebar ───────────────────────────────────────── */
.sidebar {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border);
  background: var(--surface);
  padding: 0;
  height: 100vh;
  overflow: hidden;
}

.sidebar-logo {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 24px 20px;
  border-bottom: 1px solid var(--border);
}

.logo-mark {
  color: var(--accent);
  font-size: 14px;
  line-height: 1;
  margin-top: 2px; /* Slight offset to align with the first line of text */
}

.logo-text {
  font-family: var(--font-ui);
  font-weight: 800;
  font-size: 16px;
  line-height: 1.1;
  letter-spacing: 0.15em;
  color: var(--text);
  display: flex;
  flex-direction: column;
}

.logo-subtext {
  font-size: 10px;
  letter-spacing: 0.25em;
  color: var(--muted);
  margin-top: 2px;
}

.sidebar-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 12px 0;
  gap: 2px;
}

.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 20px;
  border: none;
  background: transparent;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 12px;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition: color 0.15s, background 0.15s;
  text-align: left;
  width: 100%;
}

.nav-item:hover { color: var(--text); background: rgba(255,255,255,0.03); }

.nav-item.active {
  color: var(--accent);
  background: var(--accent-dim);
}

.nav-icon { flex-shrink: 0; opacity: 0.8; }
.nav-item.active .nav-icon { opacity: 1; }

.nav-label { font-weight: 500; }

.nav-indicator {
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 2px;
  height: 20px;
  background: var(--accent);
  border-radius: 2px 0 0 2px;
}

.sidebar-footer {
  padding: 16px 20px;
  border-top: 1px solid var(--border);
}

.version-tag {
  font-size: 10px;
  font-family: var(--font-mono);
  color: var(--muted);
  letter-spacing: 0.1em;
}

/* ── Main content ──────────────────────────────────── */
.main-content {
  height: 100vh;
  overflow-y: auto;
  overflow-x: hidden;
}

.content-inner {
  max-width: 740px;
  margin: 0 auto;
  padding: 36px 32px 60px;
}

/* ── Panel transition ──────────────────────────────── */
.panel-enter-active { transition: opacity 0.18s ease, transform 0.18s ease; }
.panel-leave-active { transition: opacity 0.12s ease, transform 0.12s ease; }
.panel-enter-from  { opacity: 0; transform: translateY(6px); }
.panel-leave-to    { opacity: 0; transform: translateY(-4px); }

/* ── Section header ────────────────────────────────── */
.section-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 28px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border);
}

.section-title {
  font-family: var(--font-ui);
  font-size: 22px;
  font-weight: 700;
  color: var(--text);
  letter-spacing: -0.02em;
}

.section-sub {
  font-size: 11px;
  color: var(--muted);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

/* ── Panel blocks ──────────────────────────────────── */
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  margin-bottom: 12px;
}

.panel-label {
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--muted);
  margin-bottom: 14px;
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-label::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}

/* ── Fields ────────────────────────────────────────── */
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
}

.field:last-child { margin-bottom: 0; }

.field-label {
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 500;
}

/* ── Inputs ────────────────────────────────────────── */
input[type="text"],
input[type="url"],
input[type="password"],
input[type="number"],
select {
  font-family: var(--font-mono);
  font-size: 13px;
  background: var(--bg);
  border: 1px solid var(--border2);
  border-radius: var(--radius);
  color: var(--text);
  padding: 9px 12px;
  width: 100%;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
  -webkit-appearance: none;
  appearance: none;
}

input[type="text"]:focus,
input[type="url"]:focus,
input[type="password"]:focus,
input[type="number"]:focus,
select:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-glow);
}

input::placeholder { color: var(--muted); }

select {
  cursor: pointer;
  background-image: url("data:image/svg+xml,%3Csvg width='10' height='6' viewBox='0 0 10 6' fill='none' xmlns='http://www.w3.org/2000/svg'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%235a5a6a' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 12px center;
  padding-right: 32px;
}

select option { background: var(--surface2); color: var(--text); }

/* ── Mode pills ────────────────────────────────────── */
.mode-pills {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.mode-pill {
  padding: 6px 16px;
  border: 1px solid var(--border2);
  border-radius: 2px;
  background: transparent;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  cursor: pointer;
  transition: all 0.15s;
}

.mode-pill:hover { color: var(--text); border-color: var(--border2); background: rgba(255,255,255,0.04); }
.mode-pill.active { color: var(--accent); border-color: var(--accent); background: var(--accent-dim); }

/* ── Quality pills ─────────────────────────────────── */
.quality-pills {
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}

.q-pill {
  padding: 4px 12px;
  border: 1px solid var(--border2);
  border-radius: 2px;
  background: transparent;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.12s;
}

.q-pill:hover { color: var(--text); background: rgba(255,255,255,0.03); }
.q-pill.active { color: var(--bg); background: var(--accent); border-color: var(--accent); }

/* ── Checkbox toggle ───────────────────────────────── */
.toggle-row {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  font-size: 12px;
  color: var(--muted);
  transition: color 0.12s;
  user-select: none;
}

.toggle-row:hover { color: var(--text); }

.toggle-box {
  width: 14px;
  height: 14px;
  border: 1px solid var(--border2);
  border-radius: 2px;
  background: var(--bg);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.12s;
  flex-shrink: 0;
}

.toggle-row:hover .toggle-box { border-color: var(--accent); }
.toggle-row.checked .toggle-box { background: var(--accent); border-color: var(--accent); }
.toggle-row.checked { color: var(--text); }

.toggle-check {
  width: 8px;
  height: 8px;
  display: none;
}
.toggle-row.checked .toggle-check { display: block; }

/* ── Buttons ───────────────────────────────────────── */
.btn-row { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-top: 4px; }

.btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 9px 18px;
  border: 1px solid transparent;
  border-radius: var(--radius);
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 500;
  letter-spacing: 0.04em;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.btn:disabled { opacity: 0.35; cursor: not-allowed; }

.btn-primary {
  background: var(--accent);
  color: var(--bg);
  border-color: var(--accent);
}
.btn-primary:hover:not(:disabled) {
  background: #fbb824;
  box-shadow: 0 0 16px var(--accent-glow);
}

.btn-danger {
  background: transparent;
  color: var(--red);
  border-color: rgba(224,82,82,0.35);
}
.btn-danger:hover:not(:disabled) { background: var(--red-dim); border-color: var(--red); }

.btn-ghost {
  background: transparent;
  color: var(--muted);
  border-color: var(--border2);
}
.btn-ghost:hover:not(:disabled) { color: var(--text); background: rgba(255,255,255,0.04); }

/* ── Progress ──────────────────────────────────────── */
.progress-block { margin-top: 16px; }

.progress-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 8px;
}

.progress-pct {
  font-family: var(--font-ui);
  font-size: 28px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: -0.03em;
  line-height: 1;
}

.progress-meta {
  font-size: 11px;
  color: var(--muted);
  display: flex;
  gap: 12px;
}

.progress-track {
  height: 3px;
  background: var(--surface2);
  border-radius: 2px;
  overflow: hidden;
  position: relative;
}

.progress-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
  transition: width 0.4s ease;
  position: relative;
}

.progress-fill::after {
  content: '';
  position: absolute;
  right: 0;
  top: 0;
  width: 40px;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.4));
}

.progress-fill.indeterminate {
  width: 35% !important;
  animation: sweep 1.6s cubic-bezier(0.4, 0, 0.2, 1) infinite;
}

@keyframes sweep {
  0%   { transform: translateX(-200%); }
  100% { transform: translateX(400%); }
}

.live-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--red);
  font-weight: 500;
}

.live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--red);
  animation: pulse 1.4s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(0.7); }
}

/* ── Messages ──────────────────────────────────────── */
.msg {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12px;
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: var(--radius);
  border-left: 2px solid;
  line-height: 1.5;
}

.msg-error  { background: var(--red-dim);   color: var(--red);   border-color: var(--red); }
.msg-success{ background: var(--green-dim); color: var(--green); border-color: var(--green); }
.msg-info   { background: var(--blue-dim);  color: var(--blue);  border-color: var(--blue); }

/* ── Source tabs (inner) ───────────────────────────── */
.source-tabs {
  display: flex;
  gap: 0;
  border: 1px solid var(--border2);
  border-radius: var(--radius);
  overflow: hidden;
  margin-bottom: 16px;
  width: fit-content;
}

.source-tab {
  padding: 6px 16px;
  border: none;
  background: transparent;
  color: var(--muted);
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  cursor: pointer;
  transition: all 0.12s;
  border-right: 1px solid var(--border2);
}

.source-tab:last-child { border-right: none; }
.source-tab:hover:not(:disabled) { color: var(--text); background: rgba(255,255,255,0.04); }
.source-tab.active { color: var(--accent); background: var(--accent-dim); }
.source-tab:disabled { cursor: not-allowed; opacity: 0.4; }

/* ── Video preview ─────────────────────────────────── */
.preview-wrap {
  position: relative;
  border-radius: var(--radius);
  overflow: hidden;
  background: #000;
  margin-bottom: 16px;
  border: 1px solid var(--border);
}

.preview-wrap video,
.preview-wrap audio {
  width: 100%;
  display: block;
  max-height: 300px;
}

/* ── Time scrubbers ────────────────────────────────── */
.scrubbers {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 14px;
}

.scrubber-label {
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--muted);
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}

.scrubber-time {
  font-family: var(--font-ui);
  font-weight: 700;
  font-size: 16px;
  color: var(--accent);
}

input[type="range"] {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 3px;
  background: var(--surface2);
  border-radius: 2px;
  outline: none;
  margin: 8px 0;
}

input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--accent);
  cursor: pointer;
  box-shadow: 0 0 0 3px var(--accent-glow);
  transition: box-shadow 0.15s;
}

input[type="range"]::-webkit-slider-thumb:hover {
  box-shadow: 0 0 0 5px var(--accent-glow);
}

/* ── File input ────────────────────────────────────── */
.file-drop {
  border: 1px dashed var(--border2);
  border-radius: var(--radius);
  padding: 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.15s;
  background: var(--bg);
  position: relative;
}

.file-drop:hover { border-color: var(--accent); background: var(--accent-dim); }
.file-drop input { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; height: 100%; }

.file-drop-text {
  font-size: 12px;
  color: var(--muted);
  pointer-events: none;
}

.file-drop-text strong { color: var(--accent); display: block; font-size: 13px; margin-bottom: 4px; }

/* ── Library grid ──────────────────────────────────── */
.library-empty {
  font-size: 12px;
  color: var(--muted);
  text-align: center;
  padding: 20px;
  border: 1px dashed var(--border);
  border-radius: var(--radius);
}

/* Scrollbar */
::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--muted2); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--muted); }
</style>
