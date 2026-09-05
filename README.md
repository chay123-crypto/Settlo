# ⚡ Settlo — AI Settlement Reconciliation & Exception Analyst

> **Automated Multi-Source Reconciliation, Bounded AI Exception Analysis & Forward Cash Liquidity Forecasting for Modern Finance Ops.**

Built for the **Razorpay AI Buildathon 2026 — Track 04: AI Finance Controller**.

Live Link : https://settlo.streamlit.app/

---

## 📌 Executive Summary

Every e-commerce merchant using payment gateways like Razorpay faces a major operational challenge: merchant website orders, gateway transaction records (with hidden fee tiers and GST), bank deposit credits, and customer refunds rarely line up seamlessly. Finance teams spend hundreds of hours every month in Excel, manually cross-referencing messy CSVs to spot missing funds, fee overcharges, or uncollected bank deposits.

**Settlo** solves this by closing the finance-ops loop across multi-source datasets with **100% deterministic accuracy**, **sub-3-second throughput**, **zero financial hallucination**, and **forward liquidity forecasting**.

### 🌟 Key Highlights
- **100% Precision & Recall Benchmark**: Reconciles a 192-record multi-source synthetic batch in **2.47 seconds** with zero false positives.
- **4-Pass Deterministic Reconciliation Engine**: Code decides the money. Math is 100% reproducible down to the paisa (stored as integer `paise`).
- **12-Code Exception Taxonomy**: Automatically categorizes mismatches into clean, actionable issue types (`FEE_MISMATCH`, `AMOUNT_MISMATCH`, `MISSING_SETTLEMENT`, `DUPLICATE_PAYMENT`, `DELAYED_SETTLEMENT`).
- **Bounded AI Assistant ("Ask Settlo AI")**: Powered by Groq (Llama 3.3 70B) with tool calling. Restricted to 4 read-only backend tools for zero-hallucination investigation.
- **Forward Cash Liquidity Forecaster**: 14-day forward liquidity projection based on SLA settlement windows and pending match states.
- **Dual-Mode Razorpay Integration**: Operates seamlessly in local mock mode or live with Razorpay Test Mode API credentials (`rzp_test_...`).
- **Custom Customer File Upload Portal**: Allows merchants to upload their own custom CSV files directly from the dashboard.

---

## 🏗️ System Architecture

```
                               ┌─────────────────────────┐
                               │   Multi-Source CSVs     │
                               │  - Orders               │
                               │  - Razorpay Payments    │
                               │  - Bank Settlements     │
                               │  - Customer Refunds     │
                               └────────────┬────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │ Pass 1: Row Validation  │ (Schema & Field Sanitization)
                               └────────────┬────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │ Pass 2: Exact Matching  │ (Order ID + Net Paise Match)
                               └────────────┬────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │ Pass 3: Refund-Adjusted │ (Gross - Fee - Tax - Refund)
                               └────────────┬────────────┘
                                            │
                                            ▼
                               ┌─────────────────────────┐
                               │ Pass 4: Composite Window│ (Date ±3 days + Net Amount)
                               └────────────┬────────────┘
                                            │
                   ┌────────────────────────┴────────────────────────┐
                   ▼                                                 ▼
     ┌───────────────────────────┐                     ┌───────────────────────────┐
     │ Exact Matches (Finalized) │                     │ Exception Queue Taxonomy  │
     └───────────────────────────┘                     └─────────────┬─────────────┘
                                                                     │
                                                                     ▼
                                                       ┌───────────────────────────┐
                                                       │  "Ask Settlo AI" Agent    │
                                                       │  (Groq + Bounded Tools)   │
                                                       └───────────────────────────┘
```

---
## 🛠️ Tech Stack

- **Frontend:** Streamlit, Plotly (Dynamic Cash Forecasting Charts)
- **Backend:** FastAPI, Python 3.10+, Uvicorn
- **AI / LLM:** Groq API (Qwen 3.8 27B/ GPT-OSS-120B for zero-hallucination tool calling)
- **Integrations:** Razorpay REST API (Live Test Mode + Local Mock Mode)
- **Data & Testing:** Pandas, Pytest (100% deterministic test coverage)

## 🎯 Ground-Truth Benchmark Results

