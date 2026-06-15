# 🛡️ India Conflict Corridor Tracker

**Real-Time Intelligence Pipeline for Jammu & Kashmir and Northeast India**

A hybrid intelligence monitoring system and tactical situational awareness dashboard that is designed to detect kinetic incidents, civil unrest, and security developments across Jammu & Kashmir and Northeast India. 

Built for operational monitoring and strategic analysis. This project serves as an autonomous, end-to-end intelligence pipeline that addresses the primary pitfalls of raw OSINT collection: **high-volume noise, state duplication, media echo chambers, and localized alert dilution.**


## Why I Built This

As a senior intelligence analyst transitioning into technical OSINT and AI-augmented analysis, I wanted to explore how automation and modern NLP/LLM tooling could meaningfully augment the intelligence cycle.

The goal was to build a system that handles the high-volume, repetitive parts of OSINT collection and initial triage, allowing analysts to focus on higher-order judgment, context, and deeper strategic thinking. I also wanted to make a practical, open tool available to the broader OSINT, security research, journalism, and academic community working on conflict dynamics in South Asia.

The India Conflict Corridor Intelligence Pipeline represents my first portfolio project that leverages automation and AI to scale and streamline the Intelligence analyst workflow. I hope that you find this project useful to your own research and it contributes towards a better understanding of the dynamics of (in)security and civil unrest in Jammu and Kashmir and Northeast India. 

## 📌 Architectural Overview

The platform features a hybrid ingestion architecture running parallel web scrapers, parses unstructured data through a localized Natural Language Processing (NLP) pipeline, and utilizes cross-district lexical deduplication to feed a real-time analytics dashboard and an open-source LLM-driven intelligence brief compiler.

India Conflict Corridor Tracker is an end-to-end intelligence pipeline that combines:

- **Automated data collection** from 26+ news sources using a hybrid Playwright + RSS architecture
- **Advanced NLP classification** with custom SpaCy NER, role extraction (perpetrator/victim), and granular incident typing
- **Interactive operational dashboard** with geospatial mapping, threat actor analysis, and red flag alerting
- **Automated intelligence reporting** powered by open-source LLM, featuring dual regional heatmaps and verified incident logs

The system prioritizes **relevance and low noise**, making it suitable for security analysts, academic researchers, journalists and law enforcement professionals focused on South Asian conflict dynamics.

---

### ✨ Key Operational Features:

The India Conflict Corridor Tracker is designed to cut through OSINT noise and provide immediate, analyst-ready situational awareness across Jammu & Kashmir and Northeast India.

**Autonomous Multi-Source Collection** Continuous ingestion from 26+ regional news outlets and RSS feeds, ensuring analysts never miss a localized flashpoint or localized security development.

**Real-Time Situational Awareness** - An interactive command dashboard featuring district-level geographic heatmaps, temporal trendlines, and 24-hour tactical Red Flag alerts for rapidly escalating hotspots.

**Threat Actor Network Mapping** Dynamic visualisations including sankey operational link diagrams that visualize the complex relationships between Non-State Threat Actors, State Security Forces, deployed tactics, and targeted districts. 

**Granular Conflict Differentiation** Strict operational categorization that seamlessly separates High-Risk Kinetic operations (gunfights, IEDs, ambushes) from systemic Civil Unrest (economic blockades, mass protests, shutdowns).

**Automated Intelligence Briefs** One-click, LLM-generated intelligence briefs that compile strategic narratives, verified incident logs, and dual-regional threat assessments into standardized, distributable PDFs.

#### 🔥 Key Engineering Guardrails

This pipeline incorporates several deliberate engineering decisions to maximize signal while minimising noise and analyst fatigue:

**1. Weighted Frequency Multi-Pass Classification**  
Traditional regex-based systems often suffer from binary matching. This pipeline uses a frequency-aware scorer that applies a **2.0x multiplier** to tactical keywords found in article titles and a standard **1.0x weight** across the full body text. This significantly reduces false positives from background or tangential mentions.

**2. Multi-Layer Lexical Deduplication**  
To combat media echo chambers and multi-publisher syndication, the system applies lexical deduplication at two levels:
- Real-time batch deduplication during scraping
- Global deduplication across the entire data lake (65% word overlap threshold)  
This ensures that a single event reported across dozens of outlets is treated as one operational entity.

**3. Hierarchical Spatial Epicenter Anchoring**  
The dashboard uses a “Title Trump Card” + “Dateline Fallback” logic to correctly attribute incidents to the right district, even when articles contain boilerplate reporting language from regional bureaus.

**4. Split-Threshold Alerting + Lenient Age Filtering**  
- Kinetic events require a minimum risk score of **8.0**, while Civil Unrest events trigger at **7.5** to balance sensitivity with alert fatigue.
- The system uses **lenient article age filtering** — articles with unparseable dates are retained rather than discarded. This prevents breaking news from being lost due to HTML parsing issues.

**5. Dual-Layer Data Architecture (Live + Historical)**  
The pipeline maintains both a real-time operational view (via the dashboard) and a structured historical archive with monthly partitioned CSVs. This enables both immediate tactical awareness and longer-term trend analysis.

---

#### 🔥 Algorithmic Risk Scoring Matrix

To guarantee deterministic and transparent threat evaluation, the RiskClassifier employs a strict mathematical matrix to assign Risk Scores (0.0 to 10.0) and Risk Levels (LOW, MEDIUM, HIGH).

**Baseline Tactical Allocation** If an incident contains verified conflict context or casualties, it receives a strict baseline score based on its tactical classification:

