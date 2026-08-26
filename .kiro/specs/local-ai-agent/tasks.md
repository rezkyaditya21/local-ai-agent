# Implementation Plan: Local AI Agent

## Overview

Implementasi dilakukan secara bertahap dari fondasi (struktur proyek, model data) menuju lapisan yang lebih tinggi (tools, orchestration, CLI). Setiap langkah membangun di atas langkah sebelumnya dan diakhiri dengan penyambungan komponen menjadi sistem yang berfungsi penuh. Pengujian berbasis properti (Hypothesis) disertakan berdekatan dengan implementasi komponen yang diuji.

---

## Tasks

- [x] 1. Inisialisasi struktur proyek dan konfigurasi dependensi
  - Buat struktur direktori paket `agent/` beserta sub-paket: `cli/`, `core/`, `tools/`, `models/`, `self_improvement/`
  - Buat file `pyproject.toml` dengan dependensi produksi: `rich`, `llama-cpp-python`, `httpx[http2]`, `playwright`, `sqlalchemy`, `cryptography`, `tomli-w`
  - Tambahkan dependensi pengujian opsional: `pytest>=8.0`, `pytest-asyncio>=0.23`, `hypothesis>=6.100`, `pytest-mock>=3.12`
  - Buat file `__init__.py` untuk setiap sub-paket
  - Buat file `config.toml` template dengan field `default_model`, `tool_directories`, `sandbox_enabled`, `shell_timeout_seconds`, `log_path`, `max_consecutive_actions`
  - Buat direktori `tests/` dengan sub-direktori: `unit/`, `property/`, `integration/`, `smoke/`
  - Buat `conftest.py` di root `tests/` dengan fixture dasar (event loop, tmp_path)
  - _Requirements: 7.1, 7.6, 10.4_

- [x] 2. Implementasi data models dan skema inti
  - [x] 2.1 Buat `agent/models/schemas.py` dengan semua dataclass
    - Implementasikan dataclass: `FileEntry`, `ShellResult`, `BackgroundProcess`, `ExtractedContent`, `ColumnInfo`, `TableSchema`, `DatabaseSchema`, `HTTPResponse`, `CredentialEntry`, `AgentConfig`, `ConfigProposal`, `TaskPlan`, `ToolCall`, `ToolResult`, `InteractionRecord`
    - Pastikan semua field memiliki type hint yang akurat sesuai desain
    - _Requirements: 2.7, 3.1, 3.2, 4.1, 5.3, 6.3, 8.1_

  - [x] 2.2 Buat `agent/core/exceptions.py` dengan semua kelas error kustom
    - Implementasikan semua 20 error code: `FileNotFoundError` (E001) hingga `SelfImprovementApplyError` (E020)
    - Setiap exception class harus menyertakan kode error, nama, dan pesan deskriptif yang memuat entitas yang terlibat
    - _Requirements: 2.9, 3.7, 4.5, 5.2, 5.6, 6.5, 6.7, 7.5, 7.7, 8.4, 8.6, 8.9, 9.6, 10.2_

- [x] 3. Implementasi Blocklist
  - [x] 3.1 Buat `agent/core/blocklist.py`
    - Implementasikan enum `BlocklistEntryType` dengan tipe: `FILE_PATH`, `COMMAND`, `DOMAIN`
    - Implementasikan dataclass `BlocklistEntry` dengan field `entry_type` dan `pattern`
    - Implementasikan kelas `Blocklist` dengan method `is_blocked()`, `load_from_file()`, `add_entry()`
    - Logika matching: exact match atau glob untuk `FILE_PATH`, substring match untuk `COMMAND` dan `DOMAIN`
    - _Requirements: 10.7, 10.8_

  - [ ]* 3.2 Tulis unit tests untuk Blocklist
    - Uji matching exact path, glob path, substring command, substring domain
    - Uji kasus tidak ada file blocklist (graceful)
    - Uji penambahan entri secara dinamis
    - _Requirements: 10.7, 10.8_

