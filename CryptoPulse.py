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
    clean = re.sub(r"\s+", " ", clean)
    return clean.strip()[:280]


def extract_item_image(item):
    """Extrait l'URL de l'image associée au flux RSS."""
    # 1. Balise enclosure
    enclosure = item.find("enclosure")
    if enclosure is not None and "image" in enclosure.get("type", ""):
        url = enclosure.get("url")
        if url:
            return url

    # 2. Balise media:content ou media:thumbnail (namespaces XML)
    namespaces = {
        "media": "http://search.yahoo.com/mrss/",
        "content": "http://purl.org/rss/1.0/modules/content/",
    }
    for tag in [".//media:content", ".//media:thumbnail"]:
        elem = item.find(tag, namespaces)
        if elem is not None and elem.get("url"):
            return elem.get("url")

    # 3. Image dans la description HTML
    desc = item.find("description")
    if desc is not None and desc.text:
        img_match = re.search(r'<img[^>]+src=["\'](.*?)["\']', desc.text)
        if img_match:
            return img_match.group(1)

    return None


def fetch_multiple_feed_items(url, category, limit=3):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    items = []
    try:
        res = requests.get(url, headers=headers, timeout=8)
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for item in root.findall(".//item")[:limit]:
                title_el = item.find("title")
                link_el = item.find("link")
                desc_el = item.find("description")

                title = title_el.text if title_el is not None and title_el.text else ""
                link = link_el.text if link_el is not None and link_el.text else ""
                desc = desc_el.text if desc_el is not None and desc_el.text else ""
                image_url = extract_item_image(item)

                if title and link:
                    items.append(
                        {
                            "category": category,
                            "title": title.strip(),
                            "link": link.strip(),
                            "desc": clean_html_text(desc),
                            "image": image_url,
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
            "Macro & Taux",
            3,
        )
    )
    news_pool.extend(
        fetch_multiple_feed_items(
            "https://www.theblock.co/rss.xml", "Marchés Crypto", 3
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
    if not news_pool or not GEMINI_API_KEY:
        return None

    articles_payload = []
    for i, a in enumerate(news_pool, 1):
        articles_payload.append(
            f"ID:{i} | THÈME:{a['category']} | TITRE:{a['title']} | RÉSUMÉ:{a['desc']} | URL:{a['link']}"
        )
    articles_text = "\n".join(articles_payload)

    prompt = (
        "Tu es un analyste quantitatif et macro senior préparant un rapport de marché exécutif pour des traders institutionnels.\n"
        "Voici le flux de dépêches brutes :\n"
        f"{articles_text}\n\n"
        "Consignes impératives :\n"
        "1. Sélectionne exactement 3 événements à fort impact (1 Géopolitique, 1 Macro/Taux, 1 Crypto).\n"
        "2. Pour chaque événement, produis une analyse poussée comprenant :\n"
        "   - 'id' : l'ID d'origine (1 à 9)\n"
        "   - 'category' : libellé court en majuscules (ex: 'GÉOPOLITIQUE // STRATÉGIE', 'MACRO // LIQUIDITÉ', 'CRYPTO // VOLATILITÉ')\n"
        "   - 'title' : titre incisif et professionnel en français\n"
        "   - 'summary' : analyse dense de 3 à 4 phrases détaillant la mécanique sous-jacente, les répercussions immédiates sur les spreads, taux réels ou la liquidité, et les points de vigilance pour la session.\n"
        "   - 'link' : l'URL exacte correspondante\n\n"
        "Renvoie STRICTEMENT un tableau JSON de 3 objets."
    )

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": GEMINI_API_KEY,
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.15,
        },
    }

    # Modèles cibles opérationnels
    modeles_cibles = ["gemini-flash-latest", "gemini-pro-latest"]
    
    # Temporisations poussées : 20s, 40s, puis 60s pour franchir les goulots d'étranglement
    pauses = [20, 40, 60]

    for model in modeles_cibles:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

        for tentative, pause in enumerate(pauses, 1):
            try:
                print(f"Appel {model} (tentative {tentative}/{len(pauses)})...")
                r = requests.post(url, headers=headers, json=payload, timeout=50)

                if r.status_code == 200:
                    data = r.json()
                    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])
                    output = extraire_json_valide(parts[0].get("text", ""))
                    if output:
                        # Associe les images d'origine correspondantes aux articles choisis
                        for item_ia in output:
                            url_ia = item_ia.get("link", "")
                            match_source = next((x for x in news_pool if x["link"] == url_ia), None)
                            if match_source and match_source.get("image"):
                                item_ia["image"] = match_source["image"]
                            else:
                                item_ia["image"] = None

                        print(f"{Fore.GREEN}✔ Synthèse analytique réussie avec {model} !")
                        return output

                if r.status_code in [429, 503]:
                    print(f"Saturation Google ({r.status_code}) sur {model}. Pause tactique de {pause}s...")
                    time.sleep(pause)
                else:
                    print(f"Erreur HTTP {r.status_code} sur {model} : {r.text[:100]}")
                    break

            except requests.exceptions.Timeout:
                print(f"Timeout réseau ({pause}s d'attente avant reprise)...")
                time.sleep(pause)
            except Exception as e:
                print(f"Erreur inattendue sur {model} : {e}")
                time.sleep(pause)

    print(f"{Fore.YELLOW}⚠️ Serveurs IA indisponibles après délais complets. Bascule sur le flux brut.")
    fallback_news = []
    for item in news_pool[:3]:
        fallback_news.append({
            "category": f"FLUX DIRECT // {item['category'].upper()}",
            "title": item["title"],
            "summary": item["desc"] or "Synthèse directe indisponible. Consultez la dépêche complète via le lien.",
            "link": item["link"],
            "image": item.get("image"),
        })
    return fallback_news


