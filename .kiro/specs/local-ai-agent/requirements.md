# Requirements Document

## Introduction

Local AI Agent adalah sebuah sistem agen kecerdasan buatan yang berjalan sepenuhnya di mesin lokal pengguna melalui antarmuka terminal. Agen ini memiliki akses penuh ke sumber daya komputer pengguna — termasuk file system, shell, browser, database lokal, dan API eksternal — sehingga mampu menyelesaikan tugas kompleks secara otonom. Sistem ini dirancang secara modular agar model AI yang digunakan dapat dimulai dari skala kecil, diperbarui secara bertahap, dan bahkan mampu memodifikasi konfigurasi serta komponen dirinya sendiri (self-improvement) di bawah pengawasan dan persetujuan pengguna.

---

## Glossary

- **Agent**: Sistem perangkat lunak utama yang menerima instruksi pengguna, merencanakan tindakan, dan mengeksekusi tool untuk menyelesaikan tugas.
- **CLI (Command-Line Interface)**: Antarmuka berbasis teks di terminal yang digunakan pengguna untuk berinteraksi dengan Agent.
- **Tool**: Unit fungsionalitas modular yang dapat dipanggil oleh Agent untuk melakukan operasi spesifik (mis. membaca file, menjalankan shell command).
- **Plugin**: Paket Tool tambahan yang dapat dipasang atau dilepas tanpa mengubah inti sistem Agent.
- **Model**: Komponen AI language model yang digunakan Agent untuk memproses instruksi dan menghasilkan respons atau rencana tindakan.
- **Model_Manager**: Subsistem yang bertanggung jawab mengelola pemilihan, pemuatan, dan penggantian Model.
- **Tool_Registry**: Subsistem yang menyimpan daftar semua Tool dan Plugin yang tersedia bagi Agent.
- **Session**: Satu sesi interaksi aktif antara pengguna dan Agent dari awal hingga pengguna mengakhirinya.
- **Executor**: Subsistem yang menjalankan instruksi tool yang diberikan oleh Agent.
- **Self_Improvement_Module**: Subsistem yang mengelola proses modifikasi diri Agent, termasuk pembaruan konfigurasi, kode, dan model.
- **Sandbox**: Lingkungan terisolasi opsional untuk menjalankan operasi berisiko tinggi.
- **Confirmation_Gate**: Mekanisme yang meminta konfirmasi eksplisit dari pengguna sebelum tindakan destruktif atau berisiko tinggi dieksekusi.

---

## Requirements

### Requirement 1: Antarmuka CLI

**User Story:** Sebagai pengguna, saya ingin berinteraksi dengan AI Agent melalui terminal, agar saya dapat memberikan instruksi dalam bahasa alami dan melihat hasilnya secara langsung.

#### Acceptance Criteria

