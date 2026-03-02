import streamlit as st
import feedparser
import pandas as pd
from transformers import pipeline
from datetime import datetime, timedelta
import time
import plotly.express as px
import plotly.graph_objects as go
from urllib.parse import quote
from wordcloud import WordCloud
import matplotlib.pyplot as plt
from fpdf import FPDF
import tempfile
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap, MarkerCluster
import random
import io

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="El Faro | Sentinel Prime", layout="wide", page_icon="⚓")

# --- 2. MEMORIA BLINDADA (PREVIENE KEYERROR) ---
# Definimos las columnas base para evitar errores al cargar o guardar
COLS = ['Fecha', 'Hora', 'Dia', 'Fuente', 'Titular', 'Link', 'Sentimiento', 'Alcance', 'Interacciones', 'Emocion', 'Lugar', 'Tipo']

if 'data_master' not in st.session_state: 
    st.session_state.data_master = pd.DataFrame(columns=COLS)
if 'proyectos' not in st.session_state: st.session_state.proyectos = {}
if 'search_active' not in st.session_state: st.session_state.search_active = False

# --- 3. ESTILOS VISUALES & FARO RESTAURADO ---
speed = "2s" if st.session_state.search_active else "12s"

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap');
    .main {{ background-color: #020617 !important; color: #ffffff !important; font-family: 'Inter', sans-serif; }}
    
    /* ANIMACIÓN DEL FARO (RESTAURADA Y MEJORADA) */
    .lighthouse-container {{
        position: relative; width: 100%; height: 180px; 
        display: flex; justify-content: center; align-items: flex-end;
        background: radial-gradient(circle at bottom, #1e293b 0%, transparent 70%);
        margin-bottom: 20px; overflow: hidden; border-bottom: 1px solid #38bdf8;
    }}
    .lighthouse-svg {{ width: 70px; height: 120px; z-index: 10; position: relative; filter: drop-shadow(0 0 10px #38bdf8); }}
    .beam {{
        position: absolute; bottom: 90px; left: 50%; width: 600px; height: 600px;
        background: conic-gradient(from 0deg at 50% 50%, rgba(56,189,248,0.3) 0deg, transparent 60deg);
        transform-origin: 50% 50%; margin-left: -300px; margin-bottom: -300px;
        animation: rotateBeam {speed} linear infinite; pointer-events: none; z-index: 1;
    }}
    @keyframes rotateBeam {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}

    /* KPI CARDS - ALTO CONTRASTE */
    div[data-testid="stMetric"] {{
        background-color: #0f172a !important; border: 1px solid #38bdf8 !important;
        border-radius: 10px !important; padding: 15px !important;
        box-shadow: 0 4px 10px rgba(0,0,0,0.5);
    }}
    div[data-testid="stMetricLabel"] {{ color: #ffffff !important; font-size: 14px !important; font-weight: 700 !important; opacity: 1 !important; }}
    div[data-testid="stMetricValue"] {{ color: #38bdf8 !important; font-size: 36px !important; font-weight: 900 !important; }}
    
    /* BOTONES Y TABS */
    .stButton>button {{ background: linear-gradient(90deg, #0284c7, #2563eb); color: white; border: none; font-weight: bold; width: 100%; }}
    .stTabs [aria-selected="true"] {{ background-color: #38bdf8 !important; color: #000000 !important; font-weight: bold; }}
    </style>
    """, unsafe_allow_html=True)

# --- 4. MOTOR SENTINEL ---
@st.cache_resource
def load_ia():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def get_metrics_sim(fuente, sent):
    # Simulación inteligente de métricas
    base = 100
    src = fuente.lower()
    if any(x in src for x in ['biobio', 'emol', 'latercera', 'youtube', 'mega']): base = 100000
    elif any(x in src for x in ['eldia', 'tiempo', 'observatodo', 'region']): base = 25000
    elif 'social' in src or 'tiktok' in src: base = 5000
    
    # Randomizador realista
    alcance = int(base * random.uniform(0.8, 1.5))
    interacciones = int(alcance * (0.05 if sent == "Negativo" else 0.02))
    return alcance, interacciones

def classify_emotion(text):
    t = text.lower()
    if any(x in t for x in ['robo', 'muerte', 'delito', 'grave', 'temor']): return "😱 Miedo"
    if any(x in t for x in ['mentira', 'falla', 'error', 'vergüenza', 'odio']): return "🤬 Ira"
    if any(x in t for x in ['feliz', 'éxito', 'logro', 'avance', 'bueno']): return "🎉 Alegría"
    return "😐 Neutral"

def scan_hydra(obj, ini, fin):
    st.session_state.search_active = True
    ia = load_ia()
    
    # 30 Puntos de Búsqueda
    urls = []
    base_rss = "https://news.google.com/rss/search?q={}&hl=es-419&gl=CL&ceid=CL:es-419"
    kw_extra = ["noticias", "polémica", "municipalidad", "gestión", "seguridad"]
    sites = ["diarioeldia.cl", "semanariotiempo.cl", "elobservatodo.cl", "miradiols.cl", "tiktok.com", "reddit.com", "instagram.com", "facebook.com"]
    
    for k in kw_extra: urls.append(base_rss.format(quote(f"{obj} {k}")))
    for s in sites: urls.append(base_rss.format(quote(f"site:{s} {obj}")))
    
    res = []
    seen = set()
    prog = st.progress(0)
    
    for i, url in enumerate(urls):
        feed = feedparser.parse(url)
        for entry in feed.entries:
            try: dt = datetime.fromtimestamp(time.mktime(entry.published_parsed))
            except: dt = datetime.now()
            
            if not (ini <= dt.date() <= fin) or entry.link in seen: continue
            seen.add(entry.link)
            
            p = ia(entry.title[:512])[0]
            score = int(p['label'].split()[0])
            sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
            src = entry.source.title if 'source' in entry else "Web"
            typ = "Red Social" if any(x in src.lower() for x in ['tiktok','instagram','facebook','twitter','reddit']) else "Prensa"
            lug = "La Serena"
            if "coquimbo" in entry.title.lower(): lug = "Coquimbo"
            
            alcance, inter = get_metrics_sim(src, sent)
            
            res.append({
                'Fecha': dt.date(), 'Hora': dt.hour, 'Dia': dt.strftime('%A'),
                'Fuente': src, 'Titular': entry.title, 'Link': entry.link,
                'Sentimiento': sent, 'Alcance': alcance, 'Interacciones': inter,
                'Emocion': classify_emotion(entry.title), 'Lugar': lug, 'Tipo': typ
            })
        prog.progress((i+1)/len(urls))
        
    st.session_state.search_active = False
    return pd.DataFrame(res)

# --- 5. SIDEBAR ---
with st.sidebar:
    # FARO SVG RESTAURADO
    st.markdown("""
        <div class="lighthouse-container">
            <div class="beam"></div>
            <svg class="lighthouse-svg" viewBox="0 0 100 200">
                <path d="M35,190 L65,190 L60,50 L40,50 Z" fill="#cbd5e1" stroke="#38BDF8" stroke-width="2"/>
                <rect x="35" y="30" width="30" height="20" fill="#facc15" rx="2" stroke="#facc15"/>
                <path d="M30,30 L50,10 L70,30 Z" fill="#0f172a" stroke="#38BDF8" stroke-width="2"/>
                <rect x="42" y="50" width="16" height="140" fill="#94a3b8" opacity="0.3"/>
            </svg>
        </div>
    """, unsafe_allow_html=True)
    
    st.title("EL FARO")
    st.caption("Sentinel Prime v31.0")
    
    obj_in = st.text_input("Objetivo", "Daniela Norambuena")
    ini = st.date_input("Inicio", datetime.now()-timedelta(days=30))
    fin = st.date_input("Fin", datetime.now())
    
    if st.button("🔥 ACTIVAR RADAR"):
        st.session_state.data_master = scan_hydra(obj_in, ini, fin)
        
    with st.expander("📂 Proyectos"):
        p_name = st.text_input("Nombre")
        if st.button("Guardar"):
            if not st.session_state.data_master.empty:
                st.session_state.proyectos[p_name] = st.session_state.data_master
                st.success("Guardado")
        if st.session_state.proyectos:
            sel = st.selectbox("Cargar", list(st.session_state.proyectos.keys()))
            if st.button("Abrir"):
                st.session_state.data_master = st.session_state.proyectos[sel]
                st.rerun()

# --- 6. DASHBOARD ---
df = st.session_state.data_master
if not df.empty:
    st.markdown(f"## 🔭 Centro de Inteligencia: {obj_in.upper()}")
    
    # KPIs WHITE HOT
    k1, k2, k3, k4 = st.columns(4)
    vol = len(df)
    try:
        alc = df['Alcance'].sum()
        inter = df['Interacciones'].sum()
        pos_perc = int(len(df[df.Sentimiento=='Positivo'])/vol*100)
    except: alc=0; inter=0; pos_perc=0 # Fallback por si acaso
    
    k1.metric("MENCIONES", vol)
    k2.metric("ALCANCE EST.", f"{alc/1000000:.1f}M")
    k3.metric("INTERACCIONES", f"{inter/1000:.1f}K")
    k4.metric("POSITIVIDAD", f"{pos_perc}%")
    
    tabs = st.tabs(["📊 ESTRATEGIA", "📥 INGESTA TÁCTICA", "🗺️ GEO & EMOCIÓN", "📄 REPORTE PRO", "📝 DATOS"])
    
    # === TAB 1: ESTRATEGIA ===
    with tabs[0]:
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown("### 🕸️ Ecosistema (Sunburst)")
            fig_sun = px.sunburst(df, path=['Sentimiento', 'Fuente', 'Titular'], color='Sentimiento',
                                  color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
            fig_sun.update_layout(height=600, paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"))
            st.plotly_chart(fig_sun, use_container_width=True)
        with c2:
            st.markdown("### 🌳 Mapa de Conceptos (Treemap)")
            fig_tree = px.treemap(df, path=['Lugar', 'Fuente', 'Titular'], color='Sentimiento',
                                  color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
            fig_tree.update_traces(textinfo="label+value", textfont=dict(size=24))
            fig_tree.update_layout(height=600, margin=dict(t=0,l=0,r=0,b=0))
            st.plotly_chart(fig_tree, use_container_width=True)

    # === TAB 2: INGESTA TÁCTICA (MANUAL) ===
    with tabs[1]:
        st.markdown("### 📥 Ingesta Manual de Inteligencia")
        st.info("Utilice este módulo para incorporar datos offline, comunicados o hallazgos directos al análisis.")
        
        with st.form("manual_ingest"):
            txt_in = st.text_area("Texto / Transcripción / Nota", height=150)
            src_in = st.text_input("Fuente (Ej: Radio, WhatsApp, Reunión)", "Inteligencia Humana")
            sub = st.form_submit_button("⚡ PROCESAR E INTEGRAR")
            
            if sub and txt_in:
                # Procesar como dato real
                ia = load_ia()
                sc = int(ia(txt_in[:512])[0]['label'].split()[0])
                s_new = "Negativo" if sc <= 2 else "Neutro" if sc == 3 else "Positivo"
                a_new, i_new = get_metrics_sim("Manual", s_new)
                
                new_row = {
                    'Fecha': datetime.now().date(), 'Hora': 12, 'Dia': 'Manual', 
                    'Fuente': src_in, 'Titular': txt_in[:100]+"...", 'Link': 'Manual',
                    'Sentimiento': s_new, 'Alcance': a_new, 'Interacciones': i_new,
                    'Emocion': classify_emotion(txt_in), 'Lugar': 'Manual', 'Tipo': 'Ingesta'
                }
                st.session_state.data_master = pd.concat([st.session_state.data_master, pd.DataFrame([new_row])], ignore_index=True)
                st.success("Dato incorporado al sistema.")
                st.rerun()

    # === TAB 3: GEO & EMOCIÓN ===
    with tabs[2]:
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("### 📡 Radar Emocional")
            emo_counts = df['Emocion'].value_counts().reset_index()
            emo_counts.columns = ['Emocion', 'Count']
            fig_rad = px.line_polar(emo_counts, r='Count', theta='Emocion', line_close=True, template="plotly_dark")
            fig_rad.update_traces(fill='toself', line_color='#38bdf8')
            st.plotly_chart(fig_rad, use_container_width=True)
        with c4:
            st.markdown("### 📍 Mapa Táctico")
            m = folium.Map(location=[-29.90, -71.25], zoom_start=12, tiles="CartoDB dark_matter")
            mc = MarkerCluster().add_to(m)
            for _, r in df.iterrows():
                folium.Marker([random.uniform(-29.95,-29.85), random.uniform(-71.3,-71.2)], popup=r['Titular']).add_to(mc)
            st_folium(m, width="100%", height=400)

    # === TAB 4: REPORTE PRO ===
    with tabs[3]:
        st.subheader("Generador de Informes Ejecutivos")
        
        top_src = df['Fuente'].mode()[0] if not df.empty else "N/A"
        txt_rep = f"""
        INFORME DE INTELIGENCIA ESTRATÉGICA - SENTINEL PRIME
        ====================================================
        OBJETIVO: {obj_in.upper()} | PERIODO: {ini} al {fin}
        
        1. SÍNTESIS EJECUTIVA
        Se han procesado {vol} unidades de información con un alcance estimado de {alc/1000000:.2f}M impresiones.
        El sentimiento predominante es {df['Sentimiento'].mode()[0]}.
        
        2. HALLAZGOS TÁCTICOS
        La fuente de mayor tracción es '{top_src}'. La emoción dominante en la audiencia es '{df['Emocion'].mode()[0]}'.
        
        3. RECOMENDACIÓN
        {'Mantener estrategia.' if pos_perc > 50 else 'Activar protocolo de crisis digital.'}
        
        Generado por El Faro v31.0
        """
        st.text_area("Contenido:", txt_rep, height=300)
        
        if st.button("📄 GENERAR PDF CON GRÁFICOS"):
            # Gráficos
            fig, ax = plt.subplots(figsize=(6,4))
            df['Sentimiento'].value_counts().plot(kind='bar', color=['green','red','orange'], ax=ax)
            buf = io.BytesIO(); plt.savefig(buf, format='png'); buf.seek(0)
            
            pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 16); pdf.cell(0, 10, "REPORTE EL FARO", 0, 1, 'C')
            pdf.ln(10); pdf.set_font("Arial", size=11); pdf.multi_cell(0, 8, txt_rep.encode('latin-1','replace').decode('latin-1'))
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                f.write(buf.getvalue()); pdf.image(f.name, x=50, w=100)
            
            out = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            pdf.output(out.name)
            with open(out.name, "rb") as f: st.download_button("📥 DESCARGAR PDF", f, "Reporte_Prime.pdf")

    # === TAB 5: GESTIÓN ===
    with tabs[4]:
        df_ed = st.data_editor(df, use_container_width=True, key="ed_v31")
        if st.button("💾 SINCRONIZAR"):
            st.session_state.data_master = df_ed
            st.success("OK")

else:
    st.info("👋 Bienvenido a El Faro. Configure su misión en el panel lateral.")
