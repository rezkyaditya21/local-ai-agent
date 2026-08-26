# Requirements Document

## Introduction

Terminal AI Model adalah sebuah aplikasi berbasis antarmuka baris perintah (CLI) yang memungkinkan pengguna menjalankan model bahasa besar (LLM) secara lokal langsung dari terminal. Aplikasi ini memanfaatkan model berukuran sekitar 5GB dalam format terquantisasi (misalnya GGUF) untuk memberikan kemampuan inferensi AI yang berkualitas tinggi tanpa memerlukan koneksi internet atau layanan cloud. Pengguna dapat berinteraksi dengan model melalui sesi percakapan interaktif maupun melalui perintah satu baris (one-shot query), dengan kontrol penuh atas parameter inferensi dan penggunaan sumber daya.

---

## Glossary

- **CLI**: Command-Line Interface — antarmuka berbasis teks untuk berinteraksi dengan aplikasi melalui terminal.
- **LLM**: Large Language Model — model kecerdasan buatan berbasis Transformer yang dilatih pada data teks dalam jumlah besar.
- **Model Terquantisasi**: Model LLM yang bobotnya dikompresi dari presisi penuh (FP32/FP16) ke presisi lebih rendah (INT4, INT8, dll.) untuk mengurangi ukuran dan kebutuhan memori tanpa kehilangan kualitas yang signifikan.
- **GGUF**: Format file model yang digunakan oleh runtime llama.cpp; mendukung quantisasi berbagai level dan portabilitas lintas platform.
- **ONNX**: Open Neural Network Exchange — format model standar lintas framework AI.
- **llama.cpp**: Runtime inferensi LLM berbasis C++ yang efisien dan mendukung format GGUF.
- **Inferensi**: Proses menghasilkan output dari model AI berdasarkan input yang diberikan.
- **Konteks (Context Window)**: Jumlah token maksimum yang dapat diproses model dalam satu sesi inferensi.
- **Token**: Unit terkecil teks yang diproses oleh LLM.
- **VRAM**: Video RAM — memori pada GPU yang digunakan untuk inferensi berbantuan GPU.
- **RAM**: Random Access Memory — memori sistem yang digunakan untuk inferensi berbasis CPU.
- **Sesi Percakapan**: Mode interaktif di mana pengguna dan model saling bertukar pesan secara berulang dalam satu sesi.
- **One-Shot Query**: Mode di mana pengguna mengirimkan satu pertanyaan dan menerima satu jawaban, lalu sesi berakhir.
- **System Prompt**: Instruksi awal yang diberikan kepada model untuk mendefinisikan persona, konteks, atau batasan perilakunya.
- **Runtime**: Komponen perangkat lunak yang mengeksekusi inferensi model (contoh: llama.cpp, ollama).
- **Model_Loader**: Komponen yang bertanggung jawab memuat file model ke dalam memori.
- **CLI_Interface**: Komponen yang mengelola input/output pengguna di terminal.
- **Inference_Engine**: Komponen yang menjalankan proses inferensi terhadap input pengguna.
- **Config_Manager**: Komponen yang membaca dan mengelola konfigurasi aplikasi.
- **Session_Manager**: Komponen yang mengelola riwayat percakapan dalam satu sesi.

---

## Requirements

### Requirement 1: Instalasi dan Pengaturan Awal

**User Story:** Sebagai pengguna baru, saya ingin menginstal dan mengkonfigurasi aplikasi dengan mudah, sehingga saya dapat mulai menggunakan model AI lokal tanpa pengetahuan teknis yang mendalam.

#### Acceptance Criteria

