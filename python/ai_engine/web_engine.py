import urllib.request
import urllib.parse
import json
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

def get_google_news(query: str, count: int = 3) -> list:
    """Mengambil berita dan informasi terkini real-time dari Google News RSS"""
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=id&gl=ID&ceid=ID:id"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    items = []
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            tree = ET.fromstring(r.read())
            for item in tree.findall(".//item")[:count]:
                title = item.find("title").text if item.find("title") is not None else ""
                source = item.find("source").text if item.find("source") is not None else "Media"
                items.append(f"[Berita Terkini - {source}]: {title}")
    except Exception:
        pass
    return items

def search_wikipedia(query: str) -> str:
    """Mengambil definisi dan data ensiklopedia terverifikasi dari Wikipedia"""
    try:
        w_url = f"https://id.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&format=json&utf8=1"
        req = urllib.request.Request(w_url, headers={"User-Agent": "LocalAutonomousAgent/1.0 (rezky@local)"})
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
            hits = data.get("query", {}).get("search", [])
            if not hits:
                return ""
            output = []
            for h in hits[:2]:
                title = h.get("title", "")
                sum_url = f"https://id.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
                try:
                    s_req = urllib.request.Request(sum_url, headers={"User-Agent": "LocalAutonomousAgent/1.0"})
                    with urllib.request.urlopen(s_req, timeout=4) as sr:
                        s_data = json.loads(sr.read().decode("utf-8"))
                        ext = s_data.get("extract", "")
                        if ext:
                            output.append(f"[Wikipedia - {title}]: {ext}")
                except Exception:
                    clean_snip = BeautifulSoup(h.get("snippet", ""), "html.parser").get_text()
                    output.append(f"[Wikipedia - {title}]: {clean_snip}")
            return "\n\n".join(output)
    except Exception:
        pass
    return ""

def search_web(query: str) -> str:
    """Pencarian web multi-sumber: Google News Real-Time + Wikipedia Faktual"""
    output = []
    
    # 1. Google News
    news = get_google_news(query, count=3)
    if news:
        output.extend(news)
        
    # 2. Wikipedia
    wiki = search_wikipedia(query)
    if wiki:
        output.append(wiki)

    if not output:
        return "Tidak dapat menemukan data dari internet untuk kueri tersebut."
        
    return "\n\n".join(output)

def fetch_url(url: str) -> str:
    """Membaca isi teks dari halaman web mana pun"""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as r:
            soup = BeautifulSoup(r.read().decode("utf-8", errors="ignore"), "html.parser")
            for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
                tag.decompose()
            text = soup.get_text(separator=" ", strip=True)
            text = re.sub(r"\s+", " ", text)
            return text[:1500]
    except Exception as e:
        return f"Gagal mengambil konten web: {e}"