- [x] 4. Implementasi Audit Logger
  - [x] 4.1 Buat `agent/core/audit_logger.py`
    - Implementasikan kelas `AuditLogger` dengan `RotatingFileHandler` (maxBytes = 100 MB)
    - Implementasikan method `log_action(action, params, result, confirmed)` dengan timestamp ISO 8601
    - Implementasikan method `log_error(error, context)`
    - Pastikan nilai credential tidak pernah dicatat ke log (filter berdasarkan key yang dikenal)
    - _Requirements: 10.4, 10.5_

  - [ ]* 4.2 Tulis unit tests untuk AuditLogger
    - Uji format timestamp ISO 8601
    - Uji rotasi log saat file mencapai 100 MB
    - Uji bahwa nilai credential tidak muncul di output log
    - _Requirements: 10.4, 10.5_

- [x] 5. Implementasi Confirmation Gate
  - [x] 5.1 Buat `agent/core/confirmation_gate.py`
    - Implementasikan dataclass `ConfirmationRequest` dengan field `operation_type`, `description`, `diff`, `full_command`
    - Implementasikan kelas `ConfirmationGate` dengan method `request(req)` yang menampilkan detail operasi
    - Logika timeout: auto-cancel dan kembalikan `False` setelah 60 detik tanpa input
    - Dukung injeksi `input_fn` untuk testability
    - _Requirements: 2.4, 3.4, 5.4, 8.2, 10.1, 10.2_

  - [ ]* 5.2 Tulis unit tests untuk ConfirmationGate
    - Uji input "y" mengembalikan `True`
    - Uji input "n" mengembalikan `False`
    - Uji auto-cancel setelah 60 detik (mock clock)
    - Uji tampilan diff untuk perubahan konfigurasi
    - _Requirements: 10.1, 10.2_

- [x] 6. Implementasi Tool Registry
  - [x] 6.1 Buat `agent/tools/registry.py`
    - Definisikan `ToolInterface` sebagai `Protocol` dengan field `name`, `description`, `input_schema`, `output_schema` dan method `run(params)`
    - Implementasikan dataclass `ToolEntry` dengan field `tool`, `enabled`, `source`
    - Implementasikan kelas `ToolRegistry` dengan method: `register()`, `get()`, `list_all()`, `enable()`, `disable()`, `validate_plugin_schema()`, `select_best()`
    - Batasi kapasitas maksimum 200 tools; tolak pendaftaran jika sudah penuh (`E017`)
    - Validasi skema plugin sebelum pendaftaran; tolak dengan `E014` dan daftar field yang tidak sesuai
    - Raise `ToolNotFoundError` dari `enable()`/`disable()` jika nama tidak ada
    - _Requirements: 9.1, 9.2, 9.3, 9.5, 9.6, 9.7_

  - [ ]* 6.2 Tulis unit tests untuk ToolRegistry
    - Uji register, get, enable, disable
    - Uji batas kapasitas 200 tools
    - Uji validasi skema plugin (field yang hilang)
    - Uji `ToolNotFoundError` pada enable/disable
    - _Requirements: 9.1, 9.5, 9.6, 9.7_

- [x] 7. Implementasi Credential Vault
  - [x] 7.1 Buat `agent/core/credential_vault.py`
    - Implementasikan kelas `CredentialVault` menggunakan enkripsi Fernet (`cryptography` library)
    - Method `store(key, value)`: enkripsi nilai sebelum menyimpan ke file konfigurasi terenkripsi
    - Method `retrieve(key)`: dekripsi dan kembalikan nilai tanpa pernah mencatatnya ke log
    - Pastikan file vault tidak dapat dibaca sebagai plaintext
    - _Requirements: 6.4, 10.5_

  - [ ]* 7.2 Tulis unit tests untuk CredentialVault
    - Uji store dan retrieve menghasilkan nilai yang sama
    - Uji bahwa file vault tidak mengandung nilai plaintext
    - Uji retrieve key yang tidak ada mengembalikan error yang tepat
    - _Requirements: 6.4, 10.5_