1. THE CLI_Interface SHALL menyediakan perintah `install` yang mengunduh model default berukuran tidak lebih dari 5,5GB ke direktori konfigurasi pengguna.
2. WHEN perintah `install` dijalankan, THE CLI_Interface SHALL menampilkan progress bar dengan persentase unduhan, kecepatan transfer, dan estimasi waktu tersisa, diperbarui setiap 1 detik.
3. WHEN unduhan model selesai, THE CLI_Interface SHALL memverifikasi integritas file menggunakan checksum SHA-256 dalam 30 detik setelah unduhan selesai, dan menampilkan pesan konfirmasi keberhasilan beserta nilai checksum yang diverifikasi.
4. IF checksum verifikasi gagal, THEN THE CLI_Interface SHALL menghapus file yang rusak, menampilkan pesan error yang menyebutkan nilai checksum yang diterima dan nilai yang diharapkan, dan menginstruksikan pengguna untuk menjalankan ulang perintah `install`.
5. THE Config_Manager SHALL menyimpan konfigurasi default ke file `~/.config/terminal-ai/config.yaml` pada saat instalasi pertama.
6. WHEN direktori konfigurasi belum ada, THE Config_Manager SHALL membuat direktori `~/.config/terminal-ai/` beserta subdirektori `models/` secara otomatis.
7. THE CLI_Interface SHALL menyediakan perintah `terminal-ai --help` yang menampilkan daftar seluruh perintah dan flag yang tersedia beserta deskripsi singkatnya dalam tidak lebih dari 2 detik.
8. IF unduhan terputus sebelum selesai, THEN THE CLI_Interface SHALL mempertahankan file unduhan parsial di direktori sementara dan menampilkan pesan yang menginformasikan bahwa unduhan dapat dilanjutkan dengan menjalankan kembali perintah `install`.
9. IF perintah `install` dijalankan dan model default sudah terinstal dengan checksum yang valid, THEN THE CLI_Interface SHALL menampilkan pesan yang menginformasikan bahwa model sudah terinstal dan melewati proses unduhan tanpa mengunduh ulang.

---

### Requirement 2: Pemilihan dan Manajemen Model

**User Story:** Sebagai pengguna, saya ingin mengelola satu atau lebih model AI yang tersimpan secara lokal, sehingga saya dapat memilih model yang sesuai dengan kebutuhan dan kapasitas perangkat saya.

#### Acceptance Criteria

1. THE Model_Loader SHALL mendukung pemuatan file model dalam format GGUF dengan level quantisasi Q2_K, Q4_K_M, Q5_K_M, dan Q8_0.
2. WHERE format ONNX tersedia, THE Model_Loader SHALL mendukung pemuatan file model dalam format ONNX sebagai opsi alternatif.
3. THE CLI_Interface SHALL menyediakan perintah `terminal-ai models list` yang menampilkan daftar model yang terinstal beserta ukuran file dalam satuan megabyte (MB) atau gigabyte (GB) dengan dua desimal, format (GGUF atau ONNX), dan level quantisasi masing-masing; jika tidak ada model yang terdaftar, perintah SHALL menampilkan pesan yang menginformasikan bahwa daftar model masih kosong.
4. WHEN pengguna menjalankan perintah `terminal-ai models add <path>`, THE CLI_Interface SHALL memvalidasi bahwa file pada `<path>` ada, dapat dibaca, dan berformat GGUF atau ONNX; jika validasi berhasil, THE CLI_Interface SHALL mendaftarkan file tersebut ke dalam daftar model yang dikelola aplikasi dan menampilkan konfirmasi yang menyebutkan nama model dan path yang didaftarkan.
5. IF file pada `<path>` yang diberikan ke perintah `terminal-ai models add` tidak ditemukan, tidak dapat dibaca, atau memiliki format selain GGUF dan ONNX, THEN THE CLI_Interface SHALL menampilkan pesan error yang menyebutkan path yang diberikan dan alasan kegagalan, tanpa mengubah daftar model yang sudah ada.
6. WHEN pengguna menjalankan perintah `terminal-ai models remove <nama-model>`, THE CLI_Interface SHALL menampilkan prompt konfirmasi yang menyebutkan nama model yang akan dihapus dan menunggu input pengguna berupa "y" atau "n" sebelum melanjutkan; jika pengguna mengonfirmasi, THE CLI_Interface SHALL menghapus entri model dari daftar kelola dan menampilkan pesan yang mengonfirmasi penghapusan.
7. IF pengguna membatalkan perintah `terminal-ai models remove` pada prompt konfirmasi, THEN THE CLI_Interface SHALL membatalkan operasi tanpa mengubah daftar model dan menampilkan pesan yang menginformasikan bahwa penghapusan dibatalkan.
8. IF nama model yang diberikan ke perintah `terminal-ai models remove` tidak ditemukan dalam daftar model yang dikelola, THEN THE CLI_Interface SHALL menampilkan pesan error yang menyebutkan nama model yang dicari, tanpa mengubah daftar model yang sudah ada.
9. WHEN model yang diminta tidak ditemukan di direktori model, THE Model_Loader SHALL menampilkan pesan error yang menyebutkan nama model yang dicari dan path direktori yang diperiksa, serta menghentikan operasi yang memerlukan model tersebut tanpa mengubah state aplikasi yang sudah ada.
10. THE CLI_Interface SHALL menyediakan flag `--model <nama-model>` pada perintah `chat` dan `ask` untuk menentukan model yang digunakan; jika flag tidak diberikan, THE CLI_Interface SHALL menggunakan model default yang telah dikonfigurasi sebelumnya.
11. IF flag `--model <nama-model>` diberikan dengan nama model yang tidak terdaftar dalam daftar model yang dikelola, THEN THE CLI_Interface SHALL menampilkan pesan error yang menyebutkan nama model yang diberikan dan menghentikan eksekusi perintah `chat` atau `ask` tersebut.

