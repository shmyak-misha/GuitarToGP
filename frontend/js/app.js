/**
 * MusicToGP — app.js
 * Handles both YouTube URL and PDF tab upload flows.
 */

const API_BASE = '';   // same origin; change to 'http://localhost:8000' for separate dev servers
const POLL_INTERVAL_MS = 1500;

// ── Version display ───────────────────────────────────────────────────────────
fetch(`${API_BASE}/api/version`)
  .then(r => r.json())
  .then(d => {
    const el = document.getElementById('app-version');
    if (el) el.textContent = `v${d.version}`;
  })
  .catch(() => {});

// ── DOM refs ────────────────────────────────────────────────────────────────
const urlInput        = document.getElementById('youtube-url');
const convertBtn      = document.getElementById('convert-btn');
const inputError      = document.getElementById('input-error');
const youtubePreview  = document.getElementById('youtube-preview');
const youtubeFrame    = document.getElementById('youtube-preview-frame');
const youtubeTitle    = document.getElementById('youtube-preview-title');
const youtubeLink     = document.getElementById('youtube-preview-link');

const pdfFileInput    = document.getElementById('pdf-file-input');
const dropZone        = document.getElementById('drop-zone');
const pdfFilename     = document.getElementById('pdf-filename');
const pdfError        = document.getElementById('pdf-error');
const convertPdfBtn   = document.getElementById('convert-pdf-btn');

const tabYoutube      = document.getElementById('tab-youtube');
const tabPdf          = document.getElementById('tab-pdf');
const panelYoutube    = document.getElementById('panel-youtube');
const panelPdf        = document.getElementById('panel-pdf');

const progressSection = document.getElementById('progress-section');
const progressLabel   = document.getElementById('progress-label');
const progressPct     = document.getElementById('progress-pct');
const progressFill    = document.getElementById('progress-fill');
const progressMsg     = document.getElementById('progress-message');

const downloadSection = document.getElementById('download-section');
const downloadLink    = document.getElementById('download-link');
const newBtn          = document.getElementById('new-btn');

const errorSection    = document.getElementById('error-section');
const errorMessage    = document.getElementById('error-message');
const retryBtn        = document.getElementById('retry-btn');

let pollTimer    = null;
let selectedPdf  = null;   // File object for pending PDF upload
let activeMode   = 'youtube';  // 'youtube' | 'pdf'

// ── Tab switching ─────────────────────────────────────────────────────────────

function switchTab(mode) {
  activeMode = mode;
  tabYoutube.classList.toggle('mode-tab--active', mode === 'youtube');
  tabYoutube.setAttribute('aria-selected', String(mode === 'youtube'));
  tabPdf.classList.toggle('mode-tab--active', mode === 'pdf');
  tabPdf.setAttribute('aria-selected', String(mode === 'pdf'));
  panelYoutube.hidden = mode !== 'youtube';
  panelPdf.hidden     = mode !== 'pdf';
  showSection(null);
}

tabYoutube.addEventListener('click', () => switchTab('youtube'));
tabPdf.addEventListener('click',     () => switchTab('pdf'));

// ── UI state helpers ─────────────────────────────────────────────────────────

function showSection(name) {
  progressSection.hidden = name !== 'progress';
  downloadSection.hidden = name !== 'download';
  errorSection.hidden    = name !== 'error';
}

function setInputError(msg) {
  inputError.textContent = msg;
  inputError.hidden = !msg;
}

function setPdfError(msg) {
  pdfError.textContent = msg;
  pdfError.hidden = !msg;
}

function extractYouTubeVideoId(raw) {
  if (!raw) return null;

  try {
    const u = new URL(raw.trim());
    const host = u.hostname.toLowerCase().replace(/^www\./, '');

    if (host === 'youtu.be') {
      const id = u.pathname.split('/').filter(Boolean)[0];
      return id ? id.slice(0, 11) : null;
    }

    if (host === 'youtube.com' || host === 'm.youtube.com' || host === 'music.youtube.com') {
      const watchId = u.searchParams.get('v');
      if (watchId) return watchId.slice(0, 11);

      const parts = u.pathname.split('/').filter(Boolean);
      if (parts.length >= 2 && (parts[0] === 'embed' || parts[0] === 'shorts')) {
        return parts[1].slice(0, 11);
      }
    }
  } catch {
    return null;
  }

  return null;
}

function updateYouTubePreview(rawUrl) {
  const videoId = extractYouTubeVideoId(rawUrl);
  if (!videoId) {
    youtubePreview.hidden = true;
    youtubeFrame.src = 'about:blank';
    youtubeTitle.textContent = 'YouTube preview';
    youtubeLink.href = '#';
    return;
  }

  const watchUrl = `https://www.youtube.com/watch?v=${videoId}`;
  youtubeFrame.src = `https://www.youtube.com/embed/${videoId}?rel=0&modestbranding=1`;
  youtubeTitle.textContent = `Preview ready for: ${videoId}`;
  youtubeLink.href = watchUrl;
  youtubePreview.hidden = false;
}

function resetUI() {
  showSection(null);
  setInputError('');
  setPdfError('');
  convertBtn.disabled    = false;
  urlInput.disabled      = false;
  convertPdfBtn.disabled = !selectedPdf;
  updateProgress(0, 'Processing…', '');
  updateYouTubePreview(urlInput.value);
}

function updateProgress(pct, label, message) {
  progressFill.style.width  = `${pct}%`;
  progressPct.textContent   = `${pct}%`;
  progressLabel.textContent = label;
  progressMsg.textContent   = message;
}

