# Skill: Git Workflow

> Panduan standar untuk alur kerja Git: status, commit, diff, branch, dan push yang aman.

**Triggers**: git, commit, push, branch, diff, pull, status repo

## Panduan & Petunjuk Langkah:
1. Periksa status repositori saat ini menggunakan `{"tool": "git", "params": {"operation": "status"}}` atau `{"tool": "shell", "params": {"command": "git status"}}`.
2. Jika ada perubahan yang perlu ditinjau, gunakan diff untuk memastikan hanya file yang relevan yang diubah.
3. Tambahkan file yang ingin di-commit dan buat pesan commit yang deskriptif dan mengikuti konvensi (misal: `feat: ...`, `fix: ...`, `refactor: ...`).
4. Jalankan pengujian atau verifikasi sebelum melakukan push ke remote branch `origin`.

## Contoh Penggunaan:
- cek status git dan commit perubahan terakhir
- push perubahan kode ke branch main
