from datetime import datetime
from email.message import EmailMessage
import os
import smtplib
from colorama import Fore, Style, init
import requests

init(autoreset=True)

# ================= CONFIGURATION EMAIL =================
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465
SENDER_EMAIL = os.getenv("EMAIL_USER")
SENDER_PASSWORD = os.getenv("EMAIL_PASS")
RECEIVER_EMAIL = os.getenv("EMAIL_RECEIVER")
# =======================================================


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
        headers = {"User-Agent": "Mozilla/5.0"}
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


def get_color_html(valeur):
    if valeur is None:
        return "#888888", "N/A"
    signe = "+" if valeur >= 0 else ""
    couleur = "#00c853" if valeur >= 0 else "#ff5252"
    return couleur, f"{signe}{valeur:.2f}%"


def envoyer_email(fng, cg, hype_px, hype_var, tradfi):
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

    html_content = f"""
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0d1117; color: #c9d1d9; padding: 20px;">
        <div style="max-width: 520px; margin: auto; background-color: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; padding: 20px;">
            <h2 style="color: #58a6ff; margin-top: 0; text-align: center; border-bottom: 1px solid #30363d; padding-bottom: 12px;">
                ☕ Rapport Marchés du Matin
            </h2>
            <p style="text-align: center; color: #8b949e; font-size: 13px; margin-top: -6px;">{maintenant}</p>

            <div style="background-color: #21262d; border-radius: 6px; padding: 12px; margin-bottom: 20px; text-align: center;">
                <span style="color: #8b949e; font-size: 12px; text-transform: uppercase;">Fear & Greed Index</span><br>
                <strong style="font-size: 18px; color: #f0883e;">{fng['value']}/100</strong> 
                <span style="color: #c9d1d9;">({fng['value_classification']})</span>
            </div>

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

            <h3 style="color: #58a6ff; font-size: 14px; text-transform: uppercase; margin-bottom: 8px;">TradFi & Commodities</h3>
            <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                {lignes_tradfi_html}
            </table>
        </div>
    </body>
    </html>
    """

    msg = EmailMessage()
    msg["Subject"] = (
        f"📊 Briefing Marchés - BTC: {btc['usd']:,.0f}$ | Fear: {fng['value']}"
    )
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg.set_content("Ce rapport nécessite un client compatible HTML.")
    msg.add_alternative(html_content, subtype="html")

    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        print(f"{Fore.GREEN}✔ E-mail envoyé avec succès à {RECEIVER_EMAIL}")
    except Exception as e:
        print(f"{Fore.RED}✘ Échec de l'envoi du mail : {e}")


def main():
    fng, cg = fetch_crypto_data()
    hype_px, hype_var = fetch_hype_hyperliquid()
    tradfi = fetch_tradfi()

    print("Génération et envoi du rapport...")
    envoyer_email(fng, cg, hype_px, hype_var, tradfi)


if __name__ == "__main__":
    main()