- [x] 8. Implementasi Checkpoint 1
  - Pastikan semua tests untuk komponen fondasi (Blocklist, AuditLogger, ConfirmationGate, ToolRegistry, CredentialVault) lulus
  - Pastikan semua imports antar modul berjalan tanpa error
  - Tanyakan kepada pengguna jika ada pertanyaan sebelum melanjutkan ke implementasi tools.

- [x] 9. Implementasi FileSystem Tool
  - [x] 9.1 Buat `agent/tools/filesystem.py`
    - Implementasikan kelas `FileSystemTool` yang mengimplementasikan `ToolInterface`
    - Method `read_file(path)`: baca file teks/biner, batas 500 MB, raise `E003` jika melebihi batas
    - Method `write_file(path, content)`: tulis/timpa konten file
    - Method `create(path, is_dir)`: buat file atau direktori baru
    - Method `delete(path)`: selalu lewat `ConfirmationGate` sebelum eksekusi
    - Method `move(src, dst)`: raise `E004` jika `dst` sudah ada, tanpa mengubah file
    - Method `list_dir(path)`: kembalikan `list[FileEntry]` dengan ukuran, tanggal ISO 8601, tipe
    - Method `glob_search(directory, pattern)`: kembalikan daftar path yang cocok atau daftar kosong dengan pesan
    - Semua error dikembalikan sebagai `ToolResult(success=False, error=...)` dengan kode error sesuai
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9_

  - [ ]* 9.2 Tulis property test untuk FileSystemTool — Property 4: Round-Trip Tulis-Baca File
    - **Property 4: Round-Trip Tulis-Baca File**
    - **Validates: Requirements 2.2**
    - Gunakan `@given(content=st.binary(min_size=0, max_size=10*1024))` dengan `@settings(max_examples=200)`
    - Verifikasi bahwa `read_file(path)` setelah `write_file(path, content)` menghasilkan konten identik byte-for-byte

  - [ ]* 9.3 Tulis property test untuk FileSystemTool — Property 5: Pencarian Glob Hanya Mengembalikan File yang Cocok
    - **Property 5: Pencarian Glob Hanya Mengembalikan File yang Cocok**
    - **Validates: Requirements 2.8**
    - Gunakan `@given(filenames=st.lists(...))` untuk menghasilkan nama file acak
    - Verifikasi bahwa semua hasil cocok dengan pola dan tidak ada file yang cocok yang dihilangkan

  - [ ]* 9.4 Tulis unit tests untuk FileSystemTool
    - Uji batas 500 MB (mock file size)
    - Uji `ConflictError` pada move ke path yang sudah ada
    - Uji `list_dir` menghasilkan metadata yang benar
    - Uji glob dengan tidak ada hasil mengembalikan daftar kosong dan pesan
    - _Requirements: 2.6, 2.8, 2.9_

- [x] 10. Implementasi Shell Tool
  - [x] 10.1 Buat `agent/tools/shell.py`
    - Definisikan konstanta `DESTRUCTIVE_PATTERNS` dengan pola regex untuk: `rm -rf`, `rmdir /s`, `format`, `shutdown`, `del /f /s`, `mkfs.`, `dd if=`
    - Implementasikan kelas `ShellTool` yang mengimplementasikan `ToolInterface`
    - Method `run_command(command, timeout)`: eksekusi perintah, tangkap stdout/stderr secara terpisah, kembalikan `ShellResult`; kill proses dan raise `E005` jika melebihi `timeout` (default 30 detik)
    - Method `run_script(interpreter, script_path, timeout)`: jalankan skrip dengan interpreter yang ditentukan
    - Method `start_background(command)`: jalankan proses di latar belakang, kembalikan `BackgroundProcess` dengan PID dan status
    - Method `is_destructive(command)`: kembalikan `True` jika command cocok dengan pola destruktif
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ]* 10.2 Tulis property test untuk ShellTool — Property 6: Shell Result Selalu Memiliki Tiga Komponen
    - **Property 6: Shell Result Selalu Memiliki Tiga Komponen**
    - **Validates: Requirements 3.1, 3.2**
    - Gunakan `@given(cmd=st.sampled_from([...]))` dengan berbagai perintah (berhasil, gagal, error)
    - Verifikasi bahwa setiap `ShellResult` memiliki `exit_code` (int), `stdout` (str), `stderr` (str) yang terpisah

  - [ ]* 10.3 Tulis unit tests untuk ShellTool
    - Uji deteksi pola destruktif (true positives dan false positives)
    - Uji timeout dengan mock subprocess yang lambat
    - Uji background process mengembalikan PID yang valid
    - _Requirements: 3.4, 3.5, 3.7_

