import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast
import json
import os
import ast
from src.config import DISTRICT_COORDS, KEYWORDS
from src.red_flag_engine import RedFlagEngine
from src.report_generator import HybridIntelCompiler

st.set_page_config(page_title="India Conflict Corridor Tracker", page_icon="🛡️", layout="wide")

# ====================== BRANDING ======================
st.markdown("""
<style>
   /* Global Backgrounds */
   .main {background-color: #0C1B16;}
   .stApp {background-color: #0C1B16; color: #F0EAD9;}
   h1, h2, h3 {color: #F0EAD9; font-family: 'IBM Plex Serif', serif;}

   /* === EXECUTIVE SUMMARY METRICS - HIGH CONTRAST DARK MODE === */
   [data-testid="stMetric"] {
       background-color: #1F3A2E !important;
       border-radius: 10px !important;
       padding: 18px 14px !important;
       border: 2px solid #C4663F !important;
       box-shadow: 0 4px 12px rgba(0,0,0,0.4) !important;
   }
  
   [data-testid="stMetricLabel"] {
       color: #C4663F !important;
       font-size: 1.15rem !important;
       font-weight: 600 !important;
   }
   [data-testid="stMetricLabel"] * {
       color: #C4663F !important;
   }

   [data-testid="stMetricValue"] {
       color: #F0EAD9 !important;
       font-size: 2.8rem !important;
       font-weight: 700 !important;
       line-height: 1 !important;
   }
   [data-testid="stMetricValue"] * {
       color: #F0EAD9 !important;
   }

   /* Red flags */
   .red-flag {
       background-color: #C4663F;
       color: white;
       padding: 10px 14px;
       border-radius: 6px;
       margin: 4px 0;
       font-size: 1rem;
       font-weight: 500;
   }
</style>
""", unsafe_allow_html=True)

st.title("Conflict Corridor Incident Tracker")
st.caption("Jammu & Kashmir • Northeast India • Real-time Bureau Intelligence")

# ====================== DATA LOADING + DEDUPLICATION ======================
@st.cache_data(ttl=30)
def load_data() -> pd.DataFrame:
   import re 
   data_dir = Path("data/raw")
   clean_articles = []
   
   # Global sliding memory for the UI layer to catch cross-source syndication
   global_ui_seen_words = []

   for json_file in data_dir.glob("*.json"):
       if "twitter" in json_file.name.lower():
           continue
       try:
           with open(json_file, "r", encoding="utf-8") as f:
               data = json.load(f)
               for article in data:
                   # Failsafe 1: Force cast to string to prevent AttributeError on NoneType
                   title = str(article.get("title") or "").lower()
                   
                   if not title:
                       continue
                       
                   # Safely extract alphanumeric words (length >= 4)
                   words = set(re.findall(r'\b\w{4,}\b', title))
                   is_duplicate = False
                   
                   # Failsafe 2: Only attempt intersection if the set contains valid words
                   if words:
                       for seen_words in global_ui_seen_words:
                           if seen_words:
                               overlap = len(words.intersection(seen_words))
                               denominator = min(len(words), len(seen_words))
                               
                               # Failsafe 3: Guard against ZeroDivisionError
                               if denominator > 0 and (overlap / denominator) > 0.65:
                                   is_duplicate = True
                                   break
                   
                   if is_duplicate:
                       continue
                       
                   global_ui_seen_words.append(words)
                   
                   if "incident_type" not in article:
                       article["incident_type"] = "Other"
                   clean_articles.append(article)
       except Exception:
           continue

   df = pd.DataFrame(clean_articles)
   # Failsafe 4: Ensure column exists before datetime coercion
   if not df.empty and "timestamp" in df.columns:
       df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
   return df

df: pd.DataFrame = load_data()

# ====================== FILTERS & SPATIAL CORE ======================

jk_bounds = set([loc.lower() for loc in KEYWORDS["jk"]["locations"]])
ne_bounds = set([loc.lower() for loc in KEYWORDS["ne"]["locations"]])

col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
with col1:
   search = st.text_input("🔍 Search title, actors, or locations", "")
with col2:
   days = st.slider("Lookback (days)", 1, 60, 14)
with col3:
   region = st.selectbox("Region", ["All", "J&K", "Northeast"])
