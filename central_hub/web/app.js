document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const navBtns = document.querySelectorAll('.nav-btn');
  const tabPanes = document.querySelectorAll('.tab-pane');
  const sectionTitle = document.getElementById('section-title');
  const sectionDesc = document.getElementById('section-desc');

  // Header stats
  const headerDriveC = document.getElementById('header-drive-c-val');
  const headerDriveE = document.getElementById('header-drive-e-val');
  const headerRam = document.getElementById('header-ram-val');
  const pillDriveC = document.getElementById('pill-drive-c');
  const diskAlertDot = document.getElementById('disk-alert-dot');

  // Telemetry Pane
  const cBadgeStatus = document.getElementById('c-badge-status');
  const cProgressFill = document.getElementById('c-progress-fill');
  const cUsed = document.getElementById('c-used');
  const cFree = document.getElementById('c-free');
  const cardDriveC = document.getElementById('card-drive-c');
  const cleanerHintText = document.getElementById('cleaner-hint-text');
  const btnCleanDisk = document.getElementById('btn-clean-disk');
  const cleanResult = document.getElementById('clean-result');

  const eBadgeStatus = document.getElementById('e-badge-status');
  const eProgressFill = document.getElementById('e-progress-fill');
  const eUsed = document.getElementById('e-used');
  const eFree = document.getElementById('e-free');

  const valCpuCores = document.getElementById('val-cpu-cores');
  const valRamTotal = document.getElementById('val-ram-total');
  const valRamUsed = document.getElementById('val-ram-used');
  const valRamFree = document.getElementById('val-ram-free');
  const ramProgressFill = document.getElementById('ram-progress-fill');

  // Chat Elements
  const chatMessages = document.getElementById('chat-messages');
  const userInput = document.getElementById('user-input');
  const sendBtn = document.getElementById('send-btn');
  const checkWebSearch = document.getElementById('check-web-search');
  const promptPills = document.querySelectorAll('.pill-btn');
  const modelSelectorSide = document.getElementById('model-selector-side');
  const activeModelDisplay = document.getElementById('active-model-display');

  // Files Elements
  const fileCurrentPath = document.getElementById('file-current-path');
  const fileListContainer = document.getElementById('file-list-container');
  const previewFilename = document.getElementById('preview-filename');
  const previewContent = document.getElementById('preview-content');
  const btnFileUp = document.getElementById('btn-file-up');
  const btnRefreshFiles = document.getElementById('btn-refresh-files');

  let currentFolderPath = "C:/Users/rezky/Documents/agent";
  let parentFolderPath = "";

  // 1. TAB SWITCHING
  const tabInfo = {
    chat: { title: "AI Assistant", desc: "Percakapan otonom lokal dengan akses internet & kendali file" },
    telemetry: { title: "Hardware & Disk Monitor", desc: "Pemantau real-time SSD C, HDD E, CPU, dan pembersih disk otomatis" },
    files: { title: "Visual File Manager", desc: "Jelajahi dan baca isi file di sistem komputer Anda" },
    tools: { title: "Tools & Sandbox", desc: "Akses cepat ke alat eksekusi otonom" }
  };

  navBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      navBtns.forEach(b => b.classList.remove('active'));
      tabPanes.forEach(p => p.classList.remove('active'));

      btn.classList.add('active');
      const tabKey = btn.dataset.tab;
      document.getElementById(`pane-${tabKey}`).classList.add('active');

      if (tabInfo[tabKey]) {
        sectionTitle.textContent = tabInfo[tabKey].title;
        sectionDesc.textContent = tabInfo[tabKey].desc;
      }

      if (tabKey === 'files') {
        loadDirectory(currentFolderPath);
      }
    });
  });

  // 2. TELEMETRY POLLING
  async function fetchTelemetry() {
    try {
      const res = await fetch('/api/status');
      const data = await res.json();

      // Drive C
      const c = data.drives.C;
      headerDriveC.textContent = `${c.free_gb} GB Free`;
      cUsed.textContent = `${c.used_gb} GB`;
      cFree.textContent = `${c.free_gb} GB (${c.percent_free}%)`;
      const usedPctC = 100 - c.percent_free;
      cProgressFill.style.width = `${usedPctC}%`;

      if (c.is_red) {
        pillDriveC.classList.add('pill-red');
        cardDriveC.classList.add('card-red');
        cBadgeStatus.className = "status-badge badge-red";
        cBadgeStatus.textContent = "PERINGATAN: <10% (MERAH)";
        cProgressFill.className = "progress-bar-fill fill-red";
        diskAlertDot.style.display = "flex";
        cleanerHintText.innerHTML = `⚠️ <strong>Peringatan Windows:</strong> Sisa ruang tinggal <strong>${c.free_gb} GB (${c.percent_free}%)</strong> sehingga berwarna <strong>MERAH</strong>. Klik tombol di bawah untuk membersihkan 3,2 GB rekaman browser dan mengembalikannya ke warna <strong>BIRU</strong>!`;
      } else {
        pillDriveC.classList.remove('pill-red');
        cardDriveC.classList.remove('card-red');
        cBadgeStatus.className = "status-badge badge-green";
        cBadgeStatus.textContent = "AMAN (BIRU)";
        cProgressFill.className = "progress-bar-fill";
        diskAlertDot.style.display = "none";
        cleanerHintText.innerHTML = `✅ <strong>Kondisi Normal:</strong> Sisa ruang <strong>${c.free_gb} GB (${c.percent_free}%)</strong>, status bilah Windows berwarna <strong>BIRU</strong>.`;
      }

      // Drive E
      const e = data.drives.E;
      if (e && e.exists) {
        headerDriveE.textContent = `${e.free_gb} GB Free`;
        eUsed.textContent = `${e.used_gb} GB`;
        eFree.textContent = `${e.free_gb} GB (${e.percent_free}%)`;
        eProgressFill.style.width = `${100 - e.percent_free}%`;
        eBadgeStatus.textContent = "TERHUBUNG (ONLINE)";
      } else {
        headerDriveE.textContent = "Offline";
        eUsed.textContent = "0 GB";
        eFree.textContent = "0 GB";
        eProgressFill.style.width = "0%";
        eBadgeStatus.className = "status-badge";
        eBadgeStatus.textContent = "TIDAK TERHUBUNG";
      }

      // RAM & CPU
      valCpuCores.textContent = `${data.cpu_cores} Cores / 8 Threads`;
      valRamTotal.textContent = `${data.ram.total_gb} GB DDR4`;
      valRamUsed.textContent = `${data.ram.used_gb} GB (${data.ram.percent}%)`;
      valRamFree.textContent = `${data.ram.free_gb} GB`;
      headerRam.textContent = `${data.ram.used_gb}/${data.ram.total_gb} GB`;
      ramProgressFill.style.width = `${data.ram.percent}%`;

      // Active Model & Dynamic Dropdown Update
      if (data.active_model) {
        activeModelDisplay.textContent = data.active_model;
      }

      if (data.models) {
        Object.keys(data.models).forEach(key => {
          const m = data.models[key];
          const opt = modelSelectorSide.querySelector(`option[value="${key}"]`);
          if (opt) {
            opt.textContent = m.label;
            opt.disabled = !m.available;
          }
        });
      }
    } catch (err) {
      console.warn("Telemetry fetch error:", err);
    }
  }

  fetchTelemetry();
  setInterval(fetchTelemetry, 6000);

  // 3. ONE-CLICK DISK CLEANER
  btnCleanDisk.addEventListener('click', async () => {
    btnCleanDisk.disabled = true;
    btnCleanDisk.textContent = "⏳ Sedang membersihkan 28.000+ file sementara...";

    try {
      const res = await fetch('/api/clean_disk', { method: 'POST' });
      const data = await res.json();

      cleanResult.style.display = "block";
      cleanResult.innerHTML = `🎉 <strong>Pembersihan Berhasil!</strong> Memulihkan <strong>${data.recovered_mb} MB (${data.recovered_gb} GB)</strong> ruang kosong. Sisa Drive C sekarang: <strong>${data.new_drive_c.free_gb} GB</strong>. Warna bilah Windows seketika kembali <strong>BIRU</strong>!`;

      await fetchTelemetry();
    } catch (e) {
      cleanResult.style.display = "block";
      cleanResult.style.color = "#f43f5e";
      cleanResult.textContent = `Gagal membersihkan: ${e}`;
    } finally {
      btnCleanDisk.disabled = false;
      btnCleanDisk.textContent = "🧹 Bersihkan Cache & Pulihkan Ruang C Seketika";
    }
  });

  // 4. MODEL SWITCHER
  modelSelectorSide.addEventListener('change', async () => {
    const val = modelSelectorSide.value;
    activeModelDisplay.textContent = "Beralih model...";
    try {
      const res = await fetch('/api/switch_model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: jsonString({ model: val })
      });
      const data = await res.json();
      activeModelDisplay.textContent = `Model: ${val.toUpperCase()}`;
      await fetchTelemetry();
    } catch (e) {
      console.error(e);
    }
  });

  // 5. CHAT LOGIC
  function appendMessage(sender, text, isCode = false) {
    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${sender}-bubble`;

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = sender === 'ai' ? 'AI' : 'Anda';

    const content = document.createElement('div');
    content.className = 'bubble-content';

    // Format text and code blocks
    let formattedHtml = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // Format code blocks
    formattedHtml = formattedHtml.replace(/```(?:python|bash|cmd|rust|json)?\n([\s\S]*?)```/g, (match, code) => {
      return `<pre><code>${code.trim()}</code></pre>`;
    });

    // Format bold
    formattedHtml = formattedHtml.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');

    // Format newlines
    formattedHtml = formattedHtml.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br>');
    content.innerHTML = `<p>${formattedHtml}</p>`;

    bubble.appendChild(avatar);
    bubble.appendChild(content);
    chatMessages.appendChild(bubble);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return content;
  }

  async function sendMessage(text) {
    const query = text.trim();
    if (!query) return;

    appendMessage('user', query);
    userInput.value = "";
    userInput.style.height = "auto";

    // Show AI typing indicator
    const aiBubbleContent = appendMessage('ai', "⏳ <em>Sedang berpikir dan mencari data...</em>");

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: query,
          use_web: checkWebSearch.checked,
          model: modelSelectorSide.value
        })
      });

      const data = await res.json();
      const replyText = data.reply || "(Tidak ada jawaban yang dihasilkan)";

      // Format reply
      let formattedHtml = replyText
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/```(?:python|bash|cmd|rust|json)?\n([\s\S]*?)```/g, (m, code) => `<pre><code>${code.trim()}</code></pre>`)
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>');

      aiBubbleContent.innerHTML = `<p>${formattedHtml}</p>`;
      chatMessages.scrollTop = chatMessages.scrollHeight;
    } catch (err) {
      aiBubbleContent.innerHTML = `<p style="color:#f43f5e;">Terjadi kesalahan: ${err}</p>`;
    }
  }

  sendBtn.addEventListener('click', () => sendMessage(userInput.value));

  userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage(userInput.value);
    }
  });

  promptPills.forEach(pill => {
    pill.addEventListener('click', () => {
      const prompt = pill.dataset.prompt;
      sendMessage(prompt);
    });
  });

  window.sendQuickCommand = function(cmd) {
    // Switch to chat tab and send
    document.getElementById('tab-chat-btn').click();
    sendMessage(cmd);
  };

  window.switchModelDirect = async function(modelName) {
    modelSelectorSide.value = modelName;
    modelSelectorSide.dispatchEvent(new Event('change'));
    document.getElementById('tab-chat-btn').click();
    appendMessage('ai', `Otak AI telah dialihkan ke mode <strong>${modelName.toUpperCase()}</strong>! Siap digunakan dengan respon super cepat.`);
  };

  // 6. VISUAL FILE EXPLORER
  async function loadDirectory(path) {
    fileCurrentPath.textContent = path;
    fileListContainer.innerHTML = '<div style="padding:1rem;color:var(--text-dim);">Memuat berkas...</div>';

    try {
      const res = await fetch(`/api/files?path=${encodeURIComponent(path)}`);
      const data = await res.json();

      currentFolderPath = data.path;
      parentFolderPath = data.parent;
      fileCurrentPath.textContent = data.path;

      if (data.error) {
        fileListContainer.innerHTML = `<div style="padding:1rem;color:var(--accent-rose);">${data.error}</div>`;
        return;
      }

      fileListContainer.innerHTML = "";
      if (data.items.length === 0) {
        fileListContainer.innerHTML = '<div style="padding:1rem;color:var(--text-dim);">Folder kosong</div>';
        return;
      }

      data.items.forEach(item => {
        const row = document.createElement('div');
        row.className = 'file-item';

        const icon = item.is_dir ? '📁' : getFileIcon(item.name);
        const sizeStr = item.is_dir ? '' : `${item.size_kb} KB`;

        row.innerHTML = `
          <span>${icon}</span>
          <span class="file-item-name">${item.name}</span>
          <span class="file-item-size">${sizeStr}</span>
        `;

        row.addEventListener('click', () => {
          document.querySelectorAll('.file-item').forEach(r => r.classList.remove('active'));
          row.classList.add('active');

          if (item.is_dir) {
            loadDirectory(item.path);
          } else {
            loadFilePreview(item.path, item.name);
          }
        });

        fileListContainer.appendChild(row);
      });
    } catch (e) {
      fileListContainer.innerHTML = `<div style="padding:1rem;color:var(--accent-rose);">Error: ${e}</div>`;
    }
  }

  function getFileIcon(name) {
    if (name.endsWith('.py')) return '🐍';
    if (name.endsWith('.rs')) return '🦀';
    if (name.endsWith('.html') || name.endsWith('.css') || name.endsWith('.js')) return '🌐';
    if (name.endsWith('.json') || name.endsWith('.toml')) return '⚙️';
    if (name.endsWith('.bat') || name.endsWith('.sh') || name.endsWith('.ps1')) return '⚡';
    if (name.endsWith('.md') || name.endsWith('.txt')) return '📄';
    return '📄';
  }

  async function loadFilePreview(filePath, filename) {
    previewFilename.textContent = filename;
    previewContent.textContent = "Membaca berkas...";

    try {
      const res = await fetch('/api/files/read', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: filePath })
      });
      const data = await res.json();
      if (data.success) {
        previewContent.textContent = data.content;
      } else {
        previewContent.textContent = `Gagal membaca file: ${data.error}`;
      }
    } catch (e) {
      previewContent.textContent = `Error: ${e}`;
    }
  }

  btnFileUp.addEventListener('click', () => {
    if (parentFolderPath) {
      loadDirectory(parentFolderPath);
    }
  });

  btnRefreshFiles.addEventListener('click', () => {
    loadDirectory(currentFolderPath);
  });
});