---

### Requirement 3: Antarmuka Percakapan Interaktif (Chat Mode)

**User Story:** Sebagai pengguna, saya ingin berinteraksi dengan model AI dalam sesi percakapan multi-giliran, sehingga saya dapat mengajukan pertanyaan lanjutan dengan konteks yang terjaga.

#### Acceptance Criteria

1. WHEN perintah `terminal-ai chat` dijalankan, THE CLI_Interface SHALL memulai sesi percakapan interaktif dan menampilkan prompt input (`>`) yang menunggu input dari pengguna.
2. WHILE sesi percakapan aktif, THE Session_Manager SHALL mempertahankan riwayat pesan antara pengguna dan model dalam memori, dengan batas maksimum 10.000 pesan per sesi.
3. WHILE sesi percakapan aktif, THE Inference_Engine SHALL menyertakan seluruh riwayat percakapan dalam setiap permintaan inferensi, hingga batas context window model.
4. WHEN riwayat percakapan melebihi batas context window, THE Session_Manager SHALL menghapus pesan paling lama secara berurutan sebelum permintaan inferensi berikutnya dikirim, untuk menjaga total token dalam batas yang didukung model.
5. WHEN pengguna mengetik perintah `/exit` atau `/quit`, THE CLI_Interface SHALL mengakhiri sesi percakapan dan mengembalikan pengguna ke shell dalam waktu kurang dari 2 detik.
6. WHEN pengguna mengetik perintah `/clear`, THE Session_Manager SHALL menghapus seluruh riwayat percakapan pada sesi aktif dan menampilkan konfirmasi penghapusan.
7. WHEN pengguna mengetik perintah `/save <nama-file>`, THE Session_Manager SHALL menyimpan riwayat percakapan ke file JSON di direktori kerja saat ini; jika nama file tidak menyertakan ekstensi `.json`, THE Session_Manager SHALL menambahkan ekstensi `.json` secara otomatis.
8. IF file dengan nama yang diberikan pada perintah `/save` sudah ada, THEN THE Session_Manager SHALL menampilkan prompt konfirmasi yang meminta pengguna mengonfirmasi penimpaan file sebelum menyimpan.
9. WHILE sesi percakapan aktif, THE CLI_Interface SHALL menampilkan token output secara streaming sehingga token pertama respons muncul dalam waktu kurang dari 5 detik setelah input diterima.
10. IF operasi penyimpanan pada perintah `/save` gagal karena direktori tidak dapat ditulis atau kesalahan sistem, THEN THE Session_Manager SHALL menampilkan pesan error yang menyebutkan alasan kegagalan tanpa mengakhiri sesi percakapan.

---

### Requirement 4: Mode Query Satu Baris (One-Shot / Ask Mode)

**User Story:** Sebagai pengguna, saya ingin mengirimkan satu pertanyaan ke model AI dari terminal tanpa membuka sesi interaktif, sehingga saya dapat mengintegrasikan model ke dalam skrip atau alur kerja otomasi.

#### Acceptance Criteria

