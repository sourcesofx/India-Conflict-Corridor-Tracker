import os
import json
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta


from src.config import DATA_DIR, DISTRICT_COORDS


class DataFetcher:
   """Handles data ingestion and filtering for reporting."""
   def __init__(self):
       self.data_dir = DATA_DIR


   def fetch_recent_high_risk_data(self, days: int = 7, min_score: float = 5.0) -> pd.DataFrame:
       articles = []
       for json_file in self.data_dir.glob("*.json"):
           if "twitter" in json_file.name.lower():
               continue
           try:
               with open(json_file, "r", encoding="utf-8") as f:
                   articles.extend(json.load(f))
           except:
               continue
              
       df = pd.DataFrame(articles)
       if df.empty:
           return df
          
       df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
       df['final_risk_score'] = pd.to_numeric(df['final_risk_score'], errors='coerce').fillna(0)
       cutoff_date = datetime.now() - timedelta(days=days)
       return df[(df['timestamp'] >= cutoff_date) & (df['final_risk_score'] >= min_score)].copy()


class LLMCompiler:
   """Handles Groq API integration and prompt engineering."""
   def __init__(self, api_key: str):
       self.api_key = api_key


   def build_data_summary(self, df: pd.DataFrame) -> str:
       """Builds a rich, structured, and dynamic summary for the LLM."""
       if df.empty:
           return "No significant incidents recorded in the period."


       total = len(df)
       high_risk = len(df[df['final_risk_score'] >= 8.0])
       avg_score = df['final_risk_score'].mean()
       districts = df['ner_locations'].explode().nunique()


       hotspots = df['ner_locations'].explode().value_counts().head(6)
       hotspot_str = "\n".join([f"- {loc}: {count} incidents" for loc, count in hotspots.items()])


       tactics = df['granular_incident_type'].value_counts().head(6)
       tactic_str = "\n".join([f"- {tactic}: {count}" for tactic, count in tactics.items()])
       top_incidents = (
           df.sort_values(by='final_risk_score', ascending=False)
           .drop_duplicates(subset=['title'])
           .head(6)
       )
       
       def get_cas_str(row):
           k = row.get('casualties_killed', [])
           i = row.get('casualties_injured', [])
           k_fmt = ", ".join(k) if isinstance(k, list) else str(k)
           i_fmt = ", ".join(i) if isinstance(i, list) else str(i)
           return f"Killed: [{k_fmt}] | Injured: [{i_fmt}]"
       
       incident_lines = []
       for _, row in top_incidents.iterrows():
           tactic = row.get('granular_incident_type', 'Unknown')
           score = row.get('final_risk_score', 0)
           title = str(row.get('title', ''))[:115]
           region = "J&K" if row.get('region') == 'jk' else "NE"
           cas_str = get_cas_str(row)
           incident_lines.append(f"- [{tactic} | Score: {score}] {title} ({region}) | {cas_str}")
       incident_str = "\n".join(incident_lines)


       top_actors = df['ner_actors'].explode().value_counts().head(6).index.tolist()
       actor_str = ", ".join(top_actors) if top_actors else "None prominently identified"


       if "ner_state_actors" in df.columns:
           top_state = df['ner_state_actors'].explode().value_counts().head(6).index.tolist()
           state_str = ", ".join(top_state) if top_state else "None prominently identified"
       else:
           state_str = "Data not available"


       return f"""OVERALL STATISTICS (Last 7 Days):
- Total Incidents (Score >= 5.0): {total}
- High-Risk Incidents (Score >= 8.0): {high_risk}
- Average Risk Score: {avg_score:.1f}
- Number of Active Districts: {districts}


TOP GEOGRAPHIC HOTSPOTS:
{hotspot_str}


TOP TACTICS OBSERVED:
{tactic_str}


MOST ACTIVE NON-STATE THREAT ACTORS:
{actor_str}


MOST ACTIVE STATE SECURITY FORCES:
{state_str}


TOP HIGH-RISK INCIDENTS:
{incident_str}
"""


   def generate_narrative(self, raw_data_summary: str) -> str:
       if not self.api_key:
           return "Analytical engine bypassed: GROQ_API_KEY missing."


       url = "https://api.groq.com/openai/v1/chat/completions"
       headers = {
           "Authorization": f"Bearer {self.api_key}",
           "Content-Type": "application/json"
       }
       prompt = f"""
       You are a Senior Military Intelligence Analyst specializing in South Asian internal security.


       CRITICAL INSTRUCTIONS:
       1. Base your entire analysis STRICTLY and SOLELY on the 'Raw Data Summary' provided below.
       2. DO NOT invent, assume, extrapolate, or hallucinate incidents, actors, or statistics.
       3. If data for a specific region, tactic, or actor is missing, explicitly state that it is not present in the reporting window.


       Analyze the following 7-day tactical incident summary for Jammu & Kashmir and Northeast India.


       Generate a formal intelligence brief using EXACTLY these four section headers. Do not alter the numbering or phrasing of these headers:


       1. EXECUTIVE SUMMARY
          - Provide a concise, high-level overview of the regional security situation.
          - Identify the primary threat vector (e.g., kinetic attacks, civil unrest, or state-led crackdowns) driving the data.


       2. SITUATIONAL OVERVIEW
          - Summarize the operational environment based only on the provided data.
          - Differentiate between the actions of Non-State Threat Actors (insurgents) and State Security Forces.
          - Highlight the main geographic hotspots.


       3. KEY DEVELOPMENTS AND TRENDS
          - Identify shifts in tactics, specifically comparing Kinetic operations (IEDs, gunfights, ambushes) versus Civil Unrest (protests, blockades).
          - Note any changes in operational tempo based on the data.


       4. MITIGATION STRATEGIES
          - Provide exactly 3 to 5 highly specific, actionable recommendations for security forces.
          - Avoid generic blanket statements. Name specific highways, districts, or tactics based on the data.
          - Use "- " for bullet points.


       Raw Data Summary:
       {raw_data_summary}


       Write in an authoritative, objective intelligence briefing style.
       FORMATTING RULES: Do not use markdown bolding (**), asterisks (*), or hashtags (#). Use plain text only. Ensure the 4 main headers start exactly with the number.
       """


       payload = {
           "model": "llama-3.3-70b-versatile",
           "messages": [{"role": "user", "content": prompt}],
           "temperature": 0.2
       }


       try:
           print("🧠 Querying Groq Intelligence Layer...")
           res = requests.post(url, json=payload, headers=headers, timeout=30)
           res.raise_for_status()
           return res.json()['choices'][0]['message']['content']
       except Exception as e:
           print(f"⚠️ Groq API Error: {e}")
           return f"Analytical engine connection failed: {e}"