- [x] 11. Implementasi HTTP API Tool
  - [x] 11.1 Buat `agent/tools/http_api.py`
    - Implementasikan kelas `HTTPAPITool` yang mengimplementasikan `ToolInterface`
    - Method `request(method, url, headers, params, body)`: dukung GET/POST/PUT/PATCH/DELETE; batas body 10 MB; timeout 30 detik
    - Ikuti redirect otomatis hingga maksimum 10 kali; raise `E011` jika melebihi batas dengan menyebutkan jumlah redirect dan URL terakhir
    - Method `get_credential(key)` dan `store_credential(key, value)` menggunakan `CredentialVault`; nilai tidak pernah di-log
    - Kembalikan `HTTPResponse` dengan `status_code`, `headers`, `body`, `final_url`, `redirect_count`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [ ]* 11.2 Tulis property test untuk HTTPAPITool — Property 7: Credential Tidak Pernah Muncul di Output
    - **Property 7: Credential Tidak Pernah Muncul di Output**
    - **Validates: Requirements 6.4, 10.5**
    - Gunakan `@given(key=st.text(...), value=st.text(min_size=8, max_size=100))` dengan `@settings(max_examples=200)`
    - Verifikasi bahwa nilai credential tidak muncul di terminal output, log, atau respons Agent

  - [ ]* 11.3 Tulis property test untuk HTTPAPITool — Property 8: Redirect Diikuti Hingga Batas Maksimum
    - **Property 8: Redirect Diikuti Hingga Batas Maksimum**
    - **Validates: Requirements 6.6, 6.7**
    - Gunakan `@given(redirect_count=st.integers(min_value=1, max_value=15))` dengan mock server
    - Verifikasi: N ≤ 10 → request berhasil sampai tujuan akhir; N > 10 → `RedirectLimitExceededError` dengan jumlah redirect dan URL terakhir

  - [ ]* 11.4 Tulis unit tests untuk HTTPAPITool
    - Uji semua HTTP method (GET, POST, PUT, PATCH, DELETE)
    - Uji timeout 30 detik (mock httpx)
    - Uji batas body 10 MB
    - _Requirements: 6.1, 6.2, 6.5_