1. WHEN perintah `terminal-ai ask "<pertanyaan>"` dijalankan, THE CLI_Interface SHALL mengirimkan pertanyaan ke Inference_Engine, mencetak respons model ke stdout, mengakhiri proses dengan exit code 0.
2. WHEN perintah `terminal-ai ask` dijalankan dengan input dari pipe (stdin), THE CLI_Interface SHALL membaca teks dari stdin sebagai pertanyaan.
3. IF perintah `terminal-ai ask` dijalankan tanpa argumen pertanyaan dan tanpa input dari pipe, THEN THE CLI_Interface SHALL mencetak pesan error ke stderr yang menjelaskan cara penggunaan yang benar dan menghentikan eksekusi dengan exit code 1.
4. THE CLI_Interface SHALL menyediakan flag `--no-stream` untuk menonaktifkan streaming dan menampilkan seluruh respons setelah generasi selesai.
5. THE CLI_Interface SHALL menyediakan flag `--output-format <format>` dengan pilihan nilai `plain` (default) dan `json` untuk menentukan format output respons.
6. WHEN flag `--output-format json` digunakan, THE CLI_Interface SHALL menampilkan respons dalam struktur JSON dengan field `query` (string), `response` (string), `model` (string), dan `duration_ms` (integer non-negatif dalam satuan milidetik).
7. IF nilai flag `--output-format` bukan `plain` atau `json`, THEN THE CLI_Interface SHALL mencetak pesan error ke stderr yang menyebutkan nilai yang diberikan dan daftar nilai yang valid, serta menghentikan eksekusi dengan exit code 1.
8. IF proses inferensi gagal, THEN THE CLI_Interface SHALL mencetak pesan error ke stderr yang menyebutkan penyebab kegagalan dan menghentikan proses dengan exit code bukan nol.

---

### Requirement 5: Konfigurasi Parameter Inferensi

**User Story:** Sebagai pengguna tingkat lanjut, saya ingin mengkonfigurasi parameter inferensi model, sehingga saya dapat menyesuaikan perilaku, kualitas, dan kecepatan respons model sesuai kebutuhan.

#### Acceptance Criteria

1. THE CLI_Interface SHALL menyediakan flag `--temperature <nilai>` yang menerima nilai desimal antara 0.0 hingga 2.0 untuk mengontrol tingkat kreativitas respons model.
2. THE CLI_Interface SHALL menyediakan flag `--max-tokens <nilai>` yang menerima nilai integer antara 1 hingga 8192 untuk membatasi panjang respons yang dihasilkan.
3. THE CLI_Interface SHALL menyediakan flag `--context-size <nilai>` yang menerima nilai integer antara 512 hingga 131072 untuk menentukan ukuran context window dalam satuan token.
4. THE CLI_Interface SHALL menyediakan flag `--system-prompt <teks>` yang menerima teks string dengan panjang maksimum 4096 karakter untuk mendefinisikan system prompt yang dikirimkan ke model sebelum percakapan dimulai.
5. THE CLI_Interface SHALL menyediakan flag `--system-prompt-file <path>` yang menerima path ke file teks yang isinya digunakan sebagai system prompt.
6. IF nilai flag `--temperature` berada di luar rentang 0.0–2.0, THEN THE CLI_Interface SHALL menampilkan pesan error validasi dan menghentikan eksekusi dengan exit code 1.
7. IF nilai flag `--max-tokens` berada di luar rentang 1–8192, THEN THE CLI_Interface SHALL menampilkan pesan error validasi dan menghentikan eksekusi dengan exit code 1.
8. IF nilai flag `--context-size` berada di luar rentang 512–131072, THEN THE CLI_Interface SHALL menampilkan pesan error validasi yang menyebutkan nilai yang diterima dan rentang yang valid, dan menghentikan eksekusi dengan exit code 1.
9. IF file yang diacu oleh flag `--system-prompt-file` tidak ditemukan atau tidak dapat dibaca, THEN THE CLI_Interface SHALL menampilkan pesan error yang menyebutkan path file tersebut dan menghentikan eksekusi dengan exit code 1.
10. IF flag parameter inferensi tidak diberikan secara eksplisit, THEN THE Config_Manager SHALL membaca nilai default dari file `~/.config/terminal-ai/config.yaml`; jika file konfigurasi tidak ada, THE Config_Manager SHALL menggunakan nilai bawaan: temperature=0.7, max-tokens=2048, context-size=4096.

---

### Requirement 6: Manajemen Sumber Daya Komputasi