1. THE CLI SHALL menyediakan prompt interaktif yang menerima masukan teks bebas hingga 32.000 karakter per instruksi dari pengguna.
2. WHEN pengguna mengirimkan instruksi, THE CLI SHALL meneruskan instruksi tersebut ke Agent dan menampilkan setiap baris respons serta log tindakan dalam waktu tidak lebih dari 500ms setelah token tersedia.
3. WHEN Agent sedang memproses tugas, THE CLI SHALL menampilkan indikator status aktif yang diperbarui setiap 200ms hingga Agent menyelesaikan atau menghentikan pemrosesan.
4. THE CLI SHALL mendukung flag `--model <nama-model>` saat startup untuk menentukan Model yang akan digunakan pada Session tersebut.
5. IF flag `--model` tidak disertakan saat startup, THEN THE CLI SHALL menggunakan Model default yang telah dikonfigurasi dan menampilkan nama Model yang aktif kepada pengguna.
6. WHEN pengguna mengetikkan perintah `/help`, THE CLI SHALL menampilkan daftar semua perintah bawaan beserta deskripsi singkatnya dalam satu layar output.
7. WHEN pengguna mengetikkan perintah `/stop` atau menekan Ctrl+C, THE CLI SHALL menghentikan semua operasi Agent yang sedang berjalan, menampilkan konfirmasi penghentian, dan mengakhiri Session dalam waktu tidak lebih dari 3 detik.
8. IF perintah `/stop` atau Ctrl+C diterima saat tidak ada operasi Agent yang berjalan, THEN THE CLI SHALL mengakhiri Session tanpa menampilkan pesan error.
9. WHEN pengguna mengetikkan perintah `/history`, THE CLI SHALL menampilkan seluruh pasangan instruksi dan respons pada Session yang sedang aktif secara berurutan dari yang terlama hingga terbaru.
10. IF Agent menghasilkan output yang mengandung blok kode dengan penanda bahasa yang dikenali, THEN THE CLI SHALL menampilkan blok kode tersebut dengan syntax highlighting sesuai bahasa yang ditentukan.
11. IF Agent menghasilkan output yang mengandung blok kode tanpa penanda bahasa, THEN THE CLI SHALL menampilkan blok kode tersebut dengan format teks biasa yang dibedakan secara visual dari teks narasi.

---

### Requirement 2: Akses File System

**User Story:** Sebagai pengguna, saya ingin Agent dapat membaca, menulis, menghapus, dan memindahkan file serta folder, agar Agent dapat menyelesaikan tugas yang melibatkan manipulasi berkas secara otonom.

#### Acceptance Criteria

1. THE Agent SHALL mampu membaca konten file teks dan biner dari path yang diberikan di file system lokal, dengan ukuran file maksimum 500 MB per operasi baca.
2. THE Agent SHALL mampu menulis atau menimpa konten file pada path yang diberikan.
3. THE Agent SHALL mampu membuat file dan direktori baru.
4. WHEN Agent akan menghapus file atau direktori, THE Confirmation_Gate SHALL menampilkan path lengkap yang akan dihapus dan meminta konfirmasi berupa input "y" atau "n" dari pengguna sebelum eksekusi dilakukan.
5. THE Agent SHALL mampu memindahkan atau mengganti nama file dan direktori.
6. IF path tujuan pada operasi pindah atau ganti nama sudah ada, THEN THE Agent SHALL menampilkan pesan error yang menyebutkan path tujuan yang konflik dan menghentikan operasi tanpa mengubah file apapun.
7. THE Agent SHALL mampu membaca daftar isi suatu direktori beserta metadata file (ukuran dalam byte, tanggal modifikasi dalam format ISO 8601, tipe: file atau direktori).
8. THE Agent SHALL mampu mencari file berdasarkan nama atau pola glob di dalam direktori yang ditentukan; jika tidak ada hasil yang ditemukan, THE Agent SHALL mengembalikan daftar kosong beserta pesan yang menginformasikan bahwa tidak ada hasil yang cocok.
9. IF operasi file system gagal, THEN THE Agent SHALL mengembalikan pesan error yang menyebutkan jenis kegagalan (izin ditolak, path tidak ditemukan, dll.) dan path yang terlibat, kemudian menghentikan operasi terkait tanpa mengakhiri Session.

---

### Requirement 3: Akses Shell dan Terminal

**User Story:** Sebagai pengguna, saya ingin Agent dapat menjalankan perintah shell dan skrip, agar Agent dapat mengotomasi tugas sistem operasi secara langsung.

#### Acceptance Criteria

