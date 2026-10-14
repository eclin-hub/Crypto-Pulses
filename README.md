# ⚡ CryptoPulse — Automated Cross-Asset, Macro & Crypto Morning Briefing

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)
![GitHub Actions](https://img.shields.io/badge/CI%2FCD-GitHub_Actions-2088FF?logo=github-actions&logoColor=white)
![Gemini API](https://img.shields.io/badge/AI-Gemini_3.6_Flash-8E75B2?logo=google&logoColor=white)
![Hyperliquid](https://img.shields.io/badge/DEX-Hyperliquid_API-00D1B2)
![Resend](https://img.shields.io/badge/Email-Resend_API-black)
![License](https://img.shields.io/badge/License-MIT-green)

**CryptoPulse** is a serverless Python automation pipeline that aggregates real-time **Crypto & TradFi market metrics**, **multi-source geopolitical/macro RSS feeds**, and a **daily legal brief**, synthesized by **Google Gemini 3.6 Flash** and delivered every morning as a clean HTML newsletter via **Resend** and **GitHub Actions**.

---

## 🎯 What CryptoPulse Tracks Daily

Instead of checking 10 different tabs every morning, **CryptoPulse** compiles a unified cross-asset & fundamental snapshot:

### 1. 📈 Cross-Asset Market Data
* **Cryptocurrencies (CoinGecko API):** Live prices & 24h variations for **Bitcoin (BTC)** and **Ethereum (ETH)**.
* **On-Chain / DEX Focus (Hyperliquid API):** Native tracking of **HYPE** token price and 24h performance.
* **Macro & Commodities (Yahoo Finance):** **S&P 500**, **Gold (XAU)**, and **WTI Crude Oil** to monitor global risk-on/risk-off sentiment.

### 2. 📰 Curated Multi-Asset News (RSS Aggregation)
* **Geopolitics:** *BBC World News*
* **Macroeconomics & Central Banks (Fed):** *Dow Jones / MarketWatch*
* **Crypto & Digital Assets:** *The Block*

### 3. ⚖️ Daily Legal & Regulatory Capsule (`legal_briefs.py`)
* Injects a rotating daily legal/regulatory concept or case study alongside the market briefing.

### 4. 🧠 AI Executive Synthesis & Resilient Delivery
* **LLM Analysis:** Uses **Gemini 3.6 Flash** to cross-reference price action with macro/crypto headlines and output a structured morning briefing.
* **Production-Grade Reliability:** Built-in exponential backoff & **retry logic** to handle API rate limits or server overload seamlessly before dispatching via **Resend API**.

---

## 🏗️ System Architecture

~~~mermaid
graph LR
    A[⏰ GitHub Actions Cron] -->|Triggers Daily| B(🐍 CryptoPulse.py)
    
    subgraph Data Sources
        C1[🦎 CoinGecko: BTC, ETH] --> B
        C2[💧 Hyperliquid: HYPE] --> B
        C3[📊 Yahoo Finance: S&P500, Gold, WTI] --> B
        D[📰 RSS: BBC, MarketWatch, The Block] --> B
        L[⚖️ legal_briefs.py] --> B
    end

    B -->|Prompt + Context| E{🧠 Gemini 3.6 Flash<br/>+ Retry Logic}
    E -->|Executive Analysis| B
    B -->|HTML Newsletter| F[📩 Resend API]
    F -->|Morning Delivery| G((📬 User Inbox))
~~~

---

## 📂 Repository Structure

~~~text
├── .github/workflows/   # GitHub Actions cron configuration (daily execution)
├── CryptoPulse.py       # Main pipeline: API fetching, RSS parsing, Gemini synthesis & Resend dispatch
├── legal_briefs.py      # Module providing the daily legal/regulatory briefing section
├── debug_news.py        # Diagnostic & testing utility for RSS feeds and news parsing
└── README.md            # Project documentation
~~~

---

## 🚀 Getting Started (Local Setup)

### 1. Clone the repository
~~~bash
git clone https://github.com/eclin-hub/CryptoPulse.git
cd CryptoPulse
~~~

### 2. Install dependencies
~~~bash
pip install requests feedparser yfinance google-genai resend
~~~

### 3. Set up Environment Variables
Export your API keys or configure a `.env` file locally (never commit your keys):
~~~env
GEMINI_API_KEY="your_google_gemini_api_key"
RESEND_API_KEY="your_resend_api_key"
~~~

### 4. Run or test the pipeline
~~~bash
# Test RSS feeds and news aggregation independently
python debug_news.py

# Run the full morning briefing pipeline
python CryptoPulse.py
~~~

---

## ⚙️ Serverless Automation (GitHub Actions)

This project runs automatically every morning at **zero cost** using GitHub Actions runners:
1. Go to your repository **Settings** > **Secrets and variables** > **Actions**.
2. Add `GEMINI_API_KEY` and `RESEND_API_KEY` under **Repository secrets**.
3. The workflow triggers automatically on schedule or manually via `workflow_dispatch` in the **Actions** tab.

---

## 👤 Author

**Lin Bahic**  
*Master 1 in Analysis and Economic Policy (APE) — Quantitative Finance, Macro & Econometrics*  
🔗 [GitHub Profile](https://github.com/eclin-hub)