with col4:
   min_score = st.slider("Min risk score", 0.0, 10.0, 4.0, step=0.5)

cutoff = datetime.now() - timedelta(days=days)
filtered = cast(pd.DataFrame, df[df["timestamp"] >= cutoff].copy()) if not df.empty else df

def determine_regional_boundary(locs):
   if not isinstance(locs, list):
       return "other"
   locs_lower = [str(l).lower() for l in locs]
   if any(l in jk_bounds for l in locs_lower):
       return "jk"
   if any(l in ne_bounds for l in locs_lower):
       return "ne"
   return "other"

if not filtered.empty:
   filtered["derived_region"] = filtered["ner_locations"].apply(determine_regional_boundary)
   if region == "J&K":
       filtered = filtered[filtered["derived_region"] == "jk"]
   elif region == "Northeast":
       filtered = filtered[filtered["derived_region"] == "ne"]

if not filtered.empty:
   filtered = filtered[filtered["final_risk_score"] >= min_score]

if search and not filtered.empty:
   mask = (
       filtered["title"].str.contains(search, case=False, na=False) |
       filtered["ner_actors"].astype(str).str.contains(search, case=False, na=False) |
       filtered["ner_locations"].astype(str).str.contains(search, case=False, na=False)
   )
   filtered = filtered[mask]

# ====================== EXECUTIVE SUMMARY ======================
st.subheader("📊 Executive Summary")
m1, m2, m3, m4, m5 = st.columns(5)
m1.metric("Total Incidents", len(filtered))
m2.metric("High Risk", len(filtered[filtered["final_risk_level"] == "HIGH"]) if not filtered.empty else 0)
m3.metric("Avg Risk Score", f"{filtered['final_risk_score'].mean():.1f}" if not filtered.empty else "—")
m4.metric("Active Districts", filtered["ner_locations"].explode().nunique() if not filtered.empty else 0)
m5.metric("Active Actors", filtered["ner_actors"].explode().nunique() if not filtered.empty else 0)

# ====================== TABS ======================
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📈 Time Series", "🗺️ Heatmap", "🔥 Actors & Correlation", "📋 Latest Articles", "📄 Weekly Summary"])

with tab1:
   if not filtered.empty:
       filtered["hour"] = filtered["timestamp"].dt.floor("h")
       ts = filtered.groupby("hour").size().reset_index(name="count")
       fig = px.line(ts, x="hour", y="count", title="Incidents Over Time")
       fig.update_layout(template="plotly_dark", paper_bgcolor="#0C1B16")
       st.plotly_chart(fig, use_container_width=True)
   else:
       st.info("No timeline metrics matching selected parameters.")

with tab2:
   if not filtered.empty:
       loc_lists = filtered["ner_locations"].tolist()
       lats = []
       lons = []
      
       for loc_list in loc_lists:
           lat, lon = None, None
           if isinstance(loc_list, list):
               for loc in loc_list:
                   loc_lower = loc.lower()
                   if loc_lower in DISTRICT_COORDS:
                       lat, lon = DISTRICT_COORDS[loc_lower]
                       break
           lats.append(lat)
           lons.append(lon)
          
       filtered["lat"] = lats
       filtered["lon"] = lons
       map_df = filtered.dropna(subset=["lat", "lon"])
      
       if not map_df.empty:
           fig_map = px.scatter_mapbox(
               map_df, lat="lat", lon="lon", color="final_risk_score", size="final_risk_score",
               hover_name="title", hover_data=["source", "incident_type", "ner_actors"],
               title="Geographic Heatmap of Incidents (J&K + Northeast)",
               mapbox_style="carto-positron", zoom=5, center={"lat": 29.0, "lon": 78.0}, color_continuous_scale="reds"
           )
           fig_map.update_layout(height=650, margin={"r":0,"t":40,"l":0,"b":0}, paper_bgcolor="#0C1B16")
           st.plotly_chart(fig_map, use_container_width=True)
       else:
           st.info("No spatial data markers matched district coordinates.")
   else:
       st.info("No coordinates available for an empty selection layout.")