1. THE Agent SHALL mampu menjalankan perintah shell arbitrer dan menangkap output standar (stdout) serta error standar (stderr) secara terpisah.
2. WHEN perintah shell berhasil dieksekusi, THE Agent SHALL mengembalikan kode keluar (exit code), stdout, dan stderr kepada Agent untuk diproses lebih lanjut.
3. THE Agent SHALL mampu menjalankan skrip (bash, PowerShell, Python, dll.) dengan menyebutkan interpreter dan path skrip.
4. IF Agent akan menjalankan perintah yang termasuk dalam daftar perintah destruktif (antara lain: `rm -rf`, `rmdir /s`, `format`, `shutdown`, `del /f /s`, `mkfs`, `dd if=`), THEN THE Confirmation_Gate SHALL menampilkan perintah lengkap dan meminta konfirmasi berupa input "y" atau "n" dari pengguna.
5. THE Agent SHALL mampu menjalankan proses di latar belakang dan memantau status prosesnya (running, stopped, exit code).
6. WHEN proses latar belakang menghasilkan output baru, THE CLI SHALL menampilkan output tersebut dalam waktu tidak lebih dari 1 detik setelah output tersedia.
7. IF perintah shell melebihi batas waktu eksekusi default 30 detik yang dapat dikonfigurasi pengguna, THEN THE Agent SHALL menghentikan proses tersebut dan mengembalikan pesan yang menyebutkan perintah yang timeout dan durasi batas waktu yang dikonfigurasi.

---

### Requirement 4: Akses Browser

**User Story:** Sebagai pengguna, saya ingin Agent dapat membuka URL, melakukan web scraping, dan berinteraksi dengan halaman web, agar Agent dapat mengambil informasi dari internet dan mengotomasi tugas berbasis web.

#### Acceptance Criteria

1. WHEN Agent membuka URL yang valid, THE Agent SHALL mengambil konten HTML halaman tersebut dan mengembalikannya sebagai string UTF-8.
2. THE Agent SHALL mampu mengekstrak teks, tautan, dan data terstruktur dari konten HTML yang diambil.
3. WHEN Agent mengisi formulir web atau mengklik elemen pada halaman, THE Agent SHALL menggunakan browser yang dapat dikontrol secara programatik (headless browser) untuk melakukan interaksi tersebut.
4. WHEN Agent menangkap screenshot halaman web, THE Agent SHALL menyimpan hasilnya sebagai file PNG dan mengembalikan path file tersebut.
5. IF permintaan ke URL gagal atau tidak mendapat respons dalam 30 detik, THEN THE Agent SHALL mengembalikan pesan error deskriptif beserta kode status HTTP (jika tersedia) atau jenis kegagalan koneksi.
6. WHILE Session berlangsung, THE Agent SHALL mampu menyimpan dan menggunakan cookies serta token sesi autentikasi browser untuk permintaan berikutnya ke domain yang sama.
7. WHERE fitur headless browser diaktifkan, THE Agent SHALL menjalankan browser tanpa antarmuka grafis agar kompatibel dengan lingkungan tanpa display.

---

### Requirement 5: Akses Database Lokal

**User Story:** Sebagai pengguna, saya ingin Agent dapat membaca dan menulis data ke database lokal, agar Agent dapat mengelola dan memproses data terstruktur yang tersimpan di mesin saya.

#### Acceptance Criteria

1. THE Agent SHALL mendukung koneksi ke database SQLite melalui path file database yang valid.
2. IF path file yang diberikan tidak ada atau bukan file SQLite yang valid, THEN THE Agent SHALL mengembalikan pesan error yang menyebutkan path yang diberikan dan jenis kegagalan, tanpa membuat file baru.
3. WHEN koneksi database berhasil dibuat, THE Agent SHALL mampu menjalankan query SQL SELECT dan mengembalikan hasilnya sebagai kumpulan baris dengan pemetaan nama kolom ke nilai, dengan batas maksimum 1.000 baris per query.
4. WHEN Agent akan menjalankan query yang memodifikasi data (INSERT, UPDATE, DELETE, DROP), THE Confirmation_Gate SHALL menampilkan query lengkap dan meminta konfirmasi berupa input "y" atau "n" dari pengguna sebelum dieksekusi.
5. WHEN koneksi database berhasil dibuat, THE Agent SHALL mampu mengambil schema database yang mencakup nama tabel dan untuk setiap tabel: nama kolom, tipe data, dan constraint (PRIMARY KEY, NOT NULL, UNIQUE).
6. IF query SQL gagal dieksekusi, THEN THE Agent SHALL mengembalikan pesan error dari database beserta query yang menyebabkan kegagalan tersebut, tanpa mengubah state database yang sudah ada.
7. WHERE dukungan database tambahan dikonfigurasi (mis. PostgreSQL, MySQL), THE Agent SHALL menggunakan string koneksi yang diberikan untuk terhubung ke database tersebut.

