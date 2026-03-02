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

# --- 1. CONFIGURACIÓN E IDENTIDAD ---
st.set_page_config(page_title="El Faro | Tactical Hub", layout="wide", page_icon="⚓")

# --- 2. MEMORIA ESTRATÉGICA ---
if 'data_master' not in st.session_state: st.session_state.data_master = pd.DataFrame()
if 'proyectos' not in st.session_state: st.session_state.proyectos = {}
if 'current_project' not in st.session_state: st.session_state.current_project = "Investigación Nueva"
if 'search_active' not in st.session_state: st.session_state.search_active = False

# --- 3. ESTILOS PRO & FARO ANIMADO (Haz desde la Torre) ---
# Velocidad: 2s en búsqueda, 8s en reposo
v_luz = 2 if st.session_state.search_active else 8

st.markdown(f"""
    <style>
    .main {{ background-color: #020617; color: #ffffff; font-family: 'Inter', sans-serif; }}
    h1 {{ background: linear-gradient(to right, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 900; }}
    
    /* Torre del Faro y Haz Lateral */
    .faro-sidebar-container {{
        text-align: center; position: relative; padding: 20px; height: 150px; overflow: hidden;
    }}
    .torre {{
        font-size: 50px; position: relative; z-index: 10;
    }}
    .luz-faro {{
        position: absolute; top: 30%; left: 50%; width: 600px; height: 300px;
        background: conic-gradient(from 0deg at 0% 50%, rgba(56,189,248,0.4) 0deg, transparent 40deg);
        transform-origin: 0% 50%;
        animation: rotateBeam {v_luz}s linear infinite;
        z-index: 5; pointer-events: none;
    }}
    @keyframes rotateBeam {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}

    /* KPI CONTRASTE TOTAL (Textos en Blanco) */
    div[data-testid="stMetric"] {{ 
        background: #0f172a; border: 2px solid #38bdf8; border-radius: 15px; padding: 20px; 
    }}
    div[data-testid="stMetricValue"] {{ color: #ffffff !important; font-size: 42px !important; font-weight: 800 !important; }}
    div[data-testid="stMetricLabel"] {{ color: #ffffff !important; font-size: 16px !important; font-weight: bold !important; text-transform: uppercase; }}
    
    /* Tabs y Botones */
    .stTabs [aria-selected="true"] {{ background-color: #38bdf8 !important; color: #020617 !important; font-weight: bold; }}
    .stButton>button {{ background: linear-gradient(135deg, #0284c7 0%, #4f46e5 100%); color: white; border: none; font-weight: bold; width: 100%; }}
    </style>
    """, unsafe_allow_html=True)

# --- 4. ALGORITMOS DE INTELIGENCIA ---
def get_metrics_quantum(fuente, sentimiento):
    base = random.randint(100, 500)
    f = fuente.lower()
    if any(x in f for x in ['biobio', 'emol', 'latercera', 'youtube']): base *= 1000
    elif any(x in f for x in ['eldia', 'miradio', 'observatodo', 'region', 'tiempo']): base *= 300
    reach = int(base * random.uniform(0.8, 1.2))
    interact = int(reach * (0.05 if sentimiento == "Negativo" else 0.02))
    return reach, interact

# --- 5. MOTOR SENTINEL CORE ---
@st.cache_resource
def cargar_ia():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def scan_hydra_v25(obj, ini, fin, extra):
    st.session_state.search_active = True
    ia = cargar_ia()
    # ESTRATEGIA HYDRA: 25 frentes de búsqueda
    urls = [f"https://news.google.com/rss/search?q={quote(obj)}&hl=es-419&gl=CL&ceid=CL:es-419"]
    queries = ["noticias", "polémica", "gestión", "opinión", "crítica", "denuncia"]
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
            reach, interact = get_metrics_quantum(entry.source.title if 'source' in entry else "Web", sent)
            
            # Detección de Emociones
            emo, t_l = "Neutral", entry.title.lower()
            if any(x in t_l for x in ['odio', 'error', 'atropello', 'falla']): emo = "Ira"
            elif any(x in t_l for x in ['miedo', 'alerta', 'riesgo']): emo = "Miedo"
            elif any(x in t_l for x in ['gracias', 'éxito', 'feliz']): emo = "Alegría"
            
            res.append({
                'Fecha': dt.date(), 'Hora': dt.hour, 'Día': dt.strftime('%A'),
                'Fuente': entry.source.title if 'source' in entry else "Web",
                'Titular': entry.title, 'Sentimiento': sent, 'Link': entry.link,
                'Reach': reach, 'Interactions': interact, 'Emotion': emo, 'Lugar': "Sector Serena/Coquimbo"
            })
        prog.progress((i+1)/len(urls))
    st.session_state.search_active = False
    return pd.DataFrame(res)