- [x] 12. Implementasi Database Tool
  - [x] 12.1 Buat `agent/tools/database.py`
    - Implementasikan kelas `DatabaseTool` yang mengimplementasikan `ToolInterface`
    - Method `connect(connection_string)`: validasi path SQLite (raise `E008` jika tidak valid atau bukan file SQLite); dukung koneksi PostgreSQL/MySQL via SQLAlchemy jika dikonfigurasi
    - Method `select(query)`: eksekusi SELECT, kembalikan `list[dict]` dengan batas 1.000 baris
    - Method `execute_dml(query)`: selalu lewat `ConfirmationGate`; raise `E009` jika gagal tanpa mengubah state DB
    - Method `get_schema()`: kembalikan `DatabaseSchema` dengan nama tabel, kolom, tipe data, constraint
    - Method `disconnect()`
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [ ]* 12.2 Tulis unit tests untuk DatabaseTool
    - Uji koneksi path SQLite valid dan tidak valid
    - Uji SELECT mengembalikan baris dengan pemetaan nama kolom
    - Uji batas 1.000 baris
    - Uji `get_schema()` menghasilkan nama tabel dan kolom yang benar
    - Uji `execute_dml` selalu meminta konfirmasi
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 13. Implementasi Browser Tool
  - [x] 13.1 Buat `agent/tools/browser.py`
    - Implementasikan kelas `BrowserTool` yang mengimplementasikan `ToolInterface` menggunakan Playwright
    - Method `fetch_html(url)`: ambil konten HTML sebagai string UTF-8; timeout 30 detik; raise `E007` jika gagal
    - Method `extract_content(html)`: ekstrak teks, tautan, dan data terstruktur dari HTML; kembalikan `ExtractedContent`
    - Method `fill_form(url, selectors)`: isi formulir menggunakan headless browser
    - Method `click_element(url, selector)`: klik elemen pada halaman
    - Method `screenshot(url, output_path)`: simpan screenshot sebagai PNG; kembalikan path file
    - Method `set_cookies(domain, cookies)`: simpan cookies/token sesi untuk domain
    - Jalankan browser dalam mode headless (`headless=True`) agar kompatibel tanpa display
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_

  - [ ]* 13.2 Tulis unit tests untuk BrowserTool
    - Uji `fetch_html` timeout dengan mock Playwright
    - Uji `extract_content` mengekstrak teks dan tautan dengan benar
    - Uji `screenshot` menghasilkan file PNG dengan path yang valid
    - _Requirements: 4.1, 4.2, 4.4, 4.5_

- [x] 14. Implementasi Checkpoint 2
  - Pastikan semua tests untuk built-in tools (FileSystemTool, ShellTool, HTTPAPITool, DatabaseTool, BrowserTool) lulus
  - Daftarkan semua built-in tools ke `ToolRegistry` dan verifikasi registrasi berhasil
  - Tanyakan kepada pengguna jika ada pertanyaan sebelum melanjutkan ke komponen inti.

- [x] 15. Implementasi Model Manager
  - [x] 15.1 Buat `agent/models/manager.py`
    - Implementasikan dataclass `ModelConfig` dan `ModelParameters`
    - Implementasikan kelas `ModelManager` dengan inisialisasi dari `config.toml`
    - Method `list_models()`: kembalikan semua model terdaftar dalam ≤2 detik
    - Method `switch_model(name)`: ganti model aktif dalam ≤30 detik; raise `E012` jika tidak ada; pertahankan model lama jika gagal dimuat dalam 10 detik (`E013`)
    - Method `generate(prompt, history)`: stream token dari model aktif (GGUF via `llama-cpp-python` atau API via `httpx`)
    - Method `update_parameters(params)`: validasi rentang `temperature` (0.0–2.0) dan `context_length` (128–131072); raise `E016` jika di luar rentang
    - Method `set_default(name)`: simpan model default ke `config.toml`
    - Method `load_config()`: muat ulang konfigurasi dari `config.toml`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 8.5, 8.6_

  - [ ]* 15.2 Tulis unit tests untuk ModelManager
    - Uji `list_models()` dari config yang valid
    - Uji `switch_model()` ke model yang ada dan yang tidak ada
    - Uji `update_parameters()` dengan nilai valid, terlalu kecil, dan terlalu besar
    - Uji `set_default()` menyimpan ke `config.toml`
    - Uji agent tetap berjalan saat model gagal dimuat (`E013`)
    - _Requirements: 7.3, 7.4, 7.5, 7.6, 7.7, 8.5, 8.6_

