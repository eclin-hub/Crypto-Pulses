import os
import re
import json
import xml.etree.ElementTree as ET
from datetime import datetime
import requests
from colorama import init, Fore, Style

init(autoreset=True)

# ================= CONFIGURATION =================
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RECEIVER_EMAIL = os.getenv("EMAIL_RECEIVER")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# =================================================


def fetch_crypto_data():
    """Récupère l'indice Fear & Greed et les prix BTC/ETH via CoinGecko."""
    fng_url = "https://api.alternative.me/fng/?limit=1"
    fng_res = requests.get(fng_url, timeout=5).json()["data"][0]

    cg_url = (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true"
    )
    cg_res = requests.get(cg_url, timeout=5).json()
    return fng_res, cg_res


def fetch_hype_hyperliquid():
    """Récupère le prix et la variation 24h de HYPE sur Hyperliquid."""
    try:
        url = "https://api.hyperliquid.xyz/info"
        res = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={"type": "metaAndAssetCtxs"},
            timeout=5
        ).json()
        universe = res[0]["universe"]
        contexts = res[1]
        idx = next(i for i, asset in enumerate(universe) if asset["name"] == "HYPE")
        ctx = contexts[idx]
        prix = float(ctx["markPx"])
        prev_prix = float(ctx["prevDayPx"])
        var_24h = ((prix - prev_prix) / prev_prix) * 100
        return prix, var_24h
    except Exception:
        return None, None


def fetch_yahoo_direct(symbole):
    """Interroge l'API JSON publique de Yahoo Finance."""
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbole}?interval=1d&range=2d"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res = requests.get(url, headers=headers, timeout=5).json()
        meta = res["chart"]["result"][0]["meta"]
        prix_actuel = float(meta["regularMarketPrice"])
        prix_precedent = float(meta.get("chartPreviousClose", meta.get("previousClose")))
        var_24h = ((prix_actuel - prix_precedent) / prix_precedent) * 100
        return prix_actuel, var_24h
    except Exception:
        return None, None


def fetch_tradfi():
    """Récupère Or, Pétrole WTI et S&P 500."""
    tickers = {
        "Gold": "GC=F",
        "Crude Oil (WTI)": "CL=F",
        "S&P 500": "^GSPC"
    }
    data = {}
    for label, sym in tickers.items():
        data[label] = fetch_yahoo_direct(sym)
    return data


def clean_html_text(raw_text):
    """Nettoie les balises HTML éventuelles dans les descriptions RSS."""
    if not raw_text:
        return ""
    clean = re.sub(r"<.*?>", "", raw_text)
    return clean.strip()[:250]


def fetch_multiple_feed_items(url, category, limit=6):
    """Récupère une série d'articles bruts pour alimenter le tri de l'IA."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    items = []
    try:
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for item in root.findall(".//item")[:limit]:
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                desc = item.find("description").text if item.find("description") is not None else ""
                if title and link:
                    items.append({
                        "category": category,
                        "title": title.strip(),
                        "link": link.strip(),
                        "desc": clean_html_text(desc)
                    })
    except Exception as e:
        print(f"Erreur flux {url} : {e}")
    return items


def collect_raw_news():
    """Rassemble 15 à 20 dépêches de la nuit (Géopolitique, Macro/Fed, Crypto)."""
    news_pool = []
    # Géopolitique
    news_pool.extend(fetch_multiple_feed_items("http://feeds.bbci.co.uk/news/world/rss.xml", "Géopolitique", 7))
    # Macro / Fed / Marchés
    news_pool.extend(fetch_multiple_feed_items("https://feeds.content.dowjones.io/public/rss/mw_topstories", "Macro/Fed", 6))
    # Crypto institutionnelle
    news_pool.extend(fetch_multiple_feed_items("https://www.theblock.co/rss.xml", "Crypto", 6))
    return news_pool


def filtrer_et_analyser_avec_ia(news_pool):
    """Demande à Gemini d'isoler les 3 événements majeurs et d'en faire la synthèse."""
    if not GEMINI_API_KEY or not news_pool:
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}

    articles_text = ""
    for i, a in enumerate(news_pool, 1):
        articles_text += f"[{i}] Thème: {a['category']} | Titre: {a['title']} | Desc: {a['desc']} | URL: {a['link']}\n"

    prompt = f"""Tu es un analyste macro et de marchés financiers senior pour un briefing matinal à 8h00.
Voici la liste des actualités brutes tombées cette nuit :

{articles_text}

MISSION :
Sélectionne exactement 3 événements majeurs parmi cette liste (idéalement 1 Géopolitique critique, 1 Macro/Banques Centrales/Fed, 1 Crypto/Market Structure).
Écarte le bruit et les faits divers sans impact. Garde ce qui a un véritable impact sur le risque mondial et les marchés.

Pour chacun des 3 événements retenus, fournis :
1. "category": Le badge (ex: "🌍 Géopolitique", "🏛️ Macro & Taux", "⚡ Marchés Crypto")
2. "title": Un titre percutant rédigé en français.
3. "summary": Une explication concise de 2 phrases maximum expliquant l'événement et son impact potentiel.
4. "link": L'URL exacte associée à l'article dans la liste d'origine.

Réponds UNIQUEMENT avec un JSON valide sous la forme d'une liste d'objets, sans Markdown ```json :
[
  {{"category": "...", "title": "...", "summary": "...", "link": "..."}},
  {{"category": "...", "title": "...", "summary": "...", "link": "..."}},
  {{"category": "...", "title": "...", "summary": "...", "link": "..."}}
]
"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=12)
        if res.status_code == 200:
            data = res.json()
            raw_output = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            raw_output = re.sub(r"^```json\s*", "", raw_output, flags=re.IGNORECASE)
            raw_output = re.sub(r"```$", "", raw_output).strip()
            return json.loads(raw_output)
        else:
            print(f"Erreur API Gemini ({res.status_code}) : {res.text}")
    except Exception as e:
        print(f"Erreur lors de l'analyse IA : {e}")

    return None


def get_color_html(valeur):
    if valeur is None:
        return "#888888", "N/A"
    signe = "+" if valeur >= 0 else ""
    couleur = "#00c853" if valeur >= 0 else "#ff5252"
    return couleur, f"{signe}{valeur:.2f}%"


def envoyer_email(fng, cg, hype_px, hype_var, tradfi, ai_curated_news):
    maintenant = datetime.now().strftime("%d/%m/%Y à %H:%M")
    btc = cg["bitcoin"]
    eth = cg["ethereum"]

    c_btc, v_btc = get_color_html(btc["usd_24h_change"])
    c_eth, v_eth = get_color_html(eth["usd_24h_change"])
    c_hype, v_hype = get_color_html(hype_var)

    # Lignes TradFi & Commodities
    lignes_tradfi_html = ""
    for label, (px, var) in tradfi.items():
        if px is not None:
            c, v = get_color_html(var)
            devise = "pts" if label == "S&P 500" else "USDC"
            lignes_tradfi_html += f"""
            <tr>
                <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39;">{label}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; font-weight: bold;">{px:,.2f} {devise}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; color: {c}; font-weight: bold;">{v}</td>
            </tr>
            """

    # Blocs actualités sélectionnés par l'IA
    news_blocks_html = ""
    if ai_curated_news:
        for item in ai_curated_news:
            news_blocks_html += f"""
            <div style="margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid #21262d;">
                <span style="color: #f0883e; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">{item.get('category', 'ACTUALITÉ')}</span>
                <a href="{item.get('link', '#')}" target="_blank" style="