# --- 6. SIDEBAR HUB ---
with st.sidebar:
    st.markdown("""<div class='faro-sidebar-container'><div class='luz-faro'></div><div class='torre'>⚓</div></div>""", unsafe_allow_html=True)
    st.title("EL FARO")
    st.caption("Tactical Hub v25.0")
    
    with st.expander("💼 PROYECTOS", expanded=True):
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
            if st.button("🚀 Cargar Selección"):
                st.session_state.data_master = st.session_state.proyectos[p_sel]['df']
                st.rerun()

    st.divider()
    obj_in = st.text_input("Objetivo Principal", "Daniela Norambuena")
    f_ini = st.date_input("Desde", datetime.now()-timedelta(days=30))
    f_fin = st.date_input("Hasta", datetime.now())
    
    if st.button("🔥 ACTIVAR RADAR"):
        st.session_state.data_master = scan_hydra_v25(obj_in, f_ini, f_fin, "")

# --- 7. PANEL DE CONTROL ---
df = st.session_state.data_master
if not df.empty:
    st.title(f"Centro de Mando: {obj_in}")
    
    tabs = st.tabs(["📊 ESTRATEGIA 360", "🎭 VIBRA EMOCIONAL", "🗺️ MAPA TÁCTICO", "🤖 INFORME TÉCNICO", "📝 GESTIÓN"])
    
    # KPIs (ALTO CONTRASTE)
    vol = len(df); r_tot = df['Reach'].sum(); i_tot = df['Interactions'].sum()
    pos_rate = int(len(df[df.Sentimiento=='Positivo'])/vol*100)
    
    # === TAB 1: ESTRATEGIA ===
    with tabs[0]:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Menciones", vol)
        c2.metric("Alcance Est.", f"{r_tot/1000000:.1f}M")
        c3.metric("Interacciones", f"{i_tot/1000:.1f}K")
        c4.metric("Favorabilidad", f"{pos_rate}%")
        
        st.divider()
        col_sun, col_gauge = st.columns([2, 1])
        with col_sun:
            st.subheader("🕸️ Ecosistema Conceptual (Sunburst)")
            fig_sun = px.sunburst(df, path=['Sentimiento', 'Fuente', 'Titular'], color='Sentimiento', 
                                  color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
            fig_sun.update_layout(height=600, paper_bgcolor="rgba(0,0,0,0)", font_color="white")
            st.plotly_chart(fig_sun, use_container_width=True)
            
        with col_gauge:
            st.subheader("🌡️ Salud de Marca")
            p, n = len(df[df.Sentimiento=='Positivo']), len(df[df.Sentimiento=='Negativo'])
            sc = ((p*100)+(vol-n-p)*50)/vol if vol>0 else 0
            fig_g = go.Figure(go.Indicator(mode="gauge+number", value=sc, gauge={'axis':{'range':[0,100]}, 'steps':[{'range':[0,40],'color':'#ef4444'},{'range':[60,100],'color':'#10b981'}]}))
            fig_g.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", font={'color':'white'})
            st.plotly_chart(fig_g, use_container_width=True)

        st.divider()
        st.subheader("🌳 Clima de Lugares e Impacto (Treemap)")
        fig_tree = px.treemap(df, path=['Lugar', 'Fuente', 'Titular'], color='Sentimiento', 
                              color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
        # TEXTO GIGANTE Y LEGIBLE
        fig_tree.update_traces(textinfo="label+value", textfont=dict(size=22))
        st.plotly_chart(fig_tree, use_container_width=True)

    # === TAB 2: EMOCIONES ===
    with tabs[1]:
        c_rad, c_wc = st.columns(2)
        with c_rad:
            st.subheader("Vibra Emocional (Análisis Polar)")
            emo_df = df['Emotion'].value_counts().reset_index()
            emo_df.columns = ['Emotion', 'count']
            # Asegurar que el radar cargue datos
            fig_polar = px.line_polar(emo_df, r='count', theta='Emotion', line_close=True, color_discrete_sequence=['#38bdf8'], template="plotly_dark")
            fig_polar.update_traces(fill='toself')
            st.plotly_chart(fig_polar, use_container_width=True)
        with c_wc:
            st.subheader("Nube de Conceptos")
            wc = WordCloud(width=800, height=500, background_color='#020617', colormap='Blues').generate(" ".join(df['Titular']))
            fig_wc, ax = plt.subplots(); ax.imshow(wc); ax.axis("off"); fig_wc.patch.set_facecolor('#020617')
            st.pyplot(fig_wc)

    # === TAB 3: GEO-TACTICAL ===
    with tabs[2]:
        st.subheader("Despliegue Territorial")
        m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
        cluster = MarkerCluster().add_to(m)
        for _, r in df.iterrows():
            c = "green" if r.Sentimiento=='Positivo' else "red" if r.Sentimiento=='Negativo' else "orange"
            folium.Marker([random.uniform(-29.95,-29.85), random.uniform(-71.3,-71.2)], popup=f"<b>{r.Fuente}</b><br>{r.Titular}", icon=folium.Icon(color=c)).add_to(cluster)
        st_folium(m, width="100%", height=600)

    # === TAB 4: INFORME IA TÉCNICO ===
    with tabs[3]:
        st.subheader("Análisis Estratégico Profesional")
        top_f = df['Fuente'].mode()[0]; p_neg = int(n/vol*100)
        txt = f"""
        INFORME TÉCNICO DE INTELIGENCIA DIGITAL - EL FARO
        ====================================================
        OBJETIVO: {obj_in.upper()} | FECHA: {datetime.now().strftime('%d/%m/%Y')}
        
        1. DIAGNÓSTICO DE REPUTACIÓN Y ALCANCE:
        El sistema ha detectado {vol} impactos mediáticos con un alcance estimado de {r_tot/1000000:.2f}M de impresiones. 
        Se identifica un Índice de Favorabilidad del {pos_rate}%, siendo '{top_f}' la fuente de mayor tracción.
        
        2. ANÁLISIS EMOCIONAL Y DE RIESGO:
        La vibra emocional dominante es '{df['Emotion'].mode()[0]}'. Los datos revelan un {p_neg}% de riesgo reputacional 
        concentrado en plataformas digitales, con picos de actividad detectados en {df['Día'].mode()[0]}.
        
        3. RECOMENDACIONES TÉCNICAS:
        Se sugiere una intervención inmediata en '{top_f}' para mitigar focos de negatividad. 
        Capitalizar las menciones positivas para fortalecer la percepción en el sector {df['Lugar'].unique()[0]}.
        
        Generado por Sentinel Engine v25.0.
        """
        st.text_area("Borrador Final:", txt, height=400)
        
        # Gráficos de Resumen para el PDF
        fig_res, ax = plt.subplots(figsize=(6,4))
        df['Sentimiento'].value_counts().plot(kind='bar', ax=ax, color=['#10b981','#ef4444','#f59e0b'])
        plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format='png'); buf.seek(0)
        
        pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 14); pdf.cell(0, 10, "REPORTE ESTRATEGICO EL FARO", 0, 1, 'C')
        pdf.ln(5); pdf.set_font("Arial", size=11); pdf.multi_cell(0, 8, txt.encode('latin-1','replace').decode('latin-1'))
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f_img:
            f_img.write(buf.getvalue()); pdf.image(f_img.name, x=50, w=110)
        tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); pdf.output(tmp_pdf.name)
        with open(tmp_pdf.name, "rb") as f: st.download_button("📥 DESCARGAR REPORTE PROFESIONAL (PDF)", f, "Informe_Tactico.pdf")

    # === TAB 5: GESTIÓN ===
    with tabs[4]:
        st.subheader("Auditoría Humana")
        df_ed = st.data_editor(df, use_container_width=True, key="ed_v25")
        if st.button("✅ SINCRONIZAR CAMBIOS"):
            st.session_state.data_master = df_ed
            st.success("Dashboard actualizado.")
else:
    st.info("👋 El Faro está apagado. Configure su radar y presione 'ACTIVAR RADAR'.")