// ── PDF drop zone ─────────────────────────────────────────────────────────────

function onPdfSelected(file) {
  if (!file || !file.name.toLowerCase().endsWith('.pdf')) {
    setPdfError('Please select a PDF file.');
    return;
  }
  setPdfError('');
  selectedPdf = file;
  pdfFilename.textContent = `📄 ${file.name}`;
  pdfFilename.hidden = false;
  convertPdfBtn.disabled = false;
}

pdfFileInput.addEventListener('change', () => {
  if (pdfFileInput.files.length) onPdfSelected(pdfFileInput.files[0]);
});

dropZone.addEventListener('click', (e) => {
  // Don't trigger file dialog if the "Browse" label was clicked (it does it natively)
  if (e.target.classList.contains('drop-zone__browse')) return;
  pdfFileInput.click();
});

dropZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  dropZone.classList.add('drop-zone--over');
});

dropZone.addEventListener('dragleave', () => {
  dropZone.classList.remove('drop-zone--over');
});

dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('drop-zone--over');
  const file = e.dataTransfer.files[0];
  if (file) onPdfSelected(file);
});

// ── API calls ────────────────────────────────────────────────────────────────

async function startConversion(url) {
  const res = await fetch(`${API_BASE}/api/convert`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? `Server error ${res.status}`);
  }
  return res.json();
}

async function startPdfConversion(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}/api/convert-pdf`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(data.detail ?? `Server error ${res.status}`);
  }
  return res.json();
}

async function pollStatus(jobId) {
  const res = await fetch(`${API_BASE}/api/status/${jobId}`);
  if (!res.ok) throw new Error(`Status check failed (${res.status})`);
  return res.json();
}

// ── Poll loop ─────────────────────────────────────────────────────────────────

function startPolling(jobId) {
  clearInterval(pollTimer);

  pollTimer = setInterval(async () => {
    let job;
    try {
      job = await pollStatus(jobId);
    } catch (err) {
      clearInterval(pollTimer);
      showError(`Network error while checking status: ${err.message}`);
      return;
    }

    updateProgress(
      job.progress,
      job.status === 'completed' ? 'Done!' : 'Processing…',
      job.message,
    );

    if (job.status === 'completed') {
      clearInterval(pollTimer);
      onCompleted(jobId, job.filename);
    } else if (job.status === 'failed') {
      clearInterval(pollTimer);
      showError(job.message);
    }
  }, POLL_INTERVAL_MS);
}

// ── Outcome handlers ──────────────────────────────────────────────────────────

function onCompleted(jobId, filename) {
  downloadLink.href     = `${API_BASE}/api/download/${jobId}`;
  downloadLink.download = filename;
  showSection('download');
  convertBtn.disabled    = false;
  urlInput.disabled      = false;
  convertPdfBtn.disabled = false;
}

function showError(msg) {
  errorMessage.textContent = msg;
  showSection('error');
  convertBtn.disabled    = false;
  urlInput.disabled      = false;
  convertPdfBtn.disabled = false;
}

// ── YouTube convert action ────────────────────────────────────────────────────

async function handleConvert() {
  const url = urlInput.value.trim();
  setInputError('');

  if (!url) {
    setInputError('Please enter a YouTube URL.');
    urlInput.focus();
    return;
  }
  if (!url.startsWith('http://') && !url.startsWith('https://')) {
    setInputError('URL must start with http:// or https://');
    urlInput.focus();
    return;
  }
  if (!extractYouTubeVideoId(url)) {
    setInputError('Please paste a valid YouTube URL (watch, youtu.be, shorts, or embed). For best scanning quality, use solo fingerpicking acoustic/classical guitar videos.');
    urlInput.focus();
    return;
  }

  convertBtn.disabled = true;
  urlInput.disabled   = true;
  showSection('progress');
  updateProgress(5, 'Starting…', 'Sending request to server…');

  let job;
  try {
    job = await startConversion(url);
  } catch (err) {
    showError(err.message);
    return;
  }

  updateProgress(job.progress, 'Processing…', job.message);
  startPolling(job.job_id);
}

// ── PDF convert action ────────────────────────────────────────────────────────

async function handleConvertPdf() {
  setPdfError('');
  if (!selectedPdf) {
    setPdfError('No PDF selected.');
    return;
  }

  convertPdfBtn.disabled = true;
  showSection('progress');
  updateProgress(10, 'Uploading PDF…', 'Sending file to server…');

  let job;
  try {
    job = await startPdfConversion(selectedPdf);
  } catch (err) {
    showError(err.message);
    return;
  }

  updateProgress(job.progress, 'Processing…', job.message);
  startPolling(job.job_id);
}

// ── Event listeners ───────────────────────────────────────────────────────────

convertBtn.addEventListener('click', handleConvert);
convertPdfBtn.addEventListener('click', handleConvertPdf);

urlInput.addEventListener('input', () => {
  updateYouTubePreview(urlInput.value);
});

urlInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') handleConvert();
});

newBtn.addEventListener('click', () => {
  urlInput.value = '';
  selectedPdf = null;
  pdfFilename.hidden = true;
  pdfFileInput.value = '';
  convertPdfBtn.disabled = true;
  resetUI();
  if (activeMode === 'youtube') urlInput.focus();
});

retryBtn.addEventListener('click', () => {
  resetUI();
  if (activeMode === 'youtube') urlInput.focus();
});

// Initialize preview state on first load.
updateYouTubePreview(urlInput.value);