**User Story:** Sebagai pengguna, saya ingin aplikasi mengelola penggunaan CPU, RAM, dan GPU secara efisien, sehingga sistem tetap responsif selama inferensi berjalan.

#### Acceptance Criteria

1. THE Inference_Engine SHALL menggunakan tidak lebih dari 90% kapasitas RAM sistem yang terdeteksi saat proses pemuatan model dimulai dan selama inferensi berlangsung, diukur sebagai persentase dari total RAM fisik yang dilaporkan oleh sistem operasi.
2. WHEN GPU tersedia dan driver CUDA atau Metal terpasang, THE Inference_Engine SHALL memindahkan layer model ke VRAM secara otomatis untuk mempercepat inferensi.
3. THE CLI_Interface SHALL menyediakan flag `--cpu-only` yang memaksa Inference_Engine menggunakan CPU meskipun GPU tersedia.
4. THE CLI_Interface SHALL menyediakan flag `--gpu-layers <nilai>` yang menerima nilai integer antara 0 hingga jumlah total layer model untuk menentukan jumlah layer model yang dimuat ke VRAM.
5. IF nilai flag `--gpu-layers` kurang dari 0 atau melebihi jumlah total layer model, THEN THE CLI_Interface SHALL menampilkan pesan error yang menyebutkan nilai yang diterima, rentang nilai yang valid, dan menghentikan eksekusi dengan exit code 1.
6. WHEN RAM yang tersedia kurang dari 2GB sebelum pemuatan model dimulai, THE Model_Loader SHALL menampilkan pesan peringatan yang menyebutkan jumlah RAM tersedia dalam satuan MB dan RAM yang diperkirakan dibutuhkan oleh model dalam satuan MB, lalu melanjutkan proses pemuatan.
7. THE CLI_Interface SHALL menyediakan flag `--threads <nilai>` yang menerima nilai integer antara 1 hingga jumlah core CPU yang tersedia untuk menentukan jumlah thread inferensi.
8. IF nilai flag `--threads` melebihi jumlah core CPU yang tersedia pada sistem, THEN THE CLI_Interface SHALL menampilkan pesan peringatan yang menyebutkan nilai yang diberikan dan jumlah core yang tersedia, dan menggunakan nilai jumlah core yang tersedia secara otomatis.

---

### Requirement 7: Kecepatan dan Latensi Inferensi

**User Story:** Sebagai pengguna, saya ingin respons model dihasilkan dalam waktu yang wajar, sehingga interaksi terasa responsif dan produktif.

#### Acceptance Criteria

1. WHEN inferensi dijalankan pada perangkat dengan RAM minimal 16GB dan CPU 8-core, THE Inference_Engine SHALL menghasilkan token pertama dalam waktu kurang dari 5 detik setelah input diterima, diukur dari saat input dikirim hingga karakter pertama respons ditampilkan.
2. WHILE inferensi berlangsung pada perangkat dengan RAM minimal 16GB dan CPU 8-core, THE Inference_Engine SHALL menghasilkan token dengan kecepatan minimal 5 token per detik, diukur sebagai rata-rata seluruh token yang dihasilkan dalam satu respons.
3. WHEN model selesai dimuat ke memori, THE Model_Loader SHALL mencetak pesan yang menyebutkan waktu pemuatan dalam satuan detik dengan presisi dua angka desimal.
4. WHEN respons selesai dihasilkan dan flag `--verbose` aktif, THE CLI_Interface SHALL mencetak ringkasan statistik inferensi yang mencakup jumlah token yang dihasilkan, kecepatan rata-rata token per detik, dan total durasi dalam milidetik.
5. IF inferensi tidak menghasilkan token pertama dalam 30 detik setelah input diterima, THEN THE Inference_Engine SHALL menghentikan proses inferensi dan menampilkan pesan error yang menyebutkan durasi timeout, serta mengembalikan exit code 1.

---

### Requirement 8: Kompatibilitas Platform

**User Story:** Sebagai pengguna di berbagai sistem operasi, saya ingin aplikasi berjalan secara konsisten, sehingga saya tidak perlu mengganti alur kerja saya berdasarkan platform yang digunakan.

#### Acceptance Criteria

