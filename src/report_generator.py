import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from PIL import Image as PILImage
import re


from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from src.report_components import DataFetcher, LLMCompiler, ChartGenerator
from src.utils import lexical_deduplicate
from src.kinetic_log_filter import is_kinetic_log_eligible


load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


# ==================== BRANDING & COLORS ====================
BG_COLOR = colors.HexColor('#0C1B16')
BOX_BG = colors.HexColor('#1F3A2E')
ACCENT = colors.HexColor('#C4663F')
ACCENT_MUTED = colors.HexColor('#6B9B7E')
TEXT_MAIN = colors.HexColor('#F0EAD9')




class HybridIntelCompiler:
   def __init__(self):
       self.report_dir = Path("reports")
       self.temp_dir = self.report_dir / "temp_assets"
       self.report_dir.mkdir(parents=True, exist_ok=True)
       self.temp_dir.mkdir(parents=True, exist_ok=True)
       self.fetcher = DataFetcher()
       self.llm = LLMCompiler(api_key=GROQ_API_KEY)
       self.charts = ChartGenerator(temp_dir=self.temp_dir)


   def _draw_dark_background(self, canvas, doc):
       canvas.saveState()
       canvas.setFillColor(BG_COLOR)
       canvas.rect(0, 0, letter[0], letter[1], fill=True, stroke=False)
       canvas.restoreState()


   def compile_weekly_brief(self):
       print("📊 Aggregating Data...")
      
       # 1. Fetch Data via Component
       recent_df = self.fetcher.fetch_recent_high_risk_data(days=7, min_score=5.0)
       if recent_df is None or recent_df.empty:
           print("⚠️ Insufficient high-risk kinetic data in the last 7 days to generate a formal brief.")
           return None


       # 2. Generate Charts via Component
       chart_paths = self.charts.generate(recent_df)


       # 3. LLM Processing via Component
       raw_data_summary = self.llm.build_data_summary(recent_df)
       narrative = self.llm.generate_narrative(raw_data_summary)


       # Pre-calculate Metrics with safety
       total_incidents = len(recent_df)
       high_risk_count = len(recent_df[recent_df['final_risk_score'] >= 8.0])
       avg_score = recent_df['final_risk_score'].mean()
       active_districts = recent_df["ner_locations"].apply(lambda x: x if isinstance(x, list) else []).explode().nunique()
       active_actors = recent_df["ner_actors"].apply(lambda x: x if isinstance(x, list) else []).explode().nunique()


       # 4. PDF Assembly (ReportLab)
       pdf_path = self.report_dir / f"Caesura_Intelligence_Brief_{datetime.now().strftime('%Y-%m-%d')}.pdf"
       doc = SimpleDocTemplate(str(pdf_path), pagesize=letter, leftMargin=30, rightMargin=30, topMargin=30, bottomMargin=30)
       styles = getSampleStyleSheet()
      
       title_style = ParagraphStyle('DocTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=22, textColor=TEXT_MAIN, spaceAfter=8)
       subtitle_style = ParagraphStyle('DocSubtitle', fontName='Helvetica', fontSize=10, textColor=ACCENT_MUTED, spaceAfter=20)
       h2_style = ParagraphStyle('SectionHeading', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=13, textColor=ACCENT, spaceBefore=18, spaceAfter=10, textTransform='uppercase')
       body_style = ParagraphStyle('ReportBody', fontName='Helvetica', fontSize=10.5, leading=16, textColor=TEXT_MAIN, spaceAfter=10)


       story = []


       # CAESURA Header
       logo_source = "05 _ Prism _ Clarity mark.png"
       processed_logo = str(self.temp_dir / "caesura_icon.png")


       try:
           with PILImage.open(logo_source) as img:
               w, h = img.size
               crop_box = (w * 0.23, h * 0.30, w * 0.37, h * 0.48)
               icon = img.crop(crop_box)
               icon.save(processed_logo)
           logo_img = Image(processed_logo, width=40, height=52)
       except Exception as e:
           print(f"⚠️ Could not process logo: {e}")
           logo_img = Paragraph("<b>[LOGO]</b>", body_style)


       header_data = [[logo_img, Paragraph("<font size=24 color='#F0EAD9'><b>CAESURA</b></font><br/><font size=12 color='#6B9B7E'>INTELLIGENCE</font>", body_style)]]
       header_table = Table(header_data, colWidths=[55, 400], style=[('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('BOTTOMPADDING', (0, 0), (-1, -1), 15)])
       story.append(header_table)


       story.append(Paragraph("🛡️ CONFLICT CORRIDOR INTELLIGENCE BRIEF", title_style))
       story.append(Paragraph(f"GENERATED: {datetime.now().strftime('%Y-%m-%d')} | CLASSIFICATION: OSINT", subtitle_style))


       # Metrics Table
       metric_data = [
           [Paragraph("<font color='#C4663F'><b>Total Incidents</b></font>", body_style),
            Paragraph("<font color='#C4663F'><b>High Risk</b></font>", body_style),
            Paragraph("<font color='#C4663F'><b>Avg Score</b></font>", body_style),
            Paragraph("<font color='#C4663F'><b>Districts</b></font>", body_style),
            Paragraph("<font color='#C4663F'><b>Actors</b></font>", body_style)],
           [Paragraph(f"<font size=20 color='#F0EAD9'><b>{total_incidents}</b></font>", body_style),
            Paragraph(f"<font size=20 color='#F0EAD9'><b>{high_risk_count}</b></font>", body_style),
            Paragraph(f"<font size=20 color='#F0EAD9'><b>{avg_score:.1f}</b></font>", body_style),
            Paragraph(f"<font size=20 color='#F0EAD9'><b>{active_districts}</b></font>", body_style),
            Paragraph(f"<font size=20 color='#F0EAD9'><b>{active_actors}</b></font>", body_style)]
       ]
       metric_table = Table(metric_data, colWidths=[105, 105, 105, 105, 105])
       metric_table.setStyle(TableStyle([
           ('BACKGROUND', (0, 0), (-1, -1), BOX_BG),
           ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
           ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
           ('BOX', (0, 0), (-1, -1), 1.5, ACCENT),
           ('INNERGRID', (0, 0), (-1, -1), 0.5, BG_COLOR),
           ('TOPPADDING', (0, 0), (-1, -1), 10),
           ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
       ]))
       story.append(metric_table)


       # Heatmaps
       if 'jk_heatmap' in chart_paths:
           story.append(Paragraph("I. GEOGRAPHIC HEATMAP - JAMMU & KASHMIR", h2_style))
           story.append(Image(chart_paths['jk_heatmap'], width=500, height=280))


       if 'ne_heatmap' in chart_paths:
           story.append(Paragraph("I. GEOGRAPHIC HEATMAP - NORTHEAST INDIA", h2_style))
           story.append(Image(chart_paths['ne_heatmap'], width=500, height=280))


       # Tactics & Actors Charts
       story.append(Paragraph("II. TACTICS & THREAT ACTOR ANALYSIS", h2_style))
       chart_row = []
       if 'tactics' in chart_paths: chart_row.append(Image(chart_paths['tactics'], width=260, height=180))
       if 'actors' in chart_paths: chart_row.append(Image(chart_paths['actors'], width=260, height=180))
       if chart_row:
           story.append(Table([chart_row], colWidths=[270, 270], style=[('VALIGN', (0, 0), (-1, -1), 'TOP')]))


       if 'pie' in chart_paths:
           story.append(Image(chart_paths['pie'], width=300, height=180))


       # Narrative Assembly
       story.append(Paragraph("III. STRATEGIC NARRATIVE SYNTHESIS", h2_style))
       for p in narrative.split("\n\n"):
           p_clean = p.strip().replace("\n", "<br/>")
           if not p_clean or "400 Client Error" in p_clean: continue
              
           header_match = re.match(r"^[\*\#\s]*([1-4]\.\s+[A-Z\s]+):?(.*)", p_clean, re.IGNORECASE)
          
           if header_match:
               header_title = header_match.group(1).strip().upper()
               header_body = header_match.group(2).strip()
              
               if header_body:
                   header_markup = f"<font color='#C4663F'><b>{header_title}</b></font>:<br/>{header_body}"
                   story.append(Paragraph(header_markup, body_style))
               else:
                   story.append(Paragraph(f"<font color='#C4663F'><b>{header_title}</b></font>", body_style))
           else:
               clean_body = p_clean.replace("**", "").replace("##", "")
               story.append(Paragraph(clean_body, body_style))
              
       story.append(Spacer(1, 15))


       # IV. VERIFIED KINETIC LOG
       story.append(Paragraph("IV. VERIFIED CRITICAL KINETIC LOG (TOP INCIDENTS)", h2_style))
       kinetic_raw = recent_df[recent_df['incident_type'] == 'Kinetic']
       if not kinetic_raw.empty:
           kinetic_raw = kinetic_raw[kinetic_raw.apply(is_kinetic_log_eligible, axis=1)]
       kinetic_events = lexical_deduplicate(kinetic_raw, max_results=5)
      
       if not kinetic_events.empty:
           for _, row in kinetic_events.iterrows():
               log_line = f"<bullet>&bull;</bullet><b>[{row.get('granular_incident_type', 'Kinetic')}]</b> {row.get('title', 'Headline Omitted')} <i>(Source: {row.get('source', 'OSINT')})</i>"
               story.append(Paragraph(log_line, body_style))
       else:
           story.append(Paragraph("<i>No critical kinetic incidents verified in this reporting window.</i>", body_style))


       story.append(Spacer(1, 10))


       # V. VERIFIED UNREST LOG
       story.append(Paragraph("V. VERIFIED CIVIL UNREST LOG (TOP INCIDENTS)", h2_style))
       unrest_raw = recent_df[recent_df['incident_type'] == 'Unrest']
       unrest_events = lexical_deduplicate(unrest_raw, max_results=5)
      
       if not unrest_events.empty:
           for _, row in unrest_events.iterrows():
               log_line = f"<bullet>&bull;</bullet><b>[{row.get('granular_incident_type', 'Unrest')}]</b> {row.get('title', 'Headline Omitted')} <i>(Source: {row.get('source', 'OSINT')})</i>"
               story.append(Paragraph(log_line, body_style))
       else:
           story.append(Paragraph("<i>No significant civil unrest events verified in this reporting window.</i>", body_style))


       story.append(Spacer(1, 15))
       story.append(Paragraph("<font color='#6B9B7E'><i>End of Brief. Compiled by Caesura Intelligence.</i></font>", body_style))
       story.append(Spacer(1, 5))
       story.append(Paragraph("<font color='#555555' size='8'><i>Disclaimer: This intelligence brief is AI-synthesized based on OSINT data. Automated extraction and classification may contain margins of error.</i></font>", body_style))
      
       # Build document & Cleanup temp files
       doc.build(story, onFirstPage=self._draw_dark_background, onLaterPages=self._draw_dark_background)
      
       for path in chart_paths.values():
           try: os.remove(path)
           except: pass
       try: os.remove(processed_logo)
       except: pass
          
       print(f"✅ Caesura Intelligence PDF compiled successfully: {pdf_path}")
       return pdf_path


if __name__ == "__main__":
   try:
       compiler = HybridIntelCompiler()
       compiler.compile_weekly_brief()
   except Exception as e:
       print(f"⚠️ System Error during standalone compilation: {e}")