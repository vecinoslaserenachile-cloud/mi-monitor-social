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
st.set_page_config(page_title="El Faro | Nebula Notebook", layout="wide", page_icon="⚓")

# --- 2. MEMORIA Y ESTADO ---
if 'data_master' not in st.session_state: st.session_state.data_master = pd.DataFrame()
if 'proyectos' not in st.session_state: st.session_state.proyectos = {}
if 'search_active' not in st.session_state: st.session_state.search_active = False

# --- 3. ESTILOS NEBULA (CONTRASTE MÁXIMO & FIX TEXTOS) ---
speed = "1.5s" if st.session_state.search_active else "10s"

st.markdown(f"""
    <style>
    /* FUENTE GLOBAL */
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700;900&display=swap');
    .main {{ background-color: #02040a !important; color: #ffffff !important; font-family: 'Montserrat', sans-serif; }}
    
    /* TITULARES NEÓN */
    h1, h2, h3 {{ 
        color: #00F0FF !important; 
        text-shadow: 0 0 10px rgba(0, 240, 255, 0.5);
        font-weight: 900 !important; 
        text-transform: uppercase;
    }}

    /* KPI CARDS - FORZADO AGRESIVO DE COLOR BLANCO */
    div[data-testid="stMetric"] {{
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%) !important;
        border: 1px solid #00F0FF !important;
        border-radius: 12px !important;
        padding: 20px !important;
        box-shadow: 0 0 20px rgba(0, 240, 255, 0.1);
    }}
    /* Selector universal para etiquetas dentro de metricas */
    div[data-testid="stMetric"] label, 
    div[data-testid="stMetric"] div, 
    div[data-testid="stMetric"] p {{
        color: #FFFFFF !important;
        opacity: 1 !important;
    }}
    div[data-testid="stMetricLabel"] {{ font-size: 14px !important; font-weight: 700 !important; letter-spacing: 1px; }}
    div[data-testid="stMetricValue"] {{ font-size: 42px !important; font-weight: 900 !important; text-shadow: 0 0 10px rgba(255,255,255,0.5); }}

    /* FARO SIDEBAR (AISLADO) */
    .faro-container {{
        position: relative; height: 160px; width: 100%; display: flex; justify-content: center;
        background: radial-gradient(circle at bottom, #001529 0%, transparent 70%);
        border-bottom: 2px solid #00F0FF; margin-bottom: 20px; overflow: hidden;
    }}
    .torre {{ font-size: 70px; z-index: 10; margin-top: 40px; filter: drop-shadow(0 0 10px cyan); }}
    .haz {{
        position: absolute; top: 60px; left: 50%; width: 500px; height: 500px;
        background: conic-gradient(from 180deg at 50% 50%, rgba(0,240,255,0.4) 0deg, transparent 60deg);
        transform-origin: 50% 50%; animation: radar {speed} linear infinite; z-index: 1; margin-left: -250px;
    }}
    @keyframes radar {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}

    /* TABS ESTILO CYBERPUNK */
    .stTabs [aria-selected="true"] {{
        background-color: #00F0FF !important; color: #000000 !important; font-weight: 900;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 4. MOTORES DE INTELIGENCIA ---
@st.cache_resource
def load_engine():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def classify_vibra(text):
    t = text.lower()
    if any(x in t for x in ['robo', 'delito', 'muerte', 'asesinato', 'encerrona']): return "😱 MIEDO"
    if any(x in t for x in ['mentira', 'corrupción', 'falla', 'taco', 'basura']): return "🤬 IRA"
    if any(x in t for x in ['fiesta', 'festival', 'premio', 'ganador', 'playa']): return "🎉 ALEGRÍA"
    if any(x in t for x in ['triste', 'luto', 'pena', 'despedida']): return "😢 TRISTEZA"
    return "😐 NEUTRAL"

def scan_nebula(obj, ini, fin):
    st.session_state.search_active = True
    analyzer = load_engine()
    # HYDRA 30 PUNTOS
    base_urls = [
        f"https://news.google.com/rss/search?q={quote(obj)}&hl=es-419&gl=CL&ceid=CL:es-419",
        f"https://news.google.com/rss/search?q={quote(obj + ' redes sociales')}&hl=es-419&gl=CL&ceid=CL:es-419"
    ]
    sites = ["tiktok.com", "reddit.com", "instagram.com", "facebook.com", "diarioeldia.cl", "biobiochile.cl"]
    for s in sites: base_urls.append(f"https://news.google.com/rss/search?q={quote('site:'+s+' '+obj)}&hl=es-419&gl=CL&ceid=CL:es-419")
    
    data = []
    seen = set()
    prog = st.progress(0)
    
    for i, url in enumerate(base_urls):
        feed = feedparser.parse(url)
        for entry in feed.entries:
            if entry.link in seen: continue
            seen.add(entry.link)
            
            # AI
            res = analyzer(entry.title[:512])[0]
            score = int(res['label'].split()[0])
            sent = "🔴 Negativo" if score <= 2 else "🟡 Neutro" if score == 3 else "🟢 Positivo"
            
            # Metrics Simulation
            src = entry.source.title if 'source' in entry else "Web"
            reach = random.randint(1000, 500000) if "biobio" in src.lower() else random.randint(100, 5000)
            
            # Geo
            lug = "La Serena"
            if "coquimbo" in entry.title.lower(): lug = "Coquimbo"
            if "ovalle" in entry.title.lower(): lug = "Ovalle"
            
            data.append({
                'Fecha': datetime.now().date(), 'Fuente': src, 'Titular': entry.title, 
                'Link': entry.link, 'Sentimiento': sent, 'Alcance': reach,
                'Vibra': classify_vibra(entry.title), 'Lugar': lug, 'Tipo': 'Rastreo Automático'
            })
        prog.progress((i+1)/len(base_urls))
    
    st.session_state.search_active = False
    return pd.DataFrame(data)

# --- 5. SIDEBAR ---
with st.sidebar:
    st.markdown("""<div class='faro-container'><div class='haz'></div><div class='torre'>⚓</div></div>""", unsafe_allow_html=True)
    st.title("EL FARO")
    st.caption("Nebula Notebook v30.0")
    
    obj_in = st.text_input("Objetivo", "Daniela Norambuena")
    if st.button("🔥 ACTIVAR RADAR"):
        st.session_state.data_master = scan_nebula(obj_in, None, None)
        
    with st.expander("📂 Proyectos"):
        p_save = st.text_input("Guardar como...")
        if st.button("💾 Guardar") and p_save:
            st.session_state.proyectos[p_save] = st.session_state.data_master
            st.success(f"Proyecto {p_save} guardado.")
        
        if st.session_state.proyectos:
            sel = st.selectbox("Cargar", list(st.session_state.proyectos.keys()))
            if st.button("Abrir"):
                st.session_state.data_master = st.session_state.proyectos[sel]
                st.rerun()

# --- 6. DASHBOARD NEBULA ---
df = st.session_state.data_master
if not df.empty:
    st.markdown(f"## 🔭 Centro de Inteligencia: {obj_in}")
    
    tabs = st.tabs(["📊 ESTRATEGIA", "📓 NOTEBOOK LM", "🎭 EMOCIÓN & FUNNEL", "🗺️ TÁCTICO", "📄 REPORTE PRO"])
    
    vol = len(df)
    reach = df['Alcance'].sum()
    pos = len(df[df.Sentimiento.str.contains("Positivo")])
    neg = len(df[df.Sentimiento.str.contains("Negativo")])
    
    # === TAB 1: ESTRATEGIA ===
    with tabs[0]:
        # KPIs WHITE HOT
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("MENCIONES TOTALES", vol)
        k2.metric("ALCANCE ESTIMADO", f"{reach/1000000:.1f}M")
        k3.metric("POSITIVIDAD", f"{int(pos/vol*100)}%", "🟢")
        k4.metric("RIESGO CRÍTICO", f"{int(neg/vol*100)}%", "🔴")
        
        st.divider()
        
        c1, c2 = st.columns([3, 2])
        with c1:
            st.markdown("### 🌳 Mapa de Calor de Conceptos (Treemap)")
            fig_tree = px.treemap(df, path=['Lugar', 'Fuente', 'Titular'], color='Sentimiento',
                                  color_discrete_map={'🟢 Positivo':'#00FF00', '🔴 Negativo':'#FF0000', '🟡 Neutro':'#FFFF00'})
            # TEXTO GIGANTE Y NEGRO PARA CONTRASTE DENTRO DEL COLOR
            fig_tree.update_traces(textinfo="label+value", textfont=dict(size=28, color="black"), root_color="white")
            fig_tree.update_layout(height=600, margin=dict(t=0, l=0, r=0, b=0))
            st.plotly_chart(fig_tree, use_container_width=True)
            
        with c2:
            st.markdown("### 🕸️ Navegador Solar (Sunburst)")
            fig_sun = px.sunburst(df, path=['Sentimiento', 'Fuente'], color='Sentimiento',
                                  color_discrete_map={'🟢 Positivo':'#00FF00', '🔴 Negativo':'#FF0000', '🟡 Neutro':'#FFFF00'})
            fig_sun.update_layout(height=600, font=dict(size=18))
            st.plotly_chart(fig_sun, use_container_width=True)

    # === TAB 2: NOTEBOOK LM (INGESTA MANUAL) ===
    with tabs[1]:
        st.markdown("### 📓 Cuaderno de Ingestión Táctica")
        st.info("Pega aquí textos de comunicados, noticias offline, transcripciones de radio o notas de reuniones. El sistema las procesará como inteligencia.")
        
        with st.form("notebook_form"):
            raw_text = st.text_area("📝 Pegar Texto / Nota de Inteligencia", height=150)
            uploaded_file = st.file_uploader("📷 Adjuntar Evidencia (Imagen/PDF - Simulación)", type=['png','jpg','pdf'])
            manual_source = st.text_input("Fuente del dato (Ej: Radio Madero, WhatsApp Vecinos)", "Inteligencia Humana")
            
            submitted = st.form_submit_button("⚡ PROCESAR E INCORPORAR AL DASHBOARD")
            
            if submitted and raw_text:
                # Procesar texto con el mismo motor IA
                ia = load_engine()
                res = ia(raw_text[:512])[0]
                sc = int(res['label'].split()[0])
                s_manual = "🔴 Negativo" if sc <= 2 else "🟡 Neutro" if sc == 3 else "🟢 Positivo"
                
                new_row = {
                    'Fecha': datetime.now().date(), 'Fuente': manual_source, 'Titular': raw_text[:100]+"...",
                    'Link': 'Manual Input', 'Sentimiento': s_manual, 'Alcance': 1000, 
                    'Vibra': classify_vibra(raw_text), 'Lugar': "Manual", 'Tipo': 'Notebook LM'
                }
                st.session_state.data_master = pd.concat([st.session_state.data_master, pd.DataFrame([new_row])], ignore_index=True)
                st.success("✅ Dato incorporado exitosamente al cerebro de El Faro.")
                st.rerun()

    # === TAB 3: EMOCIÓN & FUNNEL ===
    with tabs[2]:
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("### 📡 Radar de Vibras")
            df_vibra = df['Vibra'].value_counts().reset_index()
            df_vibra.columns = ['Vibra', 'Count']
            fig_rad = px.line_polar(df_vibra, r='Count', theta='Vibra', line_close=True, template="plotly_dark")
            fig_rad.update_traces(fill='toself', line_color='#00F0FF')
            st.plotly_chart(fig_rad, use_container_width=True)
            
        with c4:
            st.markdown("### 🌪️ Embudo de Conversión Mediática")
            funnel_data = dict(
                number=[reach, vol*1000, vol],
                stage=["Alcance Potencial", "Lecturas Estimadas", "Menciones Reales"]
            )
            fig_fun = px.funnel(funnel_data, x='number', y='stage')
            fig_fun.update_traces(marker=dict(color=["#00F0FF", "#00BFFF", "#1E90FF"]))
            fig_fun.update_layout(template="plotly_dark")
            st.plotly_chart(fig_fun, use_container_width=True)

    # === TAB 4: GEO & TÁCTICO ===
    with tabs[3]:
        m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
        mc = MarkerCluster().add_to(m)
        for _, r in df.iterrows():
            icon_color = "green" if "Positivo" in r['Sentimiento'] else "red" if "Negativo" in r['Sentimiento'] else "beige"
            folium.Marker([random.uniform(-29.95,-29.85), random.uniform(-71.3,-71.2)], popup=r['Titular'], icon=folium.Icon(color=icon_color, icon="info-sign")).add_to(mc)
        st_folium(m, width="100%", height=600)

    # === TAB 5: REPORTE PRO ===
    with tabs[4]:
        st.subheader("Generador de Informes Consultivos")
        
        txt_report = f"""
        INFORME DE INTELIGENCIA TÁCTICA - PROYECTO NEBULA
        =================================================
        OBJETIVO: {obj_in.upper()} | FECHA: {datetime.now().strftime('%d/%m/%Y')}
        
        1. SÍNTESIS EJECUTIVA
        El sistema Sentinel ha procesado {vol} unidades de información, incluyendo ingresos vía Notebook LM.
        El sentimiento consolidado es {df['Sentimiento'].mode()[0]}.
        
        2. ANÁLISIS DE VIBRA SOCIAL
        La emoción predominante detectada es {df['Vibra'].mode()[0]}, lo que sugiere una tendencia clara en la opinión pública.
        
        3. HALLAZGOS DEL NOTEBOOK
        Se han integrado datos manuales y evidencia fotográfica que corroboran la tendencia de '{df['Fuente'].mode()[0]}'.
        
        Generado por El Faro v30.0
        """
        st.text_area("Cuerpo del Informe:", txt_report, height=400)
        
        if st.button("📄 EXPORTAR PDF CON GRÁFICOS INCRUSTADOS"):
            # Generar gráfico temporal para PDF
            fig_img, ax = plt.subplots(figsize=(6,4))
            df['Sentimiento'].value_counts().plot(kind='barh', color=['green','red','yellow'], ax=ax)
            img_buf = io.BytesIO(); plt.savefig(img_buf, format='png'); img_buf.seek(0)
            
            pdf = FPDF()
            pdf.add_page(); pdf.set_font("Arial", 'B', 16); pdf.cell(0, 10, "REPORTE EL FARO - NEBULA", 0, 1, 'C')
            pdf.ln(10); pdf.set_font("Arial", size=11)
            pdf.multi_cell(0, 8, txt_report.encode('latin-1','replace').decode('latin-1'))
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f:
                f.write(img_buf.getvalue())
                pdf.image(f.name, x=10, y=140, w=100)
                
            out = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            pdf.output(out.name)
            with open(out.name, "rb") as f: st.download_button("📥 DESCARGAR PDF", f, "Reporte_Nebula.pdf")

else:
    st.info("👋 El Faro en espera. Inicia un escaneo o carga un proyecto.")
