from datetime import datetime
import json
import os
import re
import xml.etree.ElementTree as ET
from colorama import Fore, Style, init
import requests
from legal_briefs import LEGAL_BRIEFS

init(autoreset=True)

# ================= CONFIGURATION =================
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RECEIVER_EMAIL = os.getenv("EMAIL_RECEIVER")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# =================================================


def fetch_crypto_data():
    fng_url = "https://api.alternative.me/fng/?limit=1"
    fng_res = requests.get(fng_url, timeout=5).json()["data"][0]

    cg_url = (
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true"
    )
    cg_res = requests.get(cg_url, timeout=5).json()
    return fng_res, cg_res


def fetch_hype_hyperliquid():
    try:
        url = "https://api.hyperliquid.xyz/info"
        res = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={"type": "metaAndAssetCtxs"},
            timeout=5,
        ).json()
        universe = res[0]["universe"]
        contexts = res[1]
        idx = next(
            i for i, asset in enumerate(universe) if asset["name"] == "HYPE"
        )
        ctx = contexts[idx]
        prix = float(ctx["markPx"])
        prev_prix = float(ctx["prevDayPx"])
        var_24h = ((prix - prev_prix) / prev_prix) * 100
        return prix, var_24h
    except Exception:
        return None, None


def fetch_yahoo_direct(symbole):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbole}?interval=1d&range=2d"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res = requests.get(url, headers=headers, timeout=5).json()
        meta = res["chart"]["result"][0]["meta"]
        prix_actuel = float(meta["regularMarketPrice"])
        prix_precedent = float(
            meta.get("chartPreviousClose", meta.get("previousClose"))
        )
        var_24h = ((prix_actuel - prix_precedent) / prix_precedent) * 100
        return prix_actuel, var_24h
    except Exception:
        return None, None


def fetch_tradfi():
    tickers = {"Gold": "GC=F", "Crude Oil (WTI)": "CL=F", "S&P 500": "^GSPC"}
    data = {}
    for label, sym in tickers.items():
        data[label] = fetch_yahoo_direct(sym)
    return data


def clean_html_text(raw_text):
    if not raw_text:
        return ""
    clean = re.sub(r"<.*?>", "", raw_text)
    return clean.strip()[:200]


def fetch_multiple_feed_items(url, category, limit=4):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    items = []
    try:
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for item in root.findall(".//item")[:limit]:
                title = (
                    item.find("title").text
                    if item.find("title") is not None
                    else ""
                )
                link = (
                    item.find("link").text
                    if item.find("link") is not None
                    else ""
                )
                desc = (
                    item.find("description").text
                    if item.find("description") is not None
                    else ""
                )
                if title and link:
                    items.append(
                        {
                            "category": category,
                            "title": title.strip(),
                            "link": link.strip(),
                            "desc": clean_html_text(desc),
                        }
                    )
    except Exception as e:
        print(f"Erreur flux {url} : {e}")
    return items


def collect_raw_news():
    news_pool = []
    news_pool.extend(
        fetch_multiple_feed_items(
            "http://feeds.bbci.co.uk/news/world/rss.xml", "Géopolitique", 4
        )
    )
    news_pool.extend(
        fetch_multiple_feed_items(
            "https://feeds.content.dowjones.io/public/rss/mw_topstories",
            "Macro/Fed",
            4,
        )
    )
    news_pool.extend(
        fetch_multiple_feed_items(
            "https://www.theblock.co/rss.xml", "Crypto", 4
        )
    )
    return news_pool


