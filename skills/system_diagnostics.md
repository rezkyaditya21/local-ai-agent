# Skill: System Diagnostics

> Panduan untuk mendiagnosis kesehatan sistem, penggunaan CPU/RAM, ruang disk, dan koneksi jaringan.

**Triggers**: diagnosa, spek sistem, ram, disk, status server, cpu, network, ping

## Panduan & Petunjuk Langkah:
1. Periksa runtime dan platform menggunakan `{"tool": "system_inspect", "params": {"target": "all"}}`.
2. Untuk memeriksa ruang disk atau memori di Windows via terminal, gunakan `{"tool": "shell", "params": {"command": "powershell \"Get-PSDrive -PSProvider FileSystem\""}}`.
3. Untuk memeriksa konektivitas internet atau port, gunakan `{"tool": "http_api", "params": {"method": "GET", "url": "https://1.1.1.1"}}` atau ping.
4. Rangkum kondisi sistem secara ringkas dan berikan saran jika ada resource yang hampir penuh.

## Contoh Penggunaan:
- cek kondisi sistem dan penggunaan memory laptop
- diagnosa koneksi internet dan status disk