- [x] 16. Implementasi Executor
  - [x] 16.1 Buat `agent/core/executor.py`
    - Implementasikan kelas `Executor` dengan dependensi `ToolRegistry`, `ConfirmationGate`, `Sandbox` (opsional)
    - Method `execute(call)`: ambil tool dari registry, periksa blocklist, jalankan tool
    - Tangkap semua exception dari plugin tanpa menghentikan sesi; catat ke `AuditLogger`; kembalikan `ToolResult(success=False, error=...)`
    - Method `is_destructive(call)`: delegasikan ke tool masing-masing untuk menentukan apakah konfirmasi diperlukan
    - Jika tool bersifat destruktif, panggil `ConfirmationGate.request()` terlebih dahulu
    - Jika `sandbox` dikonfigurasi, jalankan shell dan skrip di dalam sandbox
    - _Requirements: 3.4, 9.8, 10.1, 10.6_

  - [ ]* 16.2 Tulis property test untuk Executor — Property 10: Isolasi Error Plugin Tidak Menghentikan Sesi
    - **Property 10: Isolasi Error Plugin Tidak Menghentikan Sesi**
    - **Validates: Requirements 9.8**
    - Gunakan `@given(error_type=st.sampled_from([ValueError, RuntimeError, OSError, KeyError, Exception]))` dengan `@settings(max_examples=100)`
    - Verifikasi: plugin yang melempar exception menghasilkan `ToolResult(success=False)`, dan executor masih dapat menerima call berikutnya

  - [ ]* 16.3 Tulis unit tests untuk Executor
    - Uji eksekusi tool yang berhasil
    - Uji blocklist check mencegah eksekusi
    - Uji tool destruktif selalu memanggil `ConfirmationGate`
    - _Requirements: 9.8, 10.1, 10.7_

- [x] 17. Implementasi Agent Orchestrator
  - [x] 17.1 Buat `agent/core/orchestrator.py`
    - Implementasikan dataclass `InteractionRecord` dengan field `instruction`, `response`, `tool_calls`, `timestamp`
    - Implementasikan kelas `Agent` dengan dependensi `ModelManager`, `Executor`, `ConfirmationGate`, `AuditLogger`, `Blocklist`
    - Method `process(instruction)`: proses instruksi → rencanakan → eksekusi tools → sintesis → stream respons; log setiap tindakan ke `AuditLogger`
    - Method `stop()`: hentikan semua operasi dalam ≤3 detik
    - Method `get_history()`: kembalikan riwayat interaksi sesi aktif berurutan (terlama ke terbaru)
    - Method `_execute_plan(plan)`: eksekusi setiap tool call secara berurutan; berhenti dan minta konfirmasi setelah 10 tindakan berurutan tanpa input pengguna
    - _Requirements: 1.2, 1.7, 1.9, 10.3, 10.9_

  - [ ]* 17.2 Tulis property test untuk Agent Orchestrator — Property 2: Riwayat Sesi Lengkap dan Berurutan
    - **Property 2: Riwayat Sesi Lengkap dan Berurutan**
    - **Validates: Requirements 1.9**
    - Gunakan `@given(n=st.integers(min_value=1, max_value=50))` untuk menghasilkan N instruksi
    - Verifikasi bahwa `/history` mengembalikan tepat N pasangan instruksi-respons dalam urutan yang sama

  - [ ]* 17.3 Tulis property test untuk Agent Orchestrator — Property 3: Confirmation Gate Selalu Dipanggil untuk Operasi Berisiko Tinggi
    - **Property 3: Confirmation Gate Selalu Dipanggil untuk Operasi Berisiko Tinggi**
    - **Validates: Requirements 2.4, 3.4, 5.4, 8.2, 10.1**
    - Gunakan `@given(op=st.sampled_from(["delete_file", "dml_query", "destructive_shell", "apply_change"]))` dengan `@settings(max_examples=100)`
    - Verifikasi bahwa `ConfirmationGate.request()` selalu dipanggil sebelum eksekusi operasi berisiko tinggi

  - [ ]* 17.4 Tulis unit tests untuk Agent Orchestrator
    - Uji `stop()` menghentikan semua operasi dalam ≤3 detik
    - Uji batas 10 tindakan berurutan memicu konfirmasi
    - Uji `get_history()` mengembalikan pasangan yang benar
    - _Requirements: 1.7, 1.9, 10.3, 10.9_