---

### Requirement 6: Akses API Eksternal

**User Story:** Sebagai pengguna, saya ingin Agent dapat melakukan HTTP request ke API eksternal, agar Agent dapat mengintegrasikan layanan pihak ketiga dan mengambil data dari internet.

#### Acceptance Criteria

1. WHEN Agent melakukan HTTP request, THE Agent SHALL mendukung method GET, POST, PUT, PATCH, dan DELETE ke URL yang ditentukan.
2. WHEN Agent menyiapkan HTTP request, THE Agent SHALL mampu menyertakan header HTTP kustom, parameter query, dan body request (JSON, form-data, atau teks) dengan ukuran body maksimum 10 MB per request.
3. WHEN respons API diterima, THE Agent SHALL mengembalikan kode status HTTP, header respons, dan body respons dengan ukuran maksimum 10 MB kepada Agent.
4. THE Agent SHALL menyimpan API key, token, dan kredensial lainnya dalam penyimpanan terenkripsi dan tidak pernah menampilkan nilai aslinya di output terminal atau file log.
5. IF HTTP request tidak mendapat respons dalam 30 detik atau gagal karena error jaringan, THEN THE Agent SHALL mengembalikan pesan error deskriptif beserta kode status HTTP (jika tersedia) atau jenis kegagalan.
6. THE Agent SHALL mengikuti redirect HTTP secara otomatis hingga maksimum 10 kali pengalihan.
7. IF jumlah redirect melebihi 10 kali, THEN THE Agent SHALL menghentikan request dan mengembalikan pesan error yang menyebutkan jumlah redirect yang terjadi dan URL terakhir yang dikunjungi.

---

### Requirement 7: Manajemen Model

**User Story:** Sebagai pengguna, saya ingin dapat memilih, mengganti, dan mengonfigurasi model AI yang digunakan Agent, agar saya dapat memulai dengan model kecil dan meningkatkan kapabilitas secara bertahap.

#### Acceptance Criteria

1. THE Model_Manager SHALL mendukung pemuatan model lokal dalam format GGUF melalui path file absolut atau relatif yang ditentukan, dengan ukuran file maksimum 100 GB.
2. THE Model_Manager SHALL mendukung koneksi ke model yang berjalan melalui endpoint API lokal (mis. Ollama, llama.cpp server) menggunakan URL yang terdiri dari maksimum 2048 karakter dan nama model yang dikonfigurasi.
3. WHEN pengguna menjalankan perintah `/model list`, THE Model_Manager SHALL menampilkan daftar semua model yang terdaftar dalam konfigurasi beserta ukuran file atau tipe koneksi dan status (aktif/tidak aktif) dalam waktu tidak lebih dari 2 detik.
4. WHEN pengguna menjalankan perintah `/model use <nama-model>`, THE Model_Manager SHALL mengganti Model yang aktif pada Session saat ini dalam waktu tidak lebih dari 30 detik tanpa perlu me-restart Agent.
5. IF nama model yang diberikan pada perintah `/model use <nama-model>` tidak ditemukan dalam daftar model yang terdaftar, THEN THE Model_Manager SHALL menampilkan pesan error yang mengindikasikan model tidak ditemukan dan mempertahankan Model aktif saat ini.
6. THE Model_Manager SHALL menyimpan konfigurasi model default di file konfigurasi sehingga model yang sama digunakan secara otomatis pada Session berikutnya.
7. IF model gagal dimuat atau endpoint tidak dapat dijangkau dalam waktu 10 detik, THEN THE Model_Manager SHALL menampilkan pesan error yang mengindikasikan penyebab kegagalan dan mempertahankan Model sebelumnya yang aktif.
8. THE Agent SHALL mampu beroperasi dengan model lokal tanpa memerlukan koneksi internet aktif.

