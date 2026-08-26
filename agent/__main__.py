"""
agent/__main__.py

Memungkinkan agent dijalankan langsung sebagai modul Python:
    python -m agent

Mendelegasikan ke `agent.main:main` untuk semua logika startup.
"""

from agent.main import main

if __name__ == "__main__":
    main()
