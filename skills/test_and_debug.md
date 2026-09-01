# Skill: Test and Debug

> Panduan otomatis untuk menjalankan rangkaian unit test, membaca traceback error, dan memperbaiki bug.

**Triggers**: test, pytest, unit test, debug, fix bug, traceback, error log

## Panduan & Petunjuk Langkah:
1. Jalankan unit test menggunakan `{"tool": "test_runner", "params": {"test_path": "tests", "verbose": true}}` atau `{"tool": "shell", "params": {"command": "python -m pytest"}}`.
2. Jika ada test yang gagal (FAIL/ERROR), periksa detail assertion error dan baris file yang bermasalah.
3. Buka dan baca file yang bermasalah menggunakan `{"tool": "filesystem", "params": {"operation": "read_file", "path": "<file_path>"}}`.
4. Lakukan modifikasi kode untuk memperbaiki bug, lalu jalankan kembali unit test untuk memverifikasi 100% lulus.

## Contoh Penggunaan:
- jalankan semua unit test dan perbaiki jika ada yang error
- debug fungsi yang gagal di test suite