- [x] 18. Implementasi Self-Improvement Module dan Backup Manager
  - [x] 18.1 Buat `agent/self_improvement/backup_manager.py`
    - Implementasikan kelas `BackupManager` dengan direktori backup yang dikonfigurasi
    - Method `create_backup(config)`: buat backup dengan timestamp, kembalikan path; pangkas ke 10 versi terbaru
    - Method `get_latest()`: kembalikan backup terakhir atau `None`
    - Method `list_backups()`: kembalikan semua backup diurutkan terbaru, maks 10
    - _Requirements: 8.7, 8.8_

  - [ ]* 18.2 Tulis property test untuk BackupManager — Property 9: Backup Tidak Melebihi Sepuluh Versi
    - **Property 9: Backup Tidak Melebihi Sepuluh Versi**
    - **Validates: Requirements 8.7**
    - Gunakan `@given(n_changes=st.integers(min_value=1, max_value=25))` dengan `@settings(max_examples=100)`
    - Verifikasi bahwa `len(list_backups()) == min(n_changes, 10)` selalu berlaku

  - [x] 18.3 Buat `agent/self_improvement/module.py`
    - Implementasikan kelas `SelfImprovementModule` dengan dependensi `config_path`, `ToolRegistry`, `ConfirmationGate`, `BackupManager`
    - Method `read_config()`: baca konfigurasi Agent yang aktif dari `config.toml`
    - Method `propose_change(instruction)`: analisis instruksi dan hasilkan `ConfigProposal` dengan diff
    - Method `apply_change(proposal)`: buat backup → tampilkan diff via `ConfirmationGate` → terapkan; rollback otomatis jika gagal dalam 30 detik
    - Method `download_plugin(url, name)`: unduh plugin (≤500 MB), validasi skema via `ToolRegistry`, daftarkan
    - Method `rollback()`: pulihkan ke versi backup terakhir dalam ≤30 detik
    - Validasi parameter model: `temperature` (0.0–2.0), `context_length` (128–131072)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9_

  - [ ]* 18.4 Tulis unit tests untuk SelfImprovementModule
    - Uji `apply_change()` dengan konfirmasi "y" menerapkan perubahan
    - Uji `apply_change()` dengan konfirmasi "n" tidak mengubah konfigurasi
    - Uji rollback otomatis saat `apply_change()` gagal
    - Uji `download_plugin()` menolak plugin dengan skema tidak valid
    - Uji batas ukuran plugin 500 MB
    - _Requirements: 8.2, 8.4, 8.7, 8.8, 8.9_

- [x] 19. Implementasi Checkpoint 3
  - Pastikan semua tests untuk ModelManager, Executor, Agent Orchestrator, Self-Improvement Module, dan BackupManager lulus
  - Verifikasi integrasi antar komponen inti berjalan tanpa error
  - Tanyakan kepada pengguna jika ada pertanyaan sebelum melanjutkan ke lapisan CLI.

- [x] 20. Implementasi CLI
  - [x] 20.1 Buat `agent/cli/interface.py`
    - Implementasikan dataclass `CLIConfig` dengan field `model` (dari flag `--model`) dan `history_limit`
    - Implementasikan kelas `CLI` menggunakan `rich.console.Console` untuk rendering
    - Method `run()`: loop utama REPL — baca input (≤32.000 karakter), kirim ke Agent, render output
    - Method `handle_command(text)`: tangani built-in commands `/help`, `/stop`, `/history`, `/model`, `/tools`; kembalikan `True` jika teks adalah command
    - Method `render_stream(token_stream)`: render token stream dengan syntax highlighting via Rich
    - Method `show_history(session_history)`: tampilkan semua pasangan instruksi-respons berurutan
    - Method `show_spinner(active)`: tampilkan/matikan indikator status yang diperbarui setiap 200ms
    - Method `validate_input_length(text)`: kembalikan `True` jika `len(text) ≤ 32.000`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11_

  - [ ]* 20.2 Tulis property test untuk CLI — Property 1: Batas Panjang Input CLI
    - **Property 1: Batas Panjang Input CLI**
    - **Validates: Requirements 1.1**
    - Gunakan `@given(text=st.text(min_size=0, max_size=40000))` dengan `@settings(max_examples=200)`
    - Verifikasi bahwa `validate_input_length(text)` mengembalikan `True` jika dan hanya jika `len(text) ≤ 32.000`

  - [ ]* 20.3 Tulis unit tests untuk CLI
    - Uji `validate_input_length` pada boundary (32000 → True, 32001 → False)
    - Uji `/help` menampilkan daftar commands dalam satu layar
    - Uji `/stop` saat idle mengakhiri sesi tanpa pesan error
    - Uji syntax highlighting untuk blok kode dengan dan tanpa penanda bahasa
    - Uji flag `--model` menggunakan model yang ditentukan; tanpa flag menggunakan default dan menampilkan nama model
    - _Requirements: 1.1, 1.5, 1.6, 1.8, 1.10, 1.11_

