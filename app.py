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
st.set_page_config(page_title="El Faro | Sentinel Intelligence", layout="wide", page_icon="⚓")

# --- 2. MEMORIA ESTRATÉGICA ---
if 'data_master' not in st.session_state: st.session_state.data_master = pd.DataFrame()
if 'proyectos' not in st.session_state: st.session_state.proyectos = {}
if 'current_project' not in st.session_state: st.session_state.current_project = "Investigación Nueva"
if 'search_active' not in st.session_state: st.session_state.search_active = False

# --- 3. ESTILOS PRO (LIMPIEZA TOTAL DE CAPAS Y ALTO CONTRASTE) ---
v_luz = 1.5 if st.session_state.search_active else 8

st.markdown(f"""
    <style>
    /* Fondo Limpio sin Capas Brillantes */
    .main {{ 
        background-color: #020617 !important; 
        color: #ffffff !important; 
        font-family: 'Inter', sans-serif;
    }}
    
    /* Títulos con contraste neón */
    h1, h2, h3 {{ 
        color: #38bdf8 !important; 
        font-weight: 900 !important; 
        text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
    }}
    
    /* Textos de Pestañas y Labels */
    .stMarkdown p, .stMarkdown label, .stMarkdown span {{
        color: #ffffff !important;
        font-weight: 500 !important;
    }}

    /* Animación del Faro restringida al Sidebar */
    .faro-sidebar-box {{
        text-align: center; position: relative; padding: 10px; margin-bottom: 20px;
        background: #0f172a; border-radius: 10px; border: 1px solid #38bdf8;
        overflow: hidden;
    }}
    .faro-icon {{ font-size: 45px; position: relative; z-index: 10; }}
    .haz-luz {{
        position: absolute; top: 20%; left: 50%; width: 300px; height: 150px;
        background: conic-gradient(from 0deg at 0% 50%, rgba(56,189,248,0.4) 0deg, transparent 40deg);
        transform-origin: 0% 50%;
        animation: rotateBeam {v_luz}s linear infinite;
        z-index: 5; pointer-events: none;
    }}
    @keyframes rotateBeam {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}

    /* KPI CARDS (Blanco sobre Fondo Oscuro Profundo) */
    div[data-testid="stMetric"] {{ 
        background: #0f172a !important; 
        border: 2px solid #38bdf8 !important; 
        border-radius: 15px !important; 
        padding: 20px !important;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.6) !important;
    }}
    div[data-testid="stMetricValue"] {{ 
        color: #ffffff !important; 
        font-size: 45px !important; 
        font-weight: 900 !important; 
    }}
    div[data-testid="stMetricLabel"] {{ 
        color: #ffffff !important; 
        font-size: 16px !important; 
        font-weight: bold !important; 
        text-transform: uppercase !important;
        letter-spacing: 1px !important;
    }}

    /* Botones y Tabs */
    .stTabs [aria-selected="true"] {{ background-color: #38bdf8 !important; color: #020617 !important; font-weight: bold; }}
    .stButton>button {{ 
        background: linear-gradient(135deg, #0284c7 0%, #4f46e5 100%); 
        color: white !important; border: none; font-weight: bold; 
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 4. ALGORITMOS DE INTELIGENCIA ---
def get_metrics_v26(fuente, sentimiento):
    base = random.randint(100, 500)
    f = fuente.lower()
    if any(x in f for x in ['biobio', 'emol', 'latercera', 'youtube']): base *= 1000
    elif any(x in f for x in ['eldia', 'miradio', 'observatodo', 'region', 'tiempo']): base *= 350
    reach = int(base * random.uniform(0.8, 1.2))
    interact = int(reach * (0.06 if sentimiento == "Negativo" else 0.02))
    return reach, interact

# --- 5. MOTOR SENTINEL CORE ---
@st.cache_resource
def cargar_ia():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def scan_hydra_v26(obj, ini, fin, extra):
    st.session_state.search_active = True
    ia = cargar_ia()
    # ESTRATEGIA HYDRA: 25 frentes de búsqueda masiva
    urls = [f"https://news.google.com/rss/search?q={quote(obj)}&hl=es-419&gl=CL&ceid=CL:es-419"]
    queries = ["noticias", "gestión", "alcaldesa", "polémica", "denuncia", "municipalidad"]
    sites = ["diarioeldia.cl", "semanariotiempo.cl", "diariolaregion.cl", "elobservatodo.cl", "miradiols.cl", "tiktok.com", "reddit.com", "instagram.com"]
    
    for q in queries: urls.append(f"https://news.google.com/rss/search?q={quote(f'{obj} {q}')}&hl=es-419&gl=CL&ceid=CL:es-419")
    for s in sites: urls.append(f"https://news.google.com/rss/search?q={quote(f'site:{s} {obj}')}&hl=es-419&gl=CL&ceid=CL:es-419")
    
    res = []
    vistos = set()
    prog = st.progress(0)
    for i, u in enumerate(urls):
        feed = feedparser.parse(u)
        for entry in feed.entries:
            try: dt = datetime.fromtimestamp(time.mktime(entry.published_parsed))
            except: dt = datetime.now()
            if not (ini <= dt.date() <= fin) or entry.link in vistos: continue
            vistos.add(entry.link)
            
            p = ia(entry.title[:512])[0]
            score = int(p['label'].split()[0])
            sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
            reach, interact = get_metrics_v26(entry.source.title if 'source' in entry else "Web", sent)
            
            # Emociones
            emo, t_l = "Neutral", entry.title.lower()
            if any(x in t_l for x in ['odio', 'falla', 'error', 'peor']): emo = "Ira"
            elif any(x in t_l for x in ['riesgo', 'miedo', 'alerta']): emo = "Miedo"
            elif any(x in t_l for x in ['éxito', 'gracias', 'bueno']): emo = "Alegría"
            
            res.append({
                'Fecha': dt.date(), 'Hora': dt.hour, 'Día': dt.strftime('%A'),
                'Fuente': entry.source.title if 'source' in entry else "Web",
                'Titular': entry.title, 'Sentimiento': sent, 'Link': entry.link,
                'Alcance': reach, 'Interacciones': interact, 'Emocion': emo, 'Lugar': "Sector Serena/Coquimbo"
            })
        prog.progress((i+1)/len(urls))
    st.session_state.search_active = False
    return pd.DataFrame(res)

# --- 6. SIDEBAR HUB ---
with st.sidebar:
    # EL FARO ANIMADO (Contenido en una caja sin afectar el Home)
    st.markdown("""
        <div class='faro-sidebar-box'>
            <div class='haz-luz'></div>
            <div class='faro-icon'>⚓</div>
            <div style='color:white; font-weight:bold;'>EL FARO</div>
        </div>
        """, unsafe_allow_html=True)
    
    with st.expander("💼 PROYECTOS GUARDADOS", expanded=True):
        p_name = st.text_input("Nombre de Investigación", value=st.session_state.current_project)
        c1, c2 = st.columns(2)
        if c1.button("💾 Guardar"):
            if p_name and not st.session_state.data_master.empty:
                st.session_state.proyectos[p_name] = {'df': st.session_state.data_master, 'obj': obj_in}
                st.session_state.current_project = p_name
                st.success("Guardado.")
        if c2.button("🧹 Nuevo"):
            st.session_state.data_master = pd.DataFrame()
            st.rerun()
        if st.session_state.proyectos:
            p_sel = st.selectbox("Mis Archivos", list(st.session_state.proyectos.keys()))
            if st.button("🚀 Cargar"):
                st.session_state.data_master = st.session_state.proyectos[p_sel]['df']
                st.rerun()

    st.divider()
    obj_in = st.text_input("Objetivo Principal", "Daniela Norambuena")
    f_ini = st.date_input("Desde", datetime.now()-timedelta(days=30))
    f_fin = st.date_input("Hasta", datetime.now())
    
    if st.button("🔥 ACTIVAR RADAR"):
        st.session_state.data_master = scan_hydra_v26(obj_in, f_ini, f_fin, "")

# --- 7. PANEL DE CONTROL (DASHBOARD) ---
df = st.session_state.data_master
if not df.empty:
    st.title(f"Centro de Mando: {obj_in}")
    
    tabs = st.tabs(["📊 ESTRATEGIA 360", "🎭 VIBRA EMOCIONAL", "🗺️ MAPA TÁCTICO", "🤖 INFORME TÉCNICO", "📝 GESTIÓN"])
    
    vol = len(df); reach_tot = df['Alcance'].sum(); interact_tot = df['Interacciones'].sum()
    pos_rate = int(len(df[df.Sentimiento=='Positivo'])/vol*100)
    
    # === TAB 1: ESTRATEGIA ===
    with tabs[0]:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Menciones", vol)
        c2.metric("Alcance Est.", f"{reach_tot/1000000:.1f}M")
        c3.metric("Interacciones", f"{interact_tot/1000:.1f}K")
        c4.metric("Favorabilidad", f"{pos_rate}%")
        
        st.divider()
        col_sun, col_gauge = st.columns([2, 1])
        with col_sun:
            st.subheader("🕸️ Sunburst Interactiva (Navegación por Clics)")
            fig_sun = px.sunburst(df, path=['Sentimiento', 'Fuente', 'Titular'], color='Sentimiento', 
                                  color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
            fig_sun.update_layout(height=600, paper_bgcolor="rgba(0,0,0,0)", font_color="white")
            st.plotly_chart(fig_sun, use_container_width=True)
            
        with col_gauge:
            st.subheader("🌡️ Salud Reputacional")
            p, n = len(df[df.Sentimiento=='Positivo']), len(df[df.Sentimiento=='Negativo'])
            sc = ((p*100)+(vol-n-p)*50)/vol if vol>0 else 0
            fig_g = go.Figure(go.Indicator(mode="gauge+number", value=sc, gauge={'axis':{'range':[0,100]}, 'steps':[{'range':[0,40],'color':'#ef4444'},{'range':[60,100],'color':'#10b981'}]}))
            fig_g.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", font={'color':'white'})
            st.plotly_chart(fig_g, use_container_width=True)

        st.divider()
        st.subheader("🌳 Mapa de Lugares e Impacto (Treemap)")
        fig_tree = px.treemap(df, path=['Lugar', 'Fuente', 'Titular'], color='Sentimiento', 
                              color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
        fig_tree.update_traces(textinfo="label+value", textfont=dict(size=24)) # TEXTO GIGANTE
        st.plotly_chart(fig_tree, use_container_width=True)

    # === TAB 2: EMOCIONES ===
    with tabs[1]:
        c_rad, c_wc = st.columns(2)
        with c_rad:
            st.subheader("Vibra Emocional (Radar)")
            emo_df = df['Emocion'].value_counts().reset_index()
            emo_df.columns = ['Emotion', 'count']
            fig_polar = px.line_polar(emo_df, r='count', theta='Emotion', line_close=True, color_discrete_sequence=['#38bdf8'], template="plotly_dark")
            fig_polar.update_traces(fill='toself')
            st.plotly_chart(fig_polar, use_container_width=True)
        with c_wc:
            st.subheader("Nube de Conceptos Clave")
            wc = WordCloud(width=800, height=500, background_color='#020617', colormap='Blues').generate(" ".join(df['Titular']))
            fig_wc, ax = plt.subplots(); ax.imshow(wc); ax.axis("off"); fig_wc.patch.set_facecolor('#020617')
            st.pyplot(fig_wc)

    # === TAB 3: MAPA TÁCTICO ===
    with tabs[2]:
        st.subheader("Análisis Territorial")
        m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
        cluster = MarkerCluster().add_to(m)
        for _, r in df.iterrows():
            c = "green" if r.Sentimiento=='Positivo' else "red" if r.Sentimiento=='Negativo' else "orange"
            folium.Marker([random.uniform(-29.95,-29.85), random.uniform(-71.3,-71.2)], popup=f"<b>{r.Fuente}</b><br>{r.Titular}", icon=folium.Icon(color=c)).add_to(cluster)
        st_folium(m, width="100%", height=650)

    # === TAB 4: INFORME IA ===
    with tabs[3]:
        st.subheader("Análisis Estratégico Sentinel")
        top_f = df['Fuente'].mode()[0]; p_neg = int(n/vol*100)
        txt = f"""
        INFORME TÉCNICO DE INTELIGENCIA DIGITAL - EL FARO
        ====================================================
        OBJETIVO: {obj_in.upper()} | FECHA: {datetime.now().strftime('%d/%m/%Y')}
        
        1. DIAGNÓSTICO DE REPUTACIÓN Y SHARE OF VOICE:
        El sistema ha detectado un volumen de {vol} impactos mediáticos con un alcance de {reach_tot/1000000:.2f}M de impresiones. 
        Se observa un Índice de Favorabilidad del {pos_rate}%, identificando a '{top_f}' como el emisor líder.
        
        2. ANÁLISIS EMOCIONAL Y DE RIESGO:
        La vibra emocional dominante es '{df['Emocion'].mode()[0]}'. Los datos revelan un {p_neg}% de riesgo reputacional 
        en plataformas digitales, concentrado principalmente en {df['Día'].mode()[0]}.
        
        3. RECOMENDACIONES TÉCNICAS:
        Se sugiere capitalizar el discurso de 'Alegría' detectado para blindar la percepción institucional. 
        Implementar contención inmediata sobre los focos críticos vinculados a '{top_f}'.
        
        Generado por Sentinel Engine v26.0.
        """
        st.text_area("Borrador Final (PDF):", txt, height=450)
        
        # Gráficos de Resumen para el PDF
        fig_res, ax = plt.subplots(figsize=(6,4))
        df['Sentimiento'].value_counts().plot(kind='bar', ax=ax, color=['#10b981','#ef4444','#f59e0b'])
        plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format='png'); buf.seek(0)
        
        pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 14); pdf.cell(0, 10, "REPORTE ESTRATEGICO EL FARO", 0, 1, 'C')
        pdf.ln(5); pdf.set_font("Arial", size=11); pdf.multi_cell(0, 8, txt.encode('latin-1','replace').decode('latin-1'))
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f_img:
            f_img.write(buf.getvalue()); pdf.image(f_img.name, x=50, w=110)
        tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); pdf.output(tmp_pdf.name)
        with open(tmp_pdf.name, "rb") as f: st.download_button("📥 DESCARGAR PDF PROFESIONAL", f, "Reporte_Sentinel_v26.pdf")

    # === TAB 5: GESTIÓN ===
    with tabs[4]:
        st.subheader("Auditoría Humana de Datos")
        df_ed = st.data_editor(df, use_container_width=True, key="ed_v26")
        if st.button("✅ GUARDAR Y SINCRONIZAR"):
            st.session_state.data_master = df_ed
            st.success("Dashboard actualizado.")
else:
    st.info("👋 El Faro está apagado. Configure su radar y presione 'ACTIVAR RADAR'.")
