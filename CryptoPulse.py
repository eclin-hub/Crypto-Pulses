from datetime import datetime
import os
import re
import xml.etree.ElementTree as ET
from colorama import Fore, Style, init
import requests

init(autoreset=True)

# ================= CONFIGURATION =================
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RECEIVER_EMAIL = os.getenv("EMAIL_RECEIVER")
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
    tickers = {"Gold": "GC=F", "Silver": "SI=F", "S&P 500": "^GSPC"}
    data = {}
    for label, sym in tickers.items():
        data[label] = fetch_yahoo_direct(sym)
    return data


def clean_html_text(raw_text):
    if not raw_text:
        return ""
    clean = re.sub(r"<.*?>", "", raw_text)
    return clean.strip()[:200] + ("..." if len(clean) > 200 else "")


def fetch_single_feed_top(url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            item = root.find(".//item")
            if item is not None:
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
                    return {
                        "title": title.strip(),
                        "link": link.strip(),
                        "desc": clean_html_text(desc),
                    }
    except Exception as e:
        print(f"Erreur parsing {url} : {e}")
    return None


def fetch_curated_briefing():
    # 1. GÉOPOLITIQUE
    geopo = fetch_single_feed_top("http://feeds.bbci.co.uk/news/world/rss.xml")

    # 2. MACRO & FED
    macro = fetch_single_feed_top(
        "https://feeds.content.dowjones.io/public/rss/mw_topstories"
    )
    if not macro:
        macro = fetch_single_feed_top(
            "https://news.google.com/rss/search?q=Federal+Reserve+OR+inflation+when:1d&hl=en-US&gl=US&ceid=US:en"
        )

    # 3. CRYPTO INSTITUTIONNELLE
    crypto = fetch_single_feed_top("https://www.theblock.co/rss.xml")
    if not crypto:
        crypto = fetch_single_feed_top(
            "https://www.coindesk.com/arc/outboundfeeds/rss/?category=markets"
        )

    return {
        "geopolitics": {
            "label": "🌍 Crise & Géopolitique (BBC World)",
            "data": geopo,
        },
        "macro_fed": {
            "label": "🏛️ Macro, Fed & Taux (MarketWatch / Dow Jones)",
            "data": macro,
        },
        "crypto": {
            "label": "⚡ Crypto & Market Structure (The Block)",
            "data": crypto,
        },
    }


def get_color_html(valeur):
    if valeur is None:
        return "#888888", "N/A"
    signe = "+" if valeur >= 0 else ""
    couleur = "#00c853" if valeur >= 0 else "#ff5252"
    return couleur, f"{signe}{valeur:.2f}%"


def envoyer_email(fng, cg, hype_px, hype_var, tradfi, briefing_news):
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
            lignes_tradfi_html += f"""
            <tr>
                <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39;">{label}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; font-weight: bold;">{px:,.2f} {devise}</td>
                <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; color: {c}; font-weight: bold;">{v}</td>
            </tr>
            """

    news_blocks_html = ""
    for key, info in briefing_news.items():
        label = info["label"]
        item = info["data"]
        if item:
            news_blocks_html += f"""
            <div style="margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid #21262d;">
                <span style="color: #f0883e; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">{label}</span>
                <a href="{item['link']}" target="_blank" style="color: #58a6ff; text-decoration: none; font-size: 13px; font-weight: bold; line-height: 1.4; display: block; margin-top: 3px;">
                    {item['title']}
                </a>
                <p style="color: #8b949e; font-size: 12px; margin: 4px 0 0 0; line-height: 1.4;">
                    {item['desc']}
                </p>
            </div>
            """

    html_content = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0d1117; color: #c9d1d9; padding: 20px;">
        <div style="max-width: 520px; margin: auto; background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; padding: 20px;">
            <h2 style="color: #58a6ff; margin-top: 0; text-align: center; border-bottom: 1px solid #30363d; padding-bottom: 12px;">
                ☕ Morning Pulse : Marchés & Stratégie
            </h2>
            <p style="text-align: center; color: #8b949e; font-size: 13px; margin-top: -6px;">{maintenant}</p>

            <!-- Fear & Greed -->
            <div style="background-color: #21262d; border-radius: 6px; padding: 12px; margin-bottom: 20px; text-align: center;">
                <span style="color: #8b949e; font-size: 12px; text-transform: uppercase;">Fear & Greed Index</span><br>
                <strong style="font-size: 18px; color: #f0883e;">{fng['value']}/100</strong> 
                <span style="color: #c9d1d9;">({fng['value_classification']})</span>
            </div>

            <!-- Cryptos USDC -->
            <h3 style="color: #e3b341; font-size: 14px; text-transform: uppercase; margin-bottom: 8px;">Crypto Actifs (USDC)</h3>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 14px;">
                <tr>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39;">Bitcoin (BTC)</td>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; font-weight: bold;">{btc['usd']:,.2f} USDC</td>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; color: {c_btc}; font-weight: bold;">{v_btc}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39;">Ethereum (ETH)</td>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; font-weight: bold;">{eth['usd']:,.2f} USDC</td>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; color: {c_eth}; font-weight: bold;">{v_eth}</td>
                </tr>
                <tr>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39;">Hyperliquid (HYPE)</td>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; font-weight: bold;">{hype_px:,.2f} USDC</td>
                    <td style="padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; color: {c_hype}; font-weight: bold;">{v_hype}</td>
                </tr>
            </table>

            <!-- TradFi & Commodities -->
            <h3 style="color: #58a6ff; font-size: 14px; text-transform: uppercase; margin-bottom: 8px;">TradFi & Commodities</h3>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 14px;">
                {lignes_tradfi_html}
            </table>

            <!-- 3 Titres Clés -->
            <h3 style="color: #ff7b72; font-size: 14px; text-transform: uppercase; margin-bottom: 10px;">
                🚨 Les 3 Titres Clés de la Nuit
            </h3>
            <div style="background-color: #0d1117; border-radius: 6px; padding: 14px; border: 1px solid #30363d;">
                {news_blocks_html}
            </div>
        </div>
    </body>
    </html>
    """

    url = "https://api.resend.com/emails"
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "from": "CryptoPulse <onboarding@resend.dev>",
        "to": [RECEIVER_EMAIL],
        "subject": f"☕ Briefing Matin - BTC: {btc['usd']:,.0f}$ | Fear: {fng['value']}",
        "html": html_content,
    }

    res = requests.post(url, headers=headers, json=payload, timeout=10)
    if res.status_code in [200, 201]:
        print(f"{Fore.GREEN}✔ Rapport complet envoyé avec succès via Resend")
    else:
        print(f"{Fore.RED}✘ Échec Resend ({res.status_code}) : {res.text}")


def main():
    fng, cg = fetch_crypto_data()
    hype_px, hype_var = fetch_hype_hyperliquid()
    tradfi = fetch_tradfi()
    briefing_news = fetch_curated_briefing()

    print("Génération et envoi du rapport avec actualités ciblées...")
    envoyer_email(fng, cg, hype_px, hype_var, tradfi, briefing_news)


if __name__ == "__main__":
    main()
