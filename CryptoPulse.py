from datetime import datetime
import json
import os
import re
import time
import xml.etree.ElementTree as ET
from colorama import Fore, Style, init
import requests
from legal_briefs import LEGAL_BRIEFS

init(autoreset=True)

# ================= CONFIGURATION =================
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
RECEIVER_EMAIL = os.getenv("EMAIL_RECEIVER")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
# =================================================


def fetch_crypto_data():
    try:
        fng_url = "https://api.alternative.me/fng/?limit=1"
        fng_res = requests.get(fng_url, timeout=5).json()["data"][0]
    except Exception as e:
        print(f"Erreur Fear & Greed : {e}")
        fng_res = {"value": "50", "value_classification": "Neutral"}

    try:
        cg_url = (
            "https://api.coingecko.com/api/v3/simple/price"
            "?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true"
        )
        cg_res = requests.get(cg_url, timeout=5).json()
    except Exception as e:
        print(f"Erreur CoinGecko : {e}")
        cg_res = {
            "bitcoin": {"usd": 0.0, "usd_24h_change": 0.0},
            "ethereum": {"usd": 0.0, "usd_24h_change": 0.0},
        }

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
            i for i, asset in enumerate(universe) if asset.get("name") == "HYPE"
        )
        ctx = contexts[idx]
        prix = float(ctx["markPx"])
        prev_prix = float(ctx["prevDayPx"])
        var_24h = ((prix - prev_prix) / prev_prix) * 100 if prev_prix != 0 else 0.0
        return prix, var_24h
    except Exception as e:
        print(f"Erreur Hyperliquid : {e}")
        return None, None


def fetch_yahoo_direct(symbole):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbole}?interval=1d&range=2d"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        res = requests.get(url, headers=headers, timeout=5).json()
        meta = res["chart"]["result"][0]["meta"]

        prix_actuel = meta.get("regularMarketPrice")
        prix_precedent = meta.get("chartPreviousClose") or meta.get("previousClose")

        if prix_actuel is None or prix_precedent is None:
            return None, None

        prix_actuel = float(prix_actuel)
        prix_precedent = float(prix_precedent)
        var_24h = ((prix_actuel - prix_precedent) / prix_precedent) * 100 if prix_precedent != 0 else 0.0
        return prix_actuel, var_24h
    except Exception as e:
        print(f"Erreur Yahoo Finance ({symbole}) : {e}")
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
    return clean.strip()[:180]


def fetch_multiple_feed_items(url, category, limit=3):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    items = []
    try:
        res = requests.get(url, headers=headers, timeout=6)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for item in root.findall(".//item")[:limit]:
                title_el = item.find("title")
                link_el = item.find("link")
                desc_el = item.find("description")

                title = title_el.text if title_el is not None and title_el.text else ""
                link = link_el.text if link_el is not None and link_el.text else ""
                desc = desc_el.text if desc_el is not None and desc_el.text else ""

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
            "http://feeds.bbci.co.uk/news/world/rss.xml", "Géopolitique", 3
        )
    )
    news_pool.extend(
        fetch_multiple_feed_items(
            "https://feeds.content.dowjones.io/public/rss/mw_topstories",
            "Macro/Fed",
            3,
        )
    )
    news_pool.extend(
        fetch_multiple_feed_items(
            "https://www.theblock.co/rss.xml", "Crypto", 3
        )
    )
    return news_pool


def extraire_json_valide(texte):
    if not texte:
        return None
    texte = texte.strip()
    match = re.search(r"\[.*\]", texte, re.DOTALL)
    if match:
        try:
            res = json.loads(match.group(0))
            if isinstance(res, list) and len(res) > 0:
                return res
        except Exception:
            pass
    try:
        parsed = json.loads(texte)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            for v in parsed.values():
                if isinstance(v, list) and len(v) > 0:
                    return v
    except Exception:
        pass
    return None