- [x] 21. Buat entrypoint dan wiring komponen
  - [x] 21.1 Buat `agent/__main__.py` dan `agent/main.py`
    - Parse argumen CLI dengan `argparse`: flag `--model <nama-model>`, `--config <path>`, `--blocklist <path>`
    - Inisialisasi semua komponen dalam urutan yang benar: `CredentialVault` → `AuditLogger` → `Blocklist` → `ToolRegistry` → `ConfirmationGate` → semua built-in tools (daftarkan ke registry) → `ModelManager` → `Executor` → `SelfImprovementModule` → `Agent` → `CLI`
    - Handle Ctrl+C (SIGINT) untuk memanggil `Agent.stop()` dan mengakhiri sesi
    - Tampilkan nama model aktif saat startup
    - _Requirements: 1.4, 1.5, 1.7, 7.6_

  - [ ]* 21.2 Tulis smoke test untuk operasi offline
    - Verifikasi agent dapat diinisialisasi dan berjalan dengan model GGUF lokal tanpa koneksi internet
    - Verifikasi tidak ada outbound network traffic ke server eksternal selama operasi normal
    - _Requirements: 7.8, 10.10_

- [x] 22. Implementasi Checkpoint Akhir — Integrasi dan Verifikasi
  - Jalankan seluruh suite tests: `pytest tests/unit/ tests/property/ -v`
  - Pastikan semua property tests (Property 1–10) lulus dengan minimum 100 iterasi per properti
  - Verifikasi semua komponen terhubung dengan benar melalui wiring di `main.py`
  - Pastikan semua tests lulus, tanyakan kepada pengguna jika ada pertanyaan.

---

## Notes

- Tugas yang ditandai dengan `*` bersifat opsional dan dapat dilewati untuk MVP yang lebih cepat
- Setiap tugas mereferensikan requirements spesifik untuk keterlacakan
- Checkpoint memastikan validasi bertahap sebelum melanjutkan ke lapisan berikutnya
- Property tests memvalidasi properti kebenaran universal; unit tests memvalidasi contoh spesifik dan edge case
- Semua komponen diimplementasikan sebagai modul Python terpisah dengan antarmuka yang terdefinisi untuk mendukung pengujian independen

---

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["2.1", "2.2"] },
    { "id": 1, "tasks": ["3.1", "4.1", "5.1", "6.1", "7.1"] },
    { "id": 2, "tasks": ["3.2", "4.2", "5.2", "6.2", "7.2"] },
    { "id": 3, "tasks": ["9.1", "10.1", "11.1", "12.1", "13.1"] },
    { "id": 4, "tasks": ["9.2", "9.3", "9.4", "10.2", "10.3", "11.2", "11.3", "11.4", "12.2", "13.2"] },
    { "id": 5, "tasks": ["15.1"] },
    { "id": 6, "tasks": ["15.2", "16.1"] },
    { "id": 7, "tasks": ["16.2", "16.3", "17.1"] },
    { "id": 8, "tasks": ["17.2", "17.3", "17.4", "18.1"] },
    { "id": 9, "tasks": ["18.2", "18.3"] },
    { "id": 10, "tasks": ["18.4", "20.1"] },
    { "id": 11, "tasks": ["20.2", "20.3", "21.1"] },
    { "id": 12, "tasks": ["21.2"] }
  ]
}
```