def filtrer_et_analyser_avec_ia(news_pool):
    if not GEMINI_API_KEY:
        print(f"{Fore.RED}ERREUR: GEMINI_API_KEY non fournie.")
        return None
    if not news_pool:
        print(f"{Fore.RED}ERREUR: Aucun article chargé via les flux RSS.")
        return None

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}

    articles_text = ""
    for i, a in enumerate(news_pool, 1):
        articles_text += f"[{i}] Theme: {a['category']} | Titre: {a['title']} | Desc: {a['desc']} | URL: {a['link']}\n"

    prompt = (
        "Tu es un analyste macro et de marches financiers senior pour un briefing matinal a 8h00.\n"
        f"Voici les actualites brutes de la nuit :\n\n{articles_text}\n\n"
        "MISSION :\n"
        "Selectionne exactement 3 evenements majeurs parmi cette liste (idealement 1 Geopolitique critique, 1 Macro/Fed, 1 Crypto).\n"
        "Ecarte le bruit et les faits divers sans impact.\n\n"
        "Pour chacun des 3 evenements retenus, fournis :\n"
        "1. 'category': Le badge (ex: '🌍 Géopolitique', '🏛️ Macro & Taux', '⚡ Marchés Crypto')\n"
        "2. 'title': Un titre percutant redige en francais.\n"
        "3. 'summary': Une explication concise de 2 phrases maximum expliquant l'evenement et son impact potentiel.\n"
        "4. 'link': L'URL exacte associee a l'article dans la liste d'origine.\n\n"
        "Reponds STRICTEMENT avec un JSON valide sous la forme d'une liste d'objets, sans balises Markdown :\n"
        '[\n  {"category": "...", "title": "...", "summary": "...", "link": "..."}\n]'
    )

    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        if res.status_code == 200:
            data = res.json()
            raw_output = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            json_match = re.search(r"\[.*\]", raw_output, re.DOTALL)
            if json_match:
                return json.loads(json_match.group(0))
            return json.loads(raw_output)
        else:
            print(f"{Fore.RED}Erreur API Gemini ({res.status_code}) : {res.text}")
    except Exception as e:
        print(f"{Fore.RED}Erreur lors de l'analyse IA : {e}")

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

    lignes_tradfi_html = ""
    for label, (px, var) in tradfi.items():
        if px is not None:
            c, v = get_color_html(var)
            devise = "pts" if label == "S&P 500" else "USDC"
            lignes_tradfi_html += (
                "<tr>"
                f"<td style='padding: 8px 12px; border-bottom: 1px solid #2a2e39;'>{label}</td>"
                f"<td style='padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; font-weight: bold;'>{px:,.2f} {devise}</td>"
                f"<td style='padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; color: {c}; font-weight: bold;'>{v}</td>"
                "</tr>"
            )

    news_blocks_html = ""
    if ai_curated_news:
        for item in ai_curated_news:
            cat = item.get("category", "ACTUALITÉ")
            link = item.get("link", "#")
            title = item.get("title", "")
            summary = item.get("summary", "")
            news_blocks_html += (
                "<div style='margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid #21262d;'>"
                f"<span style='color: #f0883e; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;'>{cat}</span>"
                f"<a href='{link}' target='_blank' style='color: #58a6ff; text-decoration: none; font-size: 13px; font-weight: bold; line-height: 1.4; display: block; margin-top: 3px;'>{title}</a>"
                f"<p style='color: #c9d1d9; font-size: 12px; margin: 4px 0 0 0; line-height: 1.45;'>{summary}</p>"
                "</div>"
            )
    else:
        news_blocks_html = (
            "<p style='color: #8b949e; font-size: 12px; margin: 0;'>Synthèse d'actualités temporairement indisponible.</p>"
        )

    jour_annee = datetime.now().timetuple().tm_yday
    brief_du_jour = LEGAL_BRIEFS[jour_annee % len(LEGAL_BRIEFS)]

    legal_block_html = f"""
    <h3 style="color: #58a6ff; font-size: 14px; text-transform: uppercase; margin-top: 24px; margin-bottom: 10px;">
      ⚖️ Le Point Droit Financier : {brief_du_jour['title']}
    </h3>
    <div style="background-color: #0d1117; border-left: 3px solid #58a6ff; border-radius: 6px; padding: 14px; border-top: 1px solid #30363d; border-right: 1px solid #30363d; border-bottom: 1px solid #30363d;">
      <span style="color: #79c0ff; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">
        Thème : {brief_du_jour['category']}
      </span>
      <p style="color: #c9d1d9; font-size: 12px; margin: 6px 0 8px 0; line-height: 1.45;">
        {brief_du_jour['summary']}
      </p>
      <div style="background-color: #161b22; border-radius: 4px; padding: 8px 10px; border: 1px solid #30363d;">
        <span style="color: #f0883e; font-size: 11px; font-weight: bold;">À RETENIR :</span>
        <span style="color: #8b949e; font-size: 11px; line-height: 1.4;"> {brief_du_jour['takeaway']}</span>
      </div>
    </div>
    """

    btc_px = btc["usd"]
    eth_px = eth["usd"]
    hype_display = f"{hype_px:,.2f} USDC" if hype_px is not None else "N/A"
    fng_val = fng["value"]
    fng_class = fng["value_classification"]

    html_content = f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0d1117; color: #c9d1d9; padding: 20px;">
  <div style="max-width: 520px; margin: auto; background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; padding: 20px;">
    <h2 style="color: #58a6ff; margin-top: 0; text-align: center; border-bottom: 1px solid #30363d; padding-bottom: 12px;">
      ☕ Morning Pulse : Marchés & Stratégie
    </h2>
    <p style="text-align: center; color: #8b949e; font-size: 13px; margin-top: -6px;">{maintenant}</p>

    <div style="background-color: #21262d; border-radius: 6px; padding: 12px; margin-bottom: 20px; text-align: center;">
      <span style="color: #8b949e; font-size: 12px; text-transform: uppercase;">Fear & Greed Index</span><br>
      <strong style="font-size: 18px; color: #f0883e;">{fng_val}/100</strong> 
      <span style="color: #c9d1d9;">({fng_class})</span>
    </div>

    <h3 style="color: #e3b341; font-size: 14px; text-transform: uppercase; margin-bottom: 8px;">Crypto Actifs (USDC)</h3>
    <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 14px;">
      <tr>
        <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39;">Bitcoin (BTC)</td>
        <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; font-weight: bold;">{btc_px:,.2f} USDC</td>
        <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; color: {c_btc}; font-weight: bold;">{v_btc}</td>
      </tr>
      <tr>
        <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39;">Ethereum (ETH)</td>
        <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; font-weight: bold;">{eth_px:,.2f} USDC</td>
        <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; color: {c_eth}; font-weight: bold;">{v_eth}</td>
      </tr>
      <tr>
        <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39;">Hyperliquid (HYPE)</td>
        <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; font-weight: bold;">{hype_display}</td>
        <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; color: {c_hype}; font-weight: bold;">{v_hype}</td>
      </tr>
    </table>

    <h3 style="color: #58a6ff; font-size: 14px; text-transform: uppercase; margin-bottom: 8px;">TradFi & Commodities</h3>
    <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 14px;">
      {lignes_tradfi_html}
    </table>

    <h3 style="color: #ff7b72; font-size: 14px; text-transform: uppercase; margin-bottom: 10px;">
      🎯 Les 3 Développements Clés (Sélection IA)
    </h3>
    <div style="background-color: #0d1117; border-radius: 6px; padding: 14px; border: 1px solid #30363d;">
      {news_blocks_html}
    </div>

    {legal_block_html}
  </div>
</body>
</html>"""

    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "from": "CryptoPulse <onboarding@resend.dev>",
        "to": [RECEIVER_EMAIL],
        "subject": f"Briefing Matin - BTC: {btc_px:,.0f}$ | Fear: {fng_val}",
        "html": html_content,
    }

    res = requests.post(url, headers=headers, json=payload, timeout=10)
    if res.status_code in [200, 201]:
        print(f"{Fore.GREEN}✔ Briefing enrichi par IA envoyé avec succès !")
    else:
        print(f"{Fore.RED}✘ Échec Resend ({res.status_code}) : {res.text}")


def main():
    fng, cg = fetch_crypto_data()
    hype_px, hype_var = fetch_hype_hyperliquid()
    tradfi = fetch_tradfi()

    print("Collecte du pool d'actualités brutes...")
    raw_news = collect_raw_news()

    print("Analyse, sélection et synthèse par IA (Gemini)...")
    ai_curated_news = filtrer_et_analyser_avec_ia(raw_news)

    print("Génération et expédition du rapport final...")
    envoyer_email(fng, cg, hype_px, hype_var, tradfi, ai_curated_news)


if __name__ == "__main__":
    main()