def filtrer_et_analyser_avec_ia(news_pool):
    if not news_pool:
        return None

    articles_text = ""
    for i, a in enumerate(news_pool, 1):
        articles_text += f"[{i}] {a['category']} | Titre: {a['title']} | URL: {a['link']}\n"

    prompt = (
        "Tu es un analyste financier macro senior pour un briefing matinal.\n"
        f"Voici les actualites brutes :\n\n{articles_text}\n\n"
        "Choisis exactement 3 evenements prioritaires (idealement 1 Geopolitique, 1 Macro/Taux, 1 Crypto).\n"
        "Pour chacun, remplis cet objet JSON :\n"
        "- category : un badge court avec emoji (ex: '🌍 Géopolitique', '🏛️ Macro & Fed', '⚡ Crypto')\n"
        "- title : un titre percutant en francais\n"
        "- summary : un resume de 2 phrases percutantes sur les implications de marche\n"
        "- link : l'URL exacte reprise de la liste d'origine\n\n"
        "Renvoie STRICTEMENT un tableau JSON de 3 elements : [ {category, title, summary, link}, ... ]"
    )

    # ==========================================================
    # BATTERIE 1 : GEMINI (Multi-endpoints v1/v1beta + 10 modèles)
    # ==========================================================
    if GEMINI_API_KEY:
        gemini_combinaisons = [
            ("v1beta", "gemini-2.5-flash"),
            ("v1beta", "gemini-2.0-flash"),
            ("v1", "gemini-2.5-flash"),
            ("v1", "gemini-2.0-flash"),
            ("v1beta", "gemini-flash-latest"),
            ("v1beta", "gemini-pro-latest"),
            ("v1", "gemini-flash-latest"),
            ("v1", "gemini-pro-latest"),
            ("v1beta", "gemini-1.5-flash-latest"),
            ("v1beta", "gemini-1.5-flash"),
            ("v1", "gemini-1.5-flash"),
            ("v1beta", "gemini-1.5-pro"),
        ]

        payload_gemini = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2,
            },
        }
        headers_gemini = {"Content-Type": "application/json"}

        for version, model in gemini_combinaisons:
            url = f"https://generativelanguage.googleapis.com/{version}/models/{model}:generateContent?key={GEMINI_API_KEY}"
            try:
                r = requests.post(url, headers=headers_gemini, json=payload_gemini, timeout=15)
                if r.status_code == 200:
                    data = r.json()
                    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])
                    output = extraire_json_valide(parts[0].get("text", ""))
                    if output:
                        print(f"{Fore.GREEN}✔ Synthèse réussie avec Gemini ({version}/{model})")
                        return output
                elif r.status_code in [429, 503]:
                    print(f"Saturation {model} ({r.status_code}), passage au suivant...")
                else:
                    print(f"Échec {model} sur {version} ({r.status_code})")
            except Exception as e:
                print(f"Erreur réseau sur {model} : {e}")

    # ==========================================================
    # BATTERIE 2 : GROQ (Llama 3.3, Llama 3.1, Mixtral)
    # ==========================================================
    if GROQ_API_KEY:
        groq_modeles = [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "llama3-70b-8192",
            "mixtral-8x7b-32768",
        ]
        headers_groq = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        for gm in groq_modeles:
            print(f"Tentative Groq avec {gm}...")
            payload_groq = {
                "model": gm,
                "messages": [
                    {
                        "role": "system",
                        "content": "Tu es un analyste financier senior. Réponds TOUJOURS par un tableau JSON valide de 3 objets.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
            }
            try:
                r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers_groq, json=payload_groq, timeout=15)
                if r.status_code == 200:
                    content = r.json()["choices"][0]["message"]["content"]
                    output = extraire_json_valide(content)
                    if output:
                        print(f"{Fore.GREEN}✔ Synthèse réussie avec Groq ({gm})")
                        return output
                else:
                    print(f"Échec Groq {gm} ({r.status_code})")
            except Exception as e:
                print(f"Erreur Groq {gm} : {e}")

    # ==========================================================
    # BATTERIE 3 : OPENROUTER (Modèles gratuits)
    # ==========================================================
    if OPENROUTER_API_KEY:
        openrouter_modeles = [
            "google/gemini-2.0-flash-exp:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "qwen/qwen-2.5-72b-instruct:free",
        ]
        headers_or = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        }
        for or_m in openrouter_modeles:
            print(f"Tentative OpenRouter avec {or_m}...")
            payload_or = {
                "model": or_m,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            }
            try:
                r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers_or, json=payload_or, timeout=20)
                if r.status_code == 200:
                    content = r.json()["choices"][0]["message"]["content"]
                    output = extraire_json_valide(content)
                    if output:
                        print(f"{Fore.GREEN}✔ Synthèse réussie avec OpenRouter ({or_m})")
                        return output
            except Exception as e:
                print(f"Erreur OpenRouter {or_m} : {e}")

    # ==========================================================
    # BATTERIE 4 : SECOURS BRUT ENRICHI (Zéro IA, 100 % fiable)
    # ==========================================================
    print(f"{Fore.YELLOW}⚠️ Tous les services IA ont échoué. Bascule sur la sélection directe.")
    fallback_news = []
    for item in news_pool[:3]:
        fallback_news.append({
            "category": f"📰 {item['category']}",
            "title": item["title"],
            "summary": item["desc"] or "Consultez le lien officiel pour l'intégralité de la dépêche.",
            "link": item["link"],
        })
    return fallback_news