Settlo includes an independent ground-truth evaluation framework (`scripts/evaluate.py`) that benchmarks pipeline predictions against a held-out manifest (`scenario_manifest.csv`).

```text
============================================================
BATCH: batch_5717abb5
============================================================
Total input records:        192
Invalid rows:                8
Eligible records:            184
Exact matches:               142
Probable matches:            0
Exception count:             50
------------------------------------------------------------
MATCHING CONFUSION MATRIX:
  True Positive (Match | Match):        142
  False Positive (Match | Non-Match):    0
  False Negative (Non-Match | Match):    0
  True Negative (Non-Match | Non-Match): 50
------------------------------------------------------------
Precision: 142/142 = 1.000 (100%)
Recall:    142/142 = 1.000 (100%)
Exception Classification Accuracy: 50/50 = 1.000 (100%)
Match Rate:          74.0%
Manual Review Rate:  26.0%
Processing Duration: 2.472s
============================================================
EXCEPTION ACCURACY BREAKDOWN:
  AMBIGUOUS_MATCH: 6/6 (1.00)
  AMOUNT_MISMATCH: 8/8 (1.00)
  DELAYED_SETTLEMENT_FLAG_OPTIONAL: 10/10 (1.00)
  DUPLICATE_PAYMENT: 6/6 (1.00)
  FEE_MISMATCH_OR_TAX_MISMATCH: 12/12 (1.00)
  INPUT_VALIDATION_ERROR: 8/8 (1.00)
  MISSING_SETTLEMENT: 10/10 (1.00)
============================================================
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites
- Python 3.10+
- Git

### 2. Installation
```powershell
# Clone the repository
git clone https://github.com/YOUR_USERNAME/Settlo.git
cd Settlo

# Create a virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Copy the `.env.example` file to `.env`:
```powershell
copy .env.example .env
```

To enable live Groq LLM Q&A, paste your Groq API key in `.env`:
```env
LLM_API_KEY=gsk_your_groq_api_key_here
LLM_PROVIDER=groq
LLM_MODEL=llama-3.3-70b-versatile
```

To enable live Razorpay Test API connection, paste your Razorpay credentials in `.env`:
```env
RAZORPAY_KEY_ID=rzp_test_your_key_id
RAZORPAY_KEY_SECRET=your_key_secret
```
*(If keys are left blank, Settlo operates automatically in local Mock Mode).*

---

## 💻 Running the Application

### Option A: Launch the Streamlit Web Interface (Recommended)
```powershell
streamlit run frontend/streamlit_app.py
```
Open **[http://localhost:8501](http://localhost:8501)** in your browser to access the dashboard.

### Option B: Launch FastAPI Backend Server
```powershell
uvicorn backend.main:app --reload --port 8000
```
Interactive API documentation available at **[http://localhost:8000/docs](http://localhost:8000/docs)**.

### Option C: Run Benchmark Evaluation
```powershell
python scripts/evaluate.py
```

### Option D: Run Automated Test Suite
```powershell
pytest
```

---

## 📂 Project Directory Structure

```text
Settlo/
├── backend/
│   ├── main.py              # FastAPI Web Server
│   ├── pipeline.py          # Master batch execution pipeline
│   ├── matcher.py           # 4-pass deterministic reconciliation engine
│   ├── classifier.py        # 12-code exception taxonomy classifier
│   ├── validator.py         # Row validation & error isolation
│   ├── agent.py             # Bounded LLM tool-calling agent (Groq)
│   ├── agent_tools.py       # Read-only tool execution functions
│   ├── forecaster.py        # Forward cash liquidity forecaster
│   ├── razorpay_client.py   # Dual-mode Razorpay REST client
│   ├── config.py            # Environment configuration settings
│   └── audit.py             # Hash-linked audit event logger
├── frontend/
│   └── streamlit_app.py     # Streamlit web dashboard & customer upload portal
├── scripts/
│   ├── generate_realistic_data.py  # 192-record dataset generator
│   ├── evaluate.py                 # Ground-truth evaluation script
│   └── fetch_razorpay_live.py      # Live Razorpay API data fetcher
├── tests/                   # Automated unit test suite (20 tests)
├── data/
│   ├── input/               # Demo CSV datasets
│   └── output/              # Reconciled results & audit CSVs
├── .env.example             # Environment template without secrets
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for details.