class ChartGenerator:
   """Handles rendering and saving Plotly dark-mode visualizations."""
   def __init__(self, temp_dir):
       self.temp_dir = temp_dir
      
   def generate(self, df: pd.DataFrame) -> dict:
       print("📊 Rendering Dashboard Visualizations for PDF...")
       paths = {}
      
       df["lat"] = df["ner_locations"].apply(
           lambda x: next((DISTRICT_COORDS.get(l.lower(), (None, None))[0] for l in (x if isinstance(x, list) else []) if l.lower() in DISTRICT_COORDS), None)
       )
       df["lon"] = df["ner_locations"].apply(
           lambda x: next((DISTRICT_COORDS.get(l.lower(), (None, None))[1] for l in (x if isinstance(x, list) else []) if l.lower() in DISTRICT_COORDS), None)
       )
       map_df = df.dropna(subset=["lat", "lon"])


       if not map_df.empty:
           # === J&K Focused Heatmap ===
           jk_df = map_df[map_df["region"] == "jk"]
           if not jk_df.empty:
               fig_jk = px.scatter_mapbox(
                   jk_df, lat="lat", lon="lon", color="final_risk_score", size="final_risk_score",
                   title="Jammu & Kashmir - Geographic Hotspots",
                   mapbox_style="carto-darkmatter", zoom=6, center={"lat": 33.8, "lon": 75.0},
                   color_continuous_scale="reds", size_max=18
               )
               fig_jk.update_layout(template="plotly_dark", paper_bgcolor='#0C1B16', plot_bgcolor='#0C1B16', font=dict(color='#F0EAD9'), margin=dict(l=20, r=20, t=40, b=20), height=380)
               paths['jk_heatmap'] = str(self.temp_dir / "jk_heatmap.png")
               fig_jk.write_image(paths['jk_heatmap'], scale=2)


           # === Northeast Focused Heatmap ===
           ne_df = map_df[map_df["region"] == "ne"]
           if not ne_df.empty:
               fig_ne = px.scatter_mapbox(
                   ne_df, lat="lat", lon="lon", color="final_risk_score", size="final_risk_score",
                   title="Northeast India - Geographic Hotspots",
                   mapbox_style="carto-darkmatter", zoom=5, center={"lat": 25.5, "lon": 93.5},
                   color_continuous_scale="reds", size_max=18
               )
               fig_ne.update_layout(template="plotly_dark", paper_bgcolor='#0C1B16', plot_bgcolor='#0C1B16', font=dict(color='#F0EAD9'), margin=dict(l=20, r=20, t=40, b=20), height=380)
               paths['ne_heatmap'] = str(self.temp_dir / "ne_heatmap.png")
               fig_ne.write_image(paths['ne_heatmap'], scale=2)


       # Tactics Deployed
       tactics = df["granular_incident_type"].value_counts().reset_index()
       tactics.columns = ["Tactic", "Count"]
       tactics = tactics[~tactics["Tactic"].isin(["Unknown", "Other"])]
       fig_tactics = px.bar(tactics, x="Count", y="Tactic", orientation='h', title="Tactics Deployed")
       fig_tactics.update_layout(template="plotly_dark", paper_bgcolor='#0C1B16', plot_bgcolor='#0C1B16', font=dict(color='#F0EAD9'), margin=dict(l=20, r=20, t=40, b=20), height=300, yaxis={'categoryorder': 'total ascending'})
       fig_tactics.update_traces(marker_color="#C4663F")
       paths['tactics'] = str(self.temp_dir / "tactics.png")
       fig_tactics.write_image(paths['tactics'], scale=2)


       # Active Threat Actors
       actor_counts = df["ner_actors"].explode().value_counts().head(8).reset_index()
       actor_counts.columns = ["Actor", "Count"]
       fig_actors = px.bar(actor_counts, x="Actor", y="Count", title="Most Active Threat Actors")
       fig_actors.update_layout(template="plotly_dark", paper_bgcolor='#0C1B16', plot_bgcolor='#0C1B16', font=dict(color='#F0EAD9'), margin=dict(l=20, r=20, t=40, b=20), height=300)
       fig_actors.update_traces(marker_color="#6B9B7E")
       paths['actors'] = str(self.temp_dir / "actors.png")
       fig_actors.write_image(paths['actors'], scale=2)


       # Risk Level Composition
       risk_split = df["final_risk_level"].value_counts()
       fig_pie = px.pie(risk_split, names=risk_split.index, values=risk_split.values, title="Risk Level Composition", color_discrete_sequence=["#C4663F", "#1F3A2E", "#F0EAD9"])
       fig_pie.update_layout(template="plotly_dark", paper_bgcolor='#0C1B16', plot_bgcolor='#0C1B16', font=dict(color='#F0EAD9'), margin=dict(l=20, r=20, t=40, b=20), height=300)
       paths['pie'] = str(self.temp_dir / "pie.png")
       fig_pie.write_image(paths['pie'], scale=2)


       return paths