with tab3:
   st.subheader("🔥 Tactics & Threat Actor Analysis")
   if not filtered.empty:
       # ROW 1: Tactics and Risk Composition
       r1_col1, r1_col2 = st.columns(2)
       with r1_col1:
           tactics = filtered["granular_incident_type"].value_counts().reset_index()
           tactics.columns = ["Tactic", "Count"]
           tactics = tactics[~tactics["Tactic"].isin(["Unknown", "Other"])]
           fig_tactics = px.bar(tactics, x="Count", y="Tactic", orientation='h', title="Tactics Deployed")
           fig_tactics.update_layout(template="plotly_dark", paper_bgcolor="#0C1B16", yaxis={'categoryorder':'total ascending'})
           fig_tactics.update_traces(marker_color="#C4663F")
           st.plotly_chart(fig_tactics, use_container_width=True)

       with r1_col2:
           risk_split = filtered["final_risk_level"].value_counts()
           if not risk_split.empty:
               fig_pie = px.pie(risk_split, names=risk_split.index, values=risk_split.values, title="Risk Level Composition", color_discrete_sequence=["#C4663F", "#1F3A2E", "#F0EAD9"])
               fig_pie.update_layout(template="plotly_dark", paper_bgcolor="#0C1B16")
               st.plotly_chart(fig_pie, use_container_width=True)

       # ROW 2: Non-State Threat Actors vs State Security Forces
       r2_col1, r2_col2 = st.columns(2)
       with r2_col1:
           actor_counts = filtered["ner_actors"].explode().dropna().value_counts().head(10).reset_index()
           actor_counts.columns = ["Actor", "Count"]
           fig_actors = px.bar(actor_counts, x="Actor", y="Count", title="Most Active Threat Actors (Insurgents)")
           fig_actors.update_layout(template="plotly_dark", paper_bgcolor="#0C1B16")
           fig_actors.update_traces(marker_color="#6B9B7E")
           st.plotly_chart(fig_actors, use_container_width=True)

       with r2_col2:
           if "ner_state_actors" in filtered.columns:
               state_counts = filtered["ner_state_actors"].explode().dropna().value_counts().head(10).reset_index()
           else:
               state_counts = pd.DataFrame(columns=["Actor", "Count"])
              
           state_counts.columns = ["Actor", "Count"]
           fig_state = px.bar(state_counts, x="Actor", y="Count", title="Most Active State Security Forces")
           fig_state.update_layout(template="plotly_dark", paper_bgcolor="#0C1B16")
           fig_state.update_traces(marker_color="#F0EAD9")
           st.plotly_chart(fig_state, use_container_width=True)

       # ROW 3: Operational Links
       st.markdown("<hr style='border-color: #1F3A2E; margin-top: 15px; margin-bottom: 25px;'>", unsafe_allow_html=True)
       st.markdown("<p style='font-weight: bold; font-size: 1.1rem; margin-bottom: 0px;'>Verified Operational Links (Actor ➔ Tactic ➔ Target)</p>", unsafe_allow_html=True)
      
       links = []
       for row in filtered.to_dict('records'):
           perps = row.get("Perpetrator", []) if "Perpetrator" in row else row.get("perpetrator", [])
           tactic = row.get("granular_incident_type", "Unknown")
           targets = row.get("Target / Victim", []) if "Target / Victim" in row else row.get("victim_target", [])
          
           if isinstance(perps, str): perps = [perps]
           if isinstance(targets, str): targets = [targets]
           if not isinstance(perps, list): perps = []
           if not isinstance(targets, list): targets = []
          
           invalid_vals = ["—", "[]", "None", "nan", "Unknown", ""]
           valid_perps = [p for p in perps if p and str(p).strip() not in invalid_vals]
           valid_targets = [t for t in targets if t and str(t).strip() not in invalid_vals]
          
           if (valid_perps or valid_targets) and tactic not in ["Unknown", "Other"]:
               for p in valid_perps:
                   links.append({"source": str(p).title(), "target": tactic, "value": 1})
               for t in valid_targets:
                   links.append({"source": tactic, "target": str(t).title(), "value": 1})
                  
       if links:
           links_df = pd.DataFrame(links)
           sankey_data = links_df.groupby(['source', 'target']).size().reset_index(name='value')
           sankey_data = sankey_data[sankey_data['value'] >= 1]
           
           if not sankey_data.empty:
               all_nodes = list(pd.concat([sankey_data['source'], sankey_data['target']]).unique())
               node_dict = {node: i for i, node in enumerate(all_nodes)}
               sankey_data['source_idx'] = sankey_data['source'].map(node_dict)
               sankey_data['target_idx'] = sankey_data['target'].map(node_dict)
              
               fig_sankey = go.Figure(data=[go.Sankey(
                   node = dict(pad = 15, thickness = 15, line = dict(color = "black", width = 0.5), label = all_nodes, color = "#C4663F"),
                   link = dict(source = sankey_data['source_idx'], target = sankey_data['target_idx'], value = sankey_data['value'], color = "rgba(107, 155, 126, 0.3)")
               )])
               fig_sankey.update_layout(template="plotly_dark", paper_bgcolor="#0C1B16", plot_bgcolor="#0C1B16", margin=dict(l=10, r=10, t=25, b=10), height=380)
               st.plotly_chart(fig_sankey, use_container_width=True)
           else:
               st.info("No recurring operational patterns met the visual density threshold (Connection Count >= 2).")
       else:
           st.info("No active Actor or Target entities extracted in the current timeframe to generate links.")

       # ==========================================
       # ROW 4: Geographic Correlation Matrix
       # ==========================================
       st.markdown("<hr style='border-color: #1F3A2E; margin-top: 25px; margin-bottom: 25px;'>", unsafe_allow_html=True)
       st.markdown("<p style='font-weight: bold; font-size: 1.1rem; margin-bottom: 0px;'>Geographic Hotspots & Threat Actor Correlation Matrix</p>", unsafe_allow_html=True)

       matrix_data = []
       for row in filtered.to_dict('records'):
           actors = row.get("ner_actors", [])
           locs = row.get("ner_locations", [])
           if isinstance(actors, str): actors = [actors]
           if isinstance(locs, str): locs = [locs]
           
           for actor in actors:
               for loc in locs:
                   if actor and loc and str(actor).strip() and str(loc).strip():
                       matrix_data.append({"Actor": str(actor).title(), "District": str(loc).title()})
       
       if matrix_data:
           matrix_df = pd.DataFrame(matrix_data)
           heatmap_data = pd.crosstab(matrix_df['District'], matrix_df['Actor'])
           heatmap_data = heatmap_data.loc[(heatmap_data.sum(axis=1) > 0), (heatmap_data.sum(axis=0) > 0)]
           
           if not heatmap_data.empty:
               st.dataframe(heatmap_data, use_container_width=True)
           else:
               st.info("Insufficient actor/location overlap to generate correlation matrix.")
       else:
           st.info("No corresponding Actor and Location data extracted in the current timeframe.")

