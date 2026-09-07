import os
import re
import json
import requests
import xml.etree.ElementTree as ET

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

print(f"--- DIAGNOSTIC NEWS ---")
print(f"GEMINI_API_KEY présente : {bool(GEMINI_API_KEY)}")

# 1. Test des flux RSS
feeds = {
    "BBC": "http://feeds.bbci.co.uk/news/world/rss.xml",
    "MarketWatch": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "TheBlock": "https://www.theblock.co/rss.xml"
}

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
raw_news = []

for name, url in feeds.items():
    try:
        r = requests.get(url, headers=headers, timeout=6)
        print(f"Flux {name} : HTTP {r.status_code}")
        if r.status_code == 200:
            root = ET.fromstring(r.content)
            items = root.findall(".//item")
            print(f"  -> {len(items)} articles trouvés")
            for item in items[:2]:
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                if title and link:
                    raw_news.append({"category": name, "title": title.strip(), "link": link.strip(), "desc": ""})
    except Exception as e:
        print(f"Erreur flux {name} : {e}")

print(f"Total articles collectés : {len(raw_news)}")

if not raw_news:
    print("ÉCHEC : Aucun flux RSS n'a pu être chargé.")
    exit(1)

# 2. Test appel API Gemini
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
headers_gemini = {"Content-Type": "application/json"}

articles_text = "\n".join([f"[{i}] {a['category']} : {a['title']}" for i, a in enumerate(raw_news[:6], 1)])
prompt = (
    "Sélectionne 3 actualités parmi cette liste et réponds STRICTEMENT avec ce JSON valide :\n"
    '[{"category": "TEST", "title": "titre", "summary": "resume", "link": "https://example.com"}]\n\n'
    f"Articles :\n{articles_text}"
)

payload = {"contents": [{"parts": [{"text": prompt}]}]}

try:
    res = requests.post(url, headers=headers_gemini, json=payload, timeout=20)
    print(f"\nRéponse Gemini HTTP : {res.status_code}")
    if res.status_code != 200:
        print(f"Erreur API brute : {res.text}")
    else:
        data = res.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        print("Texte brut retourné par Gemini :")
        print(raw_text[:200] + "...")
        match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            print(f"\nSUCCÈS : {len(parsed)} articles parsés avec succès !")
        else:
            print("\nÉCHEC PARSING : Aucun bloc JSON détecté.")
except Exception as e:
    print(f"Exception lors de l'appel Gemini : {e}")