def get_color_html(valeur):
    if valeur is None:
        return "#64748b", "N/A"
    signe = "+" if valeur >= 0 else ""
    couleur = "#00e676" if valeur >= 0 else "#ff1744"
    return couleur, f"{signe}{valeur:.2f}%"


def envoyer_email(fng, cg, hype_px, hype_var, tradfi, ai_curated_news):
    maintenant = datetime.now().strftime("%d %b %Y | %H:%M UTC")
    btc = cg.get("bitcoin", {"usd": 0.0, "usd_24h_change": 0.0})
    eth = cg.get("ethereum", {"usd": 0.0, "usd_24h_change": 0.0})

    c_btc, v_btc = get_color_html(btc.get("usd_24h_change"))
    c_eth, v_eth = get_color_html(eth.get("usd_24h_change"))
    c_hype, v_hype = get_color_html(hype_var)

    lignes_tradfi_html = ""
    for label, (px, var) in tradfi.items():
        if px is not None:
            c, v = get_color_html(var)
            devise = "pts" if label == "S&P 500" else "USD"
            valeur_str = f"{px:,.2f} {devise}"
        else:
            c, v = "#64748b", "N/A"
            valeur_str = "Indisponible"

        lignes_tradfi_html += f"""
        <tr style="border-bottom: 1px solid #161f30;">
          <td style="padding: 10px 14px; color: #94a3b8; font-size: 12px; font-weight: 500; letter-spacing: 0.5px;">{label.upper()}</td>
          <td style="padding: 10px 14px; text-align: right; color: #f8fafc; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 13px; font-weight: 700;">{valeur_str}</td>
          <td style="padding: 10px 14px; text-align: right; color: {c}; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 13px; font-weight: 700;">{v}</td>
        </tr>
        """

    # Génération des blocs d'articles avec visuels
    news_cards_html = ""
    if ai_curated_news:
        for item in ai_curated_news:
            cat = item.get("category", "RAPPORT DE SESSION")
            link = item.get("link", "#")
            title = item.get("title", "")
            summary = item.get("summary", "")
            img_src = item.get("image")

            img_html = ""
            if img_src:
                img_html = f"""
                <div style="margin-bottom: 12px; overflow: hidden; border-radius: 6px; border: 1px solid #1e293b; max-height: 190px;">
                  <img src="{img_src}" alt="Vignette" style="width: 100%; height: auto; display: block; object-fit: cover;" />
                </div>
                """

            news_cards_html += f"""
            <div style="background-color: #0b0f19; border: 1px solid #1a2333; border-radius: 8px; padding: 18px; margin-bottom: 16px;">
              {img_html}
              <div style="display: inline-block; padding: 3px 8px; background-color: rgba(0, 240, 255, 0.08); border: 1px solid rgba(0, 240, 255, 0.25); border-radius: 4px; color: #00f0ff; font-size: 10px; font-weight: 700; letter-spacing: 1px; margin-bottom: 8px;">
                {cat}
              </div>
              <a href="{link}" target="_blank" style="color: #f1f5f9; text-decoration: none; font-size: 15px; font-weight: 700; line-height: 1.4; display: block; margin-bottom: 8px;">
                {title} →
              </a>
              <p style="color: #94a3b8; font-size: 13px; line-height: 1.6; margin: 0; text-align: justify;">
                {summary}
              </p>
            </div>
            """

    jour_annee = datetime.now().timetuple().tm_yday
    brief_du_jour = LEGAL_BRIEFS[jour_annee % len(LEGAL_BRIEFS)]

    btc_px = btc.get("usd", 0.0)
    eth_px = eth.get("usd", 0.0)
    hype_display = f"{hype_px:,.2f} USDC" if hype_px is not None else "N/A"
    fng_val = fng.get("value", "50")
    fng_class = fng.get("value_classification", "Neutral").upper()

    # Thème futuriste / Terminal quantitatif
    html_content = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 24px 10px; background-color: #030712; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f8fafc;">
  <div style="max-width: 580px; margin: 0 auto; background-color: #070b14; border: 1px solid #162032; border-radius: 12px; overflow: hidden; box-shadow: 0 20px 40px rgba(0,0,0,0.85);">
    
    <!-- HEADER // TERMINAL STYLE -->
    <div style="background: linear-gradient(180deg, #0d1527 0%, #070b14 100%); padding: 24px 20px; border-bottom: 1px solid #162032; text-align: left;">
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
        <span style="font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; color: #00f0ff; letter-spacing: 2px; font-weight: 700; text-transform: uppercase;">● CRYPTOPULSE // INTELLIGENCE</span>
        <span style="font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; color: #475569;">{maintenant}</span>
      </div>
      <h1 style="margin: 4px 0 0 0; font-size: 22px; font-weight: 800; letter-spacing: -0.5px; color: #ffffff;">
        Morning Quantitative Brief
      </h1>
    </div>

    <div style="padding: 20px;">
      
      <!-- SENTIMENT RADAR -->
      <div style="background-color: #0b1120; border: 1px solid #1a263d; border-radius: 8px; padding: 14px 16px; margin-bottom: 22px;">
        <table style="width: 100%; border-collapse: collapse;">
          <tr>
            <td style="color: #64748b; font-size: 11px; font-weight: 700; letter-spacing: 1px; text-transform: uppercase;">Index de Sentiment (Fear & Greed)</td>
            <td style="text-align: right;">
              <span style="font-family: 'JetBrains Mono', Consolas, monospace; font-size: 16px; font-weight: 800; color: #f59e0b;">{fng_val}</span>
              <span style="color: #64748b; font-size: 12px;"> / 100</span>
              <span style="margin-left: 8px; font-size: 11px; font-weight: 700; color: #94a3b8; background-color: #162032; padding: 2px 6px; border-radius: 4px;">{fng_class}</span>
            </td>
          </tr>
        </table>
      </div>

      <!-- CARNET DE MARCHÉ 1 : CRYPTO-ACTIFS -->
      <div style="margin-bottom: 22px;">
        <div style="font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; font-weight: 700; color: #38bdf8; letter-spacing: 1.5px; margin-bottom: 8px; text-transform: uppercase;">
          // MATRICE DES ACTIFS NUMÉRIQUES
        </div>
        <table style="width: 100%; border-collapse: collapse; background-color: #090e1a; border: 1px solid #162032; border-radius: 8px; overflow: hidden;">
          <tr style="border-bottom: 1px solid #161f30;">
            <td style="padding: 10px 14px; color: #94a3b8; font-size: 12px; font-weight: 500;">BITCOIN (BTC)</td>
            <td style="padding: 10px 14px; text-align: right; color: #f8fafc; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 13px; font-weight: 700;">{btc_px:,.2f} USDC</td>
            <td style="padding: 10px 14px; text-align: right; color: {c_btc}; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 13px; font-weight: 700;">{v_btc}</td>
          </tr>
          <tr style="border-bottom: 1px solid #161f30;">
            <td style="padding: 10px 14px; color: #94a3b8; font-size: 12px; font-weight: 500;">ETHEREUM (ETH)</td>
            <td style="padding: 10px 14px; text-align: right; color: #f8fafc; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 13px; font-weight: 700;">{eth_px:,.2f} USDC</td>
            <td style="padding: 10px 14px; text-align: right; color: {c_eth}; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 13px; font-weight: 700;">{v_eth}</td>
          </tr>
          <tr>
            <td style="padding: 10px 14px; color: #94a3b8; font-size: 12px; font-weight: 500;">HYPERLIQUID (HYPE)</td>
            <td style="padding: 10px 14px; text-align: right; color: #f8fafc; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 13px; font-weight: 700;">{hype_display}</td>
            <td style="padding: 10px 14px; text-align: right; color: {c_hype}; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 13px; font-weight: 700;">{v_hype}</td>
          </tr>
        </table>
      </div>

      <!-- CARNET DE MARCHÉ 2 : TRADFI & MACRO -->
      <div style="margin-bottom: 26px;">
        <div style="font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; font-weight: 700; color: #a855f7; letter-spacing: 1.5px; margin-bottom: 8px; text-transform: uppercase;">
          // BENCHMARKS TRADFI & MATIÈRES PREMIÈRES
        </div>
        <table style="width: 100%; border-collapse: collapse; background-color: #090e1a; border: 1px solid #162032; border-radius: 8px; overflow: hidden;">
          {lignes_tradfi_html}
        </table>
      </div>

      <!-- SÉLECTION ANALYTIQUE DES ARTICLES -->
      <div style="margin-bottom: 26px;">
        <div style="font-family: 'JetBrains Mono', Consolas, monospace; font-size: 11px; font-weight: 700; color: #f43f5e; letter-spacing: 1.5px; margin-bottom: 12px; text-transform: uppercase;">
          // DÉPÊCHES STRATÉGIQUES & ANALYSE D'IMPACT
        </div>
        {news_cards_html}
      </div>

      <!-- CADRE JURIDIQUE & RÉGULATION -->
      <div style="background-color: #080d1a; border: 1px solid #1e293b; border-left: 3px solid #38bdf8; border-radius: 8px; padding: 16px;">
        <div style="font-family: 'JetBrains Mono', Consolas, monospace; font-size: 10px; font-weight: 700; color: #38bdf8; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 6px;">
          POINT DE DROIT FINANCIER // {brief_du_jour.get('category', '').upper()}
        </div>
        <div style="font-size: 14px; font-weight: 700; color: #f1f5f9; margin-bottom: 8px;">
          {brief_du_jour.get('title', '')}
        </div>
        <p style="color: #94a3b8; font-size: 12px; line-height: 1.5; margin: 0 0 10px 0;">
          {brief_du_jour.get('summary', '')}
        </p>
        <div style="background-color: #020617; border: 1px solid #162032; border-radius: 6px; padding: 8px 12px;">
          <span style="color: #f59e0b; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 10px; font-weight: 700;">SYNTHÈSE JURIDIQUE :</span>
          <span style="color: #cbd5e1; font-size: 11px; line-height: 1.4;"> {brief_du_jour.get('takeaway', '')}</span>
        </div>
      </div>

    </div>

    <!-- FOOTER -->
    <div style="border-top: 1px solid #162032; padding: 14px 20px; background-color: #050811; text-align: center;">
      <p style="margin: 0; font-family: 'JetBrains Mono', Consolas, monospace; font-size: 10px; color: #475569; letter-spacing: 1px;">
        CRYPTOPULSE AUTOMATED SYSTEM // NO INVESTMENT ADVICE
      </p>
    </div>

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
        "subject": f"[PULSE] BTC: ${btc_px:,.0f} | F&G: {fng_val} | Macro Alert",
        "html": html_content,
    }

    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code in [200, 201]:
            print(f"{Fore.GREEN}✔ Briefing exécutif expédié avec succès !")
        else:
            print(f"{Fore.RED}✘ Échec Resend ({res.status_code}) : {res.text}")
    except Exception as e:
        print(f"{Fore.RED}✘ Erreur d'expédition e-mail : {e}")


def main():
    fng, cg = fetch_crypto_data()
    hype_px, hype_var = fetch_hype_hyperliquid()
    tradfi = fetch_tradfi()

    print("Collecte du pool d'actualités brutes (avec extraction multimédia)...")
    raw_news = collect_raw_news()

    print("Analyse, sélection et synthèse par IA...")
    ai_curated_news = filtrer_et_analyser_avec_ia(raw_news)

    print("Génération et expédition du rapport final...")
    envoyer_email(fng, cg, hype_px, hype_var, tradfi, ai_curated_news)


if __name__ == "__main__":
    main()