def get_color_html(valeur):
    if valeur is None:
        return "#888888", "N/A"
    signe = "+" if valeur >= 0 else ""
    couleur = "#00c853" if valeur >= 0 else "#ff5252"
    return couleur, f"{signe}{valeur:.2f}%"


def envoyer_email(fng, cg, hype_px, hype_var, tradfi, ai_curated_news):
    maintenant = datetime.now().strftime("%d/%m/%Y à %H:%M")
    btc = cg.get("bitcoin", {"usd": 0.0, "usd_24h_change": 0.0})
    eth = cg.get("ethereum", {"usd": 0.0, "usd_24h_change": 0.0})

    c_btc, v_btc = get_color_html(btc.get("usd_24h_change"))
    c_eth, v_eth = get_color_html(eth.get("usd_24h_change"))
    c_hype, v_hype = get_color_html(hype_var)

    lignes_tradfi_html = ""
    for label, (px, var) in tradfi.items():
        if px is not None:
            c, v = get_color_html(var)
            devise = "pts" if label == "S&P 500" else "USDC"
            valeur_str = f"{px:,.2f} {devise}"
        else:
            c, v = "#888888", "N/A"
            valeur_str = "Indisponible"

        lignes_tradfi_html += (
            "<tr>"
            f"<td style='padding: 8px 12px; border-bottom: 1px solid #2a2e39;'>{label}</td>"
            f"<td style='padding: 8px 12px; border-bottom: 1px solid #2a2e39; text-align: right; font-weight: bold;'>{valeur_str}</td>"
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
      ⚖️ Le Point Droit Financier : {brief_du_jour.get('title', '')}
    </h3>
    <div style="background-color: #0d1117; border-left: 3px solid #58a6ff; border-radius: 6px; padding: 14px; border: 1px solid #30363d;">
      <span style="color: #79c0ff; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">
        Thème : {brief_du_jour.get('category', '')}
      </span>
      <p style="color: #c9d1d9; font-size: 12px; margin: 6px 0 8px 0; line-height: 1.45;">
        {brief_du_jour.get('summary', '')}
      </p>
      <div style="background-color: #161b22; border-radius: 4px; padding: 8px 10px; border: 1px solid #30363d;">
        <span style="color: #f0883e; font-size: 11px; font-weight: bold;">À RETENIR :</span>
        <span style="color: #8b949e; font-size: 11px; line-height: 1.4;"> {brief_du_jour.get('takeaway', '')}</span>
      </div>
    </div>
    """

    btc_px = btc.get("usd", 0.0)
    eth_px = eth.get("usd", 0.0)
    hype_display = f"{hype_px:,.2f} USDC" if hype_px is not None else "N/A"
    fng_val = fng.get("value", "N/A")
    fng_class = fng.get("value_classification", "")

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

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code in [200, 201]:
            print(f"{Fore.GREEN}✔ Briefing envoyé avec succès !")
        else:
            print(f"{Fore.RED}✘ Échec Resend ({res.status_code}) : {res.text}")
    except Exception as e:
        print(f"{Fore.RED}✘ Erreur d'expédition e-mail : {e}")


def main():
    fng, cg = fetch_crypto_data()
    hype_px, hype_var = fetch_hype_hyperliquid()
    tradfi = fetch_tradfi()

    print("Collecte du pool d'actualités brutes...")
    raw_news = collect_raw_news()

    print("Analyse, sélection et synthèse par IA...")
    ai_curated_news = filtrer_et_analyser_avec_ia(raw_news)

    print("Génération et expédition du rapport final...")
    envoyer_email(fng, cg, hype_px, hype_var, tradfi, ai_curated_news)


if __name__ == "__main__":
    main()