---

### Requirement 8: Kemampuan Self-Improvement

**User Story:** Sebagai pengguna, saya ingin Agent dapat memodifikasi konfigurasi, komponen, dan kemampuannya sendiri, agar sistem dapat berkembang dan meningkat seiring waktu.

#### Acceptance Criteria

1. THE Self_Improvement_Module SHALL mampu membaca file konfigurasi Agent yang aktif dan mengusulkan perubahan berdasarkan instruksi eksplisit pengguna.
2. WHEN Self_Improvement_Module mengusulkan modifikasi pada konfigurasi atau kode Agent, THE Confirmation_Gate SHALL menampilkan diff perubahan yang diusulkan dan meminta persetujuan eksplisit dari pengguna sebelum diterapkan.
3. THE Self_Improvement_Module SHALL mampu mengunduh dan mendaftarkan Plugin baru ke Tool_Registry atas instruksi pengguna, dengan ukuran Plugin maksimum 500 MB per file.
4. IF Plugin yang diunduh tidak dapat diverifikasi kesesuaiannya dengan skema antarmuka Tool_Registry, THEN THE Self_Improvement_Module SHALL membatalkan pendaftaran Plugin tersebut dan menampilkan pesan error yang mengindikasikan ketidaksesuaian skema.
5. THE Self_Improvement_Module SHALL mampu memperbarui Parameter model dalam rentang nilai yang valid (temperature: 0.0–2.0, context length: 128–131072 token) dan menyimpannya ke konfigurasi permanen.
6. IF nilai Parameter model yang diberikan berada di luar rentang yang valid, THEN THE Self_Improvement_Module SHALL menolak perubahan dan menampilkan pesan error yang mengindikasikan nilai valid yang diizinkan.
7. WHEN Self_Improvement_Module menerapkan perubahan pada komponen inti Agent, THE Self_Improvement_Module SHALL membuat backup dari versi sebelumnya sebelum perubahan diterapkan, dengan retensi maksimum 10 versi backup terakhir.
8. WHEN pengguna menjalankan perintah `/rollback`, THE Self_Improvement_Module SHALL memulihkan konfigurasi dan komponen Agent ke versi backup terakhir dalam waktu tidak lebih dari 30 detik.
9. IF proses self-improvement gagal diterapkan, THEN THE Self_Improvement_Module SHALL membatalkan perubahan secara otomatis dan memulihkan ke versi sebelumnya tanpa intervensi pengguna dalam waktu tidak lebih dari 30 detik.

---

### Requirement 9: Sistem Tool dan Plugin Modular

**User Story:** Sebagai pengguna, saya ingin dapat menambah, menghapus, dan mengelola tool serta plugin Agent, agar saya dapat memperluas kemampuan Agent sesuai kebutuhan.

#### Acceptance Criteria