with tab4:
   if not filtered.empty:
       latest = filtered.sort_values(by="timestamp", ascending=False).head(20).copy()
      
       def safe_format(col_primary, col_fallback):
           if col_primary in latest.columns:
               return latest[col_primary].apply(lambda x: ", ".join(x).title() if isinstance(x, list) else str(x))
           elif col_fallback in latest.columns:
               return latest[col_fallback].apply(lambda x: ", ".join(x).title() if isinstance(x, list) else str(x))
           else:
               return pd.Series(["—"] * len(latest), index=latest.index)

       # === Smart Formatter ===
       def format_casualties(val):
           if isinstance(val, str) and "{'killed'" in val:
               try: val = ast.literal_eval(val)
               except: pass
           if isinstance(val, dict):
               items = val.get("killed", []) + val.get("injured", [])
               return ", ".join(items).title() if items else "—"
           elif isinstance(val, list):
               return ", ".join(val).title() if val else "—"
           elif isinstance(val, str):
               return val.title() if val.strip() not in ["[]", "{}", "None", "nan", ""] else "—"
           return "—"

       latest["Render_Perp"] = safe_format("Perpetrator", "perpetrator")
       latest["Render_Target"] = safe_format("Target / Victim", "victim_target")
       
       cas_col = "casualties_killed" if "casualties_killed" in latest.columns else "Casualties_Killed"
       if cas_col in latest.columns:
           latest["Render_Casualties"] = latest[cas_col].apply(format_casualties)
       else:
           latest["Render_Casualties"] = "—"
      
       st.dataframe(
           latest[["timestamp", "source", "title", "granular_incident_type", "Render_Perp", "Render_Target", "Render_Casualties", "final_risk_score", "url"]],
           use_container_width=True, hide_index=True,
           column_config={
               "timestamp": "Time", "granular_incident_type": "Tactic",
               "Render_Perp": "Perpetrator", "Render_Target": "Target / Victim", 
               "Render_Casualties": "Casualties",
               "final_risk_score": "Risk Score", "url": st.column_config.LinkColumn("Source Link", display_text="🔗 View Original")
           }
       )
   else:
       st.info("Database match list empty.")