1. THE CLI_Interface SHALL berjalan pada sistem operasi Linux (kernel 4.15 ke atas), macOS (versi 12 ke atas), dan Windows (versi 10 ke atas dengan WSL2 atau PowerShell).
2. THE CLI_Interface SHALL menyediakan binary yang telah dikompilasi untuk arsitektur CPU x86_64 dan ARM64.
3. WHERE sistem operasi adalah macOS dengan chip Apple Silicon, THE Inference_Engine SHALL memanfaatkan akselerasi Metal Performance Shaders (MPS) secara otomatis.
4. THE CLI_Interface SHALL dapat diinstal melalui manajer paket: `brew` untuk macOS, `apt`/`dnf` untuk Linux, dan binary installer untuk Windows.
5. IF platform yang terdeteksi tidak memenuhi persyaratan sistem operasi atau arsitektur CPU yang didukung, THEN THE CLI_Interface SHALL menampilkan pesan error yang menyebutkan platform yang terdeteksi dan daftar platform yang didukung, serta menghentikan eksekusi dengan exit code 1.

---

### Requirement 9: Pemrosesan Input Kontekstual

**User Story:** Sebagai pengguna, saya ingin memberikan konteks tambahan kepada model dalam bentuk file teks, sehingga model dapat menjawab pertanyaan berdasarkan dokumen yang saya berikan.

#### Acceptance Criteria

1. THE CLI_Interface SHALL menyediakan flag `--context-file <path>` yang menerima path ke file teks dengan ekstensi `.txt`, `.md`, atau `.json` dan ukuran file tidak melebihi 10MB untuk disertakan sebagai konteks tambahan dalam permintaan inferensi.
2. WHEN flag `--context-file` diberikan, THE Inference_Engine SHALL menyisipkan seluruh konten file ke dalam system prompt sebelum pertanyaan pengguna diproses.
3. IF file yang diacu oleh flag `--context-file` tidak ditemukan atau tidak dapat dibaca, THEN THE CLI_Interface SHALL menampilkan pesan error yang menyebutkan path file tersebut dan menghentikan eksekusi dengan exit code 1.
4. IF ekstensi file yang diberikan melalui flag `--context-file` bukan `.txt`, `.md`, atau `.json`, THEN THE CLI_Interface SHALL menampilkan pesan error yang menyebutkan ekstensi yang diterima dan daftar ekstensi yang didukung, serta menghentikan eksekusi dengan exit code 1.
5. IF ukuran konten file konteks melebihi 50% dari context window model, THEN THE CLI_Interface SHALL menampilkan pesan peringatan yang menyebutkan ukuran konten dalam satuan token dan batas 50% context window dalam satuan token, dan memotong konten secara otomatis dari akhir teks sebelum inferensi dilanjutkan.

---

### Requirement 10: Keamanan dan Privasi Data

**User Story:** Sebagai pengguna, saya ingin memastikan bahwa data percakapan saya tidak dikirimkan ke server eksternal manapun, sehingga privasi informasi sensitif saya terjaga.

#### Acceptance Criteria

1. THE Inference_Engine SHALL menjalankan seluruh proses inferensi secara lokal pada perangkat pengguna tanpa membuat koneksi jaringan keluar (outbound network connection) selama sesi aktif.
2. THE CLI_Interface SHALL menyediakan perintah `terminal-ai privacy status` yang menampilkan konfirmasi bahwa tidak ada data yang dikirimkan ke server eksternal, disertai daftar komponen aktif yang diverifikasi tidak melakukan koneksi keluar.
3. IF aplikasi mendeteksi upaya koneksi jaringan keluar yang tidak terduga selama inferensi, THEN THE Inference_Engine SHALL menghentikan proses inferensi, menampilkan pesan peringatan yang menyebutkan komponen yang memicu koneksi dan waktu kejadian, serta mencatat insiden ke file log dengan nama file berformat `security-YYYY-MM-DD.log`.
4. THE Config_Manager SHALL menyimpan riwayat percakapan hanya apabila pengguna secara eksplisit menjalankan perintah `/save`, dan tidak menyimpan riwayat secara otomatis tanpa perintah pengguna.
5. WHEN perintah `/save` dijalankan, THE Config_Manager SHALL menyimpan riwayat percakapan ke penyimpanan lokal pada perangkat pengguna dan menampilkan konfirmasi yang menyebutkan path file tujuan penyimpanan.
```