1. THE Tool_Registry SHALL menyimpan daftar semua Tool dan Plugin yang tersedia beserta skema input/output masing-masing, dengan kapasitas maksimum 200 Tool dan Plugin secara total.
2. THE Agent SHALL memilih Tool yang paling sesuai dari Tool_Registry berdasarkan kecocokan antara kebutuhan tugas yang sedang diproses dengan skema input/output yang terdaftar.
3. THE Tool_Registry SHALL mendukung pemuatan Plugin dari direktori lokal yang dikonfigurasi pengguna, dengan ukuran file Plugin maksimum 100 MB per file.
4. WHEN pengguna menjalankan perintah `/tools list`, THE Tool_Registry SHALL menampilkan semua Tool dan Plugin yang terdaftar beserta status aktif/nonaktifnya dalam waktu tidak lebih dari 2 detik.
5. WHEN pengguna menjalankan perintah `/tools enable <nama-tool>` atau `/tools disable <nama-tool>`, THE Tool_Registry SHALL mengaktifkan atau menonaktifkan Tool tersebut dalam waktu tidak lebih dari 2 detik tanpa me-restart Agent.
6. IF nama tool yang diberikan pada perintah `/tools enable` atau `/tools disable` tidak ditemukan dalam Tool_Registry, THEN THE Tool_Registry SHALL menampilkan pesan error yang mengindikasikan tool tidak ditemukan dan mempertahankan status Tool lainnya tanpa perubahan.
7. THE Tool_Registry SHALL memvalidasi bahwa setiap Plugin memenuhi skema antarmuka yang ditentukan sebelum Plugin tersebut didaftarkan, dan menolak pendaftaran Plugin yang tidak memenuhi skema dengan pesan error yang mengindikasikan field yang tidak sesuai.
8. IF Plugin mengalami error saat dieksekusi, THEN THE Executor SHALL menangkap error tersebut, mencatatnya ke file log, dan mengembalikan pesan error kepada Agent tanpa menghentikan Session.

---

### Requirement 10: Keamanan dan Kontrol Pengguna

**User Story:** Sebagai pengguna, saya ingin tetap memiliki kendali penuh atas semua tindakan Agent, agar saya dapat menghentikan, membatalkan, atau mengoverride setiap operasi kapan saja.

#### Acceptance Criteria

1. THE Confirmation_Gate SHALL meminta konfirmasi eksplisit dari pengguna sebelum Agent menjalankan operasi yang diklasifikasikan berisiko tinggi, yaitu: penghapusan file/direktori, modifikasi data database, eksekusi perintah destruktif, dan perubahan komponen Agent.
2. IF pengguna tidak memberikan konfirmasi dalam waktu 60 detik setelah Confirmation_Gate menampilkan permintaan, THEN THE Confirmation_Gate SHALL membatalkan operasi secara otomatis dan menginformasikan pengguna bahwa operasi dibatalkan karena tidak ada respons.
3. WHEN pengguna menekan Ctrl+C atau mengetikkan `/stop`, THE Agent SHALL menghentikan semua operasi yang sedang berjalan dalam waktu tidak lebih dari 3 detik.
4. THE Agent SHALL mencatat semua tindakan yang dieksekusi beserta timestamp berformat ISO 8601 ke dalam file log permanen yang dapat dibaca pengguna, dengan ukuran file log maksimum 100 MB sebelum dilakukan rotasi log.
5. THE Agent SHALL menyimpan API key, token, dan kredensial lainnya dalam file konfigurasi terenkripsi dan tidak pernah menampilkan nilai aslinya di output terminal.
6. WHERE fitur Sandbox dikonfigurasi, THE Executor SHALL menjalankan perintah shell dan skrip di dalam lingkungan terisolasi untuk membatasi dampak ke sistem host.
7. THE Agent SHALL mendukung file daftar larangan (blocklist) berisi path file, perintah, atau domain yang tidak boleh diakses Agent.
8. WHEN Agent mencoba mengakses entri yang terdaftar dalam blocklist, THE Agent SHALL menolak operasi tersebut dan menampilkan pesan yang mengindikasikan operasi ditolak karena entri terdapat dalam blocklist.
9. WHEN Agent mengeksekusi lebih dari 10 tindakan berurutan tanpa input pengguna, THE Agent SHALL berhenti dan meminta konfirmasi pengguna untuk melanjutkan.
10. THE Agent SHALL berjalan sepenuhnya secara lokal dan tidak mengirimkan data pengguna, isi file, atau riwayat percakapan ke server eksternal tanpa izin eksplisit dari pengguna.