8.0 (HIGH): Assigned to direct Kinetic operations (e.g., Gunfights, IEDs, Ambushes, Search Operations).

7.5 (MEDIUM/HIGH): Assigned to severe Civil Unrest events (e.g., Blockades, Riots, Arson).

**Threat Actor Multiplier** (+2.0): If the NLP engine successfully extracts a verified Non-State Threat Actor, explicit Perpetrator, or Claim of Responsibility, the incident receives a +2.0 multiplier (capped at a maximum score of 10.0) to reflect the escalated strategic threat.

**The Noise Floor** (4.0 - 3.0): If an article mentions a tactical keyword but lacks explicit casualties or structural conflict context, it is aggressively downgraded to a 4.0. Articles falling completely outside the regional bounding boxes default to < 3.0 (LOW risk).

**False-Positive Deflection** A proactive soft-context blacklist acts as a circuit breaker. If an article mentions "troops" in the context of a local sports tournament, the engine instantly strips its high-risk eligibility, preserving the integrity of the analyst's dashboard.

## 🏗️ System Architecture

News Sources (26) + RSS Feeds
↓
Hybrid Scraper (Playwright + RSS + Trafilatura)
↓
Risk Classifier (SpaCy + Custom Rules + Geographic Gating)
↓
Data Lake + Real-time + Global Lexical Deduplication
↓
┌──────────────────────┬──────────────────────┐
│   Streamlit Dashboard│  Report Generator    │
│   (Real-time View)   │  (LLM + PDF Export)  │
└──────────────────────┴──────────────────────┘


---

## 🛠️ Tech Stack

| Layer                    | Technology                                      |
|--------------------------|-------------------------------------------------|
| Web Scraping             | Playwright (Async) + Trafilatura                |
| RSS Ingestion            | feedparser + requests                           |
| NLP & Classification     | SpaCy + Custom EntityRuler + Regex              |
| Dashboard                | Streamlit + Plotly                              |
| Reporting                | Groq (Llama 3.3) + ReportLab                    |
| Data Processing          | Pandas                                          |
| Visualization            | Plotly (Mapbox, Sankey, Heatmaps)               |

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Playwright browsers installed
- Groq API key (for intelligence brief generation)

### Installation

```bash
git clone https://github.com/sourcesofx/conflict-corridor.git
cd conflict-corridor

python -m venv venv
source venv/bin/activate          # On Windows: venv\Scripts\activate

pip install -r requirements.txt
playwright install

Environment Variables
Create a .env file in the root directory: GROQ_API_KEY=your_groq_api_key_here

##▶️ Usage
1. Run the Full Pipeline : python run_scraper.py

This starts the hybrid scraper (Playwright + RSS), classifies articles, and saves results to data/raw/.

2. Launch the Dashboard

streamlit run src/dashboard.py

3. Generate Weekly Intelligence Brief
The weekly intelligence brief is fully integrated into the dashboard:

To generate an AI-Intel Brief you can navigate to Tab 5: Weekly Summary and click "Generate & Download PDF Report"

The system will automatically:

Aggregate the last 7 days of high-value incidents
Generate dual regional heatmaps (Jammu & Kashmir + Northeast India)
Produce an LLM-powered strategic narrative
Create verified Kinetic and Civil Unrest logs (Top 5 Incidents)
Output a professional dark-mode PDF brief


##📊 Dashboard Highlights

Executive summary with key metrics
Interactive geographic heatmap
Non-State Threat Actors vs State Security Forces analysis
Sankey operational link diagrams
24-hour Tactical Red Flag Alerts with lexical deduplication
Searchable latest incidents table
One-click generation of weekly intelligence briefs through the Dashboard UI.

##📄 Intelligence Brief Output
Generated briefs include:

Executive Summary
Situational Overview (with differentiation between Non-State and State actors)
Key Developments & Trends
Mitigation Strategies
Verified Critical Kinetic Log (Top 5)
Verified Civil Unrest Log (Top 5)
Dual Regional Heatmaps (J&K + Northeast)

##⚠️ Limitations & Notes**

The classifier is intentionally strict to prioritize relevance and reduce noise.
LLM-generated narratives should be treated as analytical aids, not definitive intelligence.
Geographic and threat actor coverage is limited to locations and organisations defined in keywords.json.
Threat Actor Network Mapping ocassionally provides some false positive results and mis-classification of tactics due to limitations of using open-source NLP models. This will be refined through further development by incorporating hybrid-architecture that uses LLM to parse operational details from main body of articles ingested by the scraper and output the results in JSON format to populate the datalake. 
Some news sources may change structure or block scraping over time.

##⚠️ Tactical System Disclaimers & Scope
Geographic Constraints: Entity extraction boundaries are strictly governed by the semantic thresholds structured in keywords.json.

Analytical Intent: LLM contextual generations function as advisory cognitive summaries. Tactical operational assessments should rely on the verified structural log logs.

Upstream Resilience: Scraping loops utilize defensive element lookups, but are subject to variance if primary newspaper DOM paths or security frameworks undergo major re-platforming.

##🗺️ Future Roadmap

Automated scheduling and email delivery of briefs
Improved red flag clustering logic
Historical trend analysis module
Docker containerization
Unit tests and CI/CD pipeline

##📜 License
This project is released under a modified MIT License with the following conditions:

Allowed: Personal use, academic research, education, and non-commercial projects (with proper attribution).
Not Allowed: Commercial use without express written permission from the developer.

For commercial licensing inquiries, please contact the author.
Full license text is available in the LICENSE file.