with tab5:
   st.subheader("📄 Executive Intelligence Briefings")
   st.markdown("<p style='color: #6B9B7E;'>Generate AI-synthesized PDF dossiers or export raw CSV metrics for the trailing 7-day reporting window.</p>", unsafe_allow_html=True)
   st.write("")

   col_pdf, col_csv = st.columns(2)
  
   with col_pdf:
       st.markdown("### 🧠 AI Intelligence Dossier")
       st.caption("Compiles all metrics, charts, and headlines into a boardroom-ready PDF with LLM-generated strategic analysis.")
      
       if st.button("Generate & Download PDF Report", use_container_width=True, type="primary"):
           with st.spinner("Querying Groq Llama-3.3 & Rendering Dark-Mode Charts (This takes ~15 seconds)..."):
               try:
                  
                   compiler = HybridIntelCompiler()
                   pdf_file_path = compiler.compile_weekly_brief()
                  
                   if pdf_file_path and os.path.exists(pdf_file_path):
                       with open(pdf_file_path, "rb") as pdf_file:
                           pdf_bytes = pdf_file.read()
                          
                       st.success("✅ Dossier Compiled Successfully!")
                       st.download_button(
                           label="📥 Download PDF Dossier",
                           data=pdf_bytes,
                           file_name=pdf_file_path.name,
                           mime="application/pdf"
                       )
                   else:
                       st.error("⚠️ Insufficient high-risk kinetic data in the last 7 days to generate a formal brief.")
               except Exception as e:
                   st.error(f"System Error during compilation: {e}")

   with col_csv:
       st.markdown("### 📊 Raw Data Export")
       st.caption("Extracts the raw programmatic DataFrame for external ingestion or machine-learning analysis.")
      
       week_ago = datetime.now() - timedelta(days=7)
       weekly = df[df["timestamp"] >= week_ago]
      
       if not weekly.empty:
           csv_data = weekly.to_csv(index=False).encode()
           st.download_button(
               label="📥 Download Weekly CSV",
               data=csv_data,
               file_name=f"caesura_raw_intel_{datetime.now().strftime('%Y%m%d')}.csv",
               mime="text/csv",
               use_container_width=True
           )
       else:
           st.info("No data available for the trailing 7 days.")

# ====================== RED ALERT LOGIC ======================
st.subheader("🚨 Tactical Red Flag Alerts (24hr Window)")

engine = RedFlagEngine(time_window_hours=24, trigger_threshold=5)
red_flags = engine.evaluate(df)

alert_triggered = False

if red_flags:
   for district_str, triggering_events in red_flags.items():
       st.markdown(
           f'<div class="red-flag">🔴 <b>ACTION REQUIRED:</b> {len(triggering_events)} unique, severe incidents centered in <b>{district_str.upper()}</b> within the last 24 hours.</div>',
           unsafe_allow_html=True
       )
       with st.expander(f"🔍 Drilldown: View {len(triggering_events)} Root Intelligence Factors for {district_str.title()}"):
           for _, row in triggering_events.iterrows():
               tactic = row.get("granular_incident_type", "Operational Activity")
               title = row.get("title", "No Headline Available")
               source = row.get("source", "OSINT Source")
               st.markdown(f"- **[{source}] {tactic}**: {title}")
       alert_triggered = True

if not alert_triggered:
   st.markdown(
       '<div style="color: #6B9B7E; font-weight: 500; padding: 10px; border-radius: 4px; background-color: #0C1B16;">✅ All monitored hot-spots are within stable operational variances. No red flags triggered.</div>',
       unsafe_allow_html=True
   )

st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} • Powered by 26 sources + Custom SpaCy NER + Lexical Deduplication")