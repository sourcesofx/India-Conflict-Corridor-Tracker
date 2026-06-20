import pandas as pd
from datetime import datetime, timedelta
from src.utils import lexical_deduplicate
from src.config import MIN_RISK_SCORE, CIVIL_UNREST_SCORE
from src.tactic_classifier import KINETIC_PATTERNS, UNREST_PATTERNS

_NON_ALERTING_TACTICS = {"Search Operation"}
KINETIC_ALERT_TACTICS = {t for _, t in KINETIC_PATTERNS} - _NON_ALERTING_TACTICS
UNREST_ALERT_TACTICS = {t for _, t in UNREST_PATTERNS}


class RedFlagEngine:
   """Evaluates intelligence data against threshold parameters to trigger tactical alerts."""
  
   def __init__(self, time_window_hours: int = 24, trigger_threshold: int = 5):
       self.time_window = timedelta(hours=time_window_hours)
       self.trigger_threshold = trigger_threshold


   def _extract_epicenter(self, row) -> str:
       """
       Critical Architectural Guardrail: Hierarchical Spatial Anchoring
       Never uses .explode(). Evaluates Title Trump Card -> Dateline Zone -> Fallback.
       """
       locs = row.get('ner_locations', [])
       if not isinstance(locs, list) or len(locs) == 0:
           return 'unmapped'
          
       title_lower = str(row.get('title', '')).lower()
       dateline_zone = str(row.get('content', ''))[:250].lower()
      
       # Priority 1: TITLE TRUMP CARD
       best_title_loc = None
       min_title_idx = float('inf')
       for loc in locs:
           loc_lower = str(loc).lower()
           idx = title_lower.find(loc_lower)
           if idx != -1 and idx < min_title_idx:
               min_title_idx = idx
               best_title_loc = loc_lower
              
       if best_title_loc:
           return best_title_loc
          
       # Priority 2: DATELINE FALLBACK
       best_body_loc = None
       min_body_idx = float('inf')
       for loc in locs:
           loc_lower = str(loc).lower()
           idx = dateline_zone.find(loc_lower)
           if idx != -1 and idx < min_body_idx:
               min_body_idx = idx
               best_body_loc = loc_lower
              
       if best_body_loc:
           return best_body_loc
          
       # Priority 3: ABSOLUTE FALLBACK
       return str(locs[0]).lower()


   def evaluate(self, df: pd.DataFrame) -> dict:
       """
       Processes the dataframe and returns a dictionary of triggering districts.
       Format: { "district_name": DataFrame_of_triggering_events }
       """
       if df.empty:
           return {}


       alert_cutoff = datetime.now() - self.time_window
       recent_incidents = df[df["timestamp"] >= alert_cutoff].copy()

       tactic = recent_incidents["granular_incident_type"].astype(str)
       score = pd.to_numeric(recent_incidents["final_risk_score"], errors="coerce")

       if "needs_review" in recent_incidents.columns:
           not_uncertain = ~recent_incidents["needs_review"].fillna(False).astype(bool)
       else:
           not_uncertain = pd.Series(True, index=recent_incidents.index)

       kinetic_hit = tactic.isin(KINETIC_ALERT_TACTICS) & (score >= MIN_RISK_SCORE)
       unrest_hit = tactic.isin(UNREST_ALERT_TACTICS) & (score >= CIVIL_UNREST_SCORE)

       high_risk_recent = recent_incidents[(kinetic_hit | unrest_hit) & not_uncertain].copy()


       if high_risk_recent.empty:
           return {}


       # 1. GLOBAL NLP LEXICAL DEDUPLICATION
       dedup_events = lexical_deduplicate(high_risk_recent)
      
       if dedup_events.empty:
           return {}


       # 2. STRICT PRIMARY LOCATION ANCHORING
       dedup_events['primary_district'] = dedup_events.apply(self._extract_epicenter, axis=1)
       alerts = dedup_events["primary_district"].value_counts()
      
       triggering_data = {}
       for district, count in alerts.items():
           if count >= self.trigger_threshold and district != 'unmapped':
               events = dedup_events[dedup_events["primary_district"] == district]
               if len(events) >= self.trigger_threshold:
                   triggering_data[str(district)] = events
                  
       return triggering_data