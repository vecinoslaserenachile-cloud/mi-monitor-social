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
import streamlit.components.v1 as components

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="El Faro | Legacy Stability", layout="wide", page_icon="lighthouse")

# --- 2. GESTIÓN DE DATOS BLINDADA (AUTO-REPARACIÓN) ---
REQUIRED_COLS = ['Fecha', 'Fuente', 'Titular', 'Link', 'Sentimiento', 'Alcance', 'Interacciones', 'Vibra', 'Lugar', 'Tipo']

if 'data_master' not in st.session_state:
    st.session_state.data_master = pd.DataFrame(columns=REQUIRED_COLS)

# AUTO-REPARACIÓN: Si la sesión antigua tiene columnas viejas, las rellenamos
if not st.session_state.data_master.empty:
    for col in REQUIRED_COLS:
        if col not in st.session_state.data_master.columns:
            st.session_state.data_master[col] = 0 if col in ['Alcance', 'Interacciones'] else "N/A"

if 'proyectos' not in st.session_state: st.session_state.proyectos = {}
if 'search_active' not in st.session_state: st.session_state.search_active = False

# --- 3. ESTILOS VISUALES (EL FARO ORIGINAL + TEXTO BLANCO) ---
# Velocidad de rotación dinámica
speed = "2s" if st.session_state.search_active else "12s"

st.markdown(f"""
    <style>
    /* FUENTE */
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700;900&display=swap');
    
    /* FONDO NEGRO PROFUNDO */
    .stApp, .main {{ background-color: #020617 !important; color: #FFFFFF !important; font-family: 'Montserrat', sans-serif; }}
    
    /* 1. SOLUCIÓN FINAL AL FLASH DEL MAPA */
    iframe {{ background-color: #020617 !important; }}
    
    /* 2. TEXTOS DE MÉTRICAS -> BLANCO PURO OBLIGATORIO */
    [data-testid="stMetricLabel"] p {{
        color: #FFFFFF !important;
        font-size: 15px !important;
        font-weight: 800 !important;
        text-transform: uppercase !important;
        opacity: 1 !important;
    }}
    [data-testid="stMetricLabel"] {{ opacity: 1 !important; }}
    
    [data-testid="stMetricValue"] {{ 
        color: #00F0FF !important; 
        font-size: 42px !important; 
        font-weight: 900 !important;
        text-shadow: 0 0 15px rgba(0,240,255,0.4);
    }}
    
    /* TARJETA KPI */
    [data-testid="stMetric"] {{
        background: linear-gradient(180deg, #0F172A 0%, #1E293B 100%) !important;
        border: 1px solid #00F0FF !important;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5) !important;
    }}

    /* TABS */
    .stTabs [aria-selected="true"] {{ background-color: #00F0FF !important; color: #000 !important; font-weight: 900; }}
    
    /* TITULOS */
    h1, h2, h3 {{ color: #ffffff !important; text-shadow: 0 0 10px rgba(0,0,0,0.5); }}
    </style>
    """, unsafe_allow_html=True)

# --- 4. MOTOR INTELIGENCIA ---
@st.cache_resource
def load_ia():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def normalizar(txt, ia):
    res = ia(txt[:512])[0]
    sc = int(res['label'].split()[0])
    s = "🔴 Negativo" if sc <= 2 else "🟡 Neutro" if sc == 3 else "🟢 Positivo"
    
    t = txt.lower()
    e = "😐 Neutral"
    if any(x in t for x in ['miedo','terror','delito','portonazo']): e = "😱 Miedo"
    elif any(x in t for x in ['ira','odio','vergüenza','robo']): e = "🤬 Ira"
    elif any(x in t for x in ['feliz','éxito','logro','ganador']): e = "🎉 Alegría"
    elif any(x in t for x in ['triste','pena','lamentable']): e = "😢 Tristeza"
    
    l = "La Serena"
    if "coquimbo" in t: l = "Coquimbo"
    
    return s, e, l

# --- 5. SIDEBAR (FARO ORIGINAL EN IFRAME) ---
# Usamos el HTML del faro SVG que te gustaba, dentro de un iframe para no parpadear
with st.sidebar:
    faro_html = f"""
    <div style="width:100%; height:200px; background:radial-gradient(circle at bottom, #0f172a 0%, transparent 80%); position:relative; overflow:hidden; border-bottom:2px solid #00F0FF; margin-bottom:20px; display:flex; justify-content:center; align-items:flex-end;">
        <div style="position:absolute; bottom:80px; left:50%; margin-left:-300px; width:600px; height:600px; 
             background:conic-gradient(from 0deg at 50% 50%, rgba(0,240,255,0.4) 0deg, transparent 60deg);
             transform-origin:50% 50%; animation: spin {speed} linear infinite;"></div>
        
        <svg width="80px" height="140px" viewBox="0 0 100 200" style="position:relative; z-index:10; filter:drop-shadow(0 0 10px #00F0FF);">
            <path d="M35,190 L65,190 L60,50 L40,50 Z" fill="#E2E8F0" stroke="#38BDF8" stroke-width="2"/>
            <rect x="35" y="30" width="30" height="20" fill="#FACC15" rx="2" stroke="#FACC15"/>
            <path d="M30,30 L50,10 L70,30 Z" fill="#0F172A" stroke="#38BDF8" stroke-width="2"/>
            <rect x="42" y="50" width="16" height="140" fill="#64748B" opacity="0.3"/>
        </svg>
        
        <style>@keyframes spin {{ 0% {{transform: rotate(0deg);}} 100% {{transform: rotate(360deg);}} }}</style>
    </div>
    """
    components.html(faro_html, height=200)
    
    st.title("EL FARO")
    st.caption("Sentinel Legacy v38.0")
    
    obj_in = st.text_input("Objetivo", "Daniela Norambuena")
    
    if st.button("🔥 ACTIVAR RADAR (TURBO)", type="primary"):
        st.session_state.search_active = True
        st.rerun()

    # Lógica de escaneo
    if st.session_state.search_active:
        ia = load_ia()
        prog = st.progress(0)
        data = []
        bases = ["noticias", "polémica", "redes", "gestión"]
        
        for i, b in enumerate(bases):
            time.sleep(0.3)
            # Simulación de datos basada en input real
            for _ in range(random.randint(5, 8)):
                t = f"{b} sobre {obj_in} {random.randint(1,100)}"
                s, e, l = normalizar(t, ia)
                src = random.choice(['El Día', 'BioBio', 'Twitter', 'Instagram'])
                alcance = random.randint(1000, 50000)
                data.append({
                    'Fecha': datetime.now().date(), 'Fuente': src,
                    'Titular': t, 'Link': '#', 'Sentimiento': s, 'Alcance': alcance,
                    'Interacciones': int(alcance * random.uniform(0.01, 0.05)), 'Vibra': e, 'Lugar': l, 'Tipo': 'Web'
                })
            prog.progress((i+1)/len(bases))
            
        st.session_state.data_master = pd.DataFrame(data)
        st.session_state.search_active = False
        st.rerun()

# --- 6. DASHBOARD ---
df = st.session_state.data_master
if not df.empty:
    st.markdown(f"## 🦾 Centro de Mando: {obj_in.upper()}")
    
    # KPIs FORZADOS A BLANCO
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("MENCIONES TOTALES", len(df))
    k2.metric("ALCANCE (IMP)", f"{df['Alcance'].sum()/1000000:.1f}M")
    k3.metric("INTERACCIONES", f"{df['Interacciones'].sum()/1000:.1f}K")
    pos_perc = int(len(df[df.Sentimiento.str.contains("Positivo")])/len(df)*100) if len(df) > 0 else 0
    k4.metric("FAVORABILIDAD", f"{pos_perc}%")
    
    tabs = st.tabs(["📊 ESTRATEGIA", "🎭 EMOCIONES", "🗺️ TÁCTICO", "🌪️ EMBUDO", "📝 ANTECEDENTES", "📄 REPORTE"])
    
    # TAB 1: ESTRATEGIA
    with tabs[0]:
        st.subheader("Tendencia de Impacto")
        # Grafico Dual Axis
        daily = df.groupby('Fecha').agg({'Titular':'count', 'Alcance':'sum'}).reset_index()
        fig_dual = go.Figure()
        fig_dual.add_trace(go.Scatter(x=daily['Fecha'], y=daily['Titular'], name='Menciones', line=dict(color='#00F0FF', width=3)))
        fig_dual.add_trace(go.Scatter(x=daily['Fecha'], y=daily['Alcance'], name='Alcance', yaxis='y2', line=dict(color='#A855F7', width=3, dash='dot')))
        fig_dual.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(title="Volumen"), yaxis2=dict(title="Alcance", overlaying='y', side='right'),
            legend=dict(orientation="h", y=1.1)
        )
        st.plotly_chart(fig_dual, use_container_width=True)

        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown("### 🕸️ Ecosistema")
            fig_sun = px.sunburst(df, path=['Sentimiento', 'Fuente'], color='Sentimiento',
                                  color_discrete_map={'🟢 Positivo':'#00FF00', '🔴 Negativo':'#FF0000', '🟡 Neutro':'#FFFF00'})
            fig_sun.update_traces(textinfo="label+percent entry", textfont=dict(size=18, color="white"))
            fig_sun.update_layout(height=500, paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_sun, use_container_width=True)
        with c2:
            st.markdown("### 🌳 Mapa de Conceptos")
            fig_tree = px.treemap(df, path=['Lugar', 'Fuente', 'Titular'], color='Sentimiento',
                                  color_discrete_map={'🟢 Positivo':'#00FF00', '🔴 Negativo':'#FF0000', '🟡 Neutro':'#FFFF00'})
            fig_tree.update_traces(textinfo="label+value", textfont=dict(size=24, color="white"))
            fig_tree.update_layout(height=500, margin=dict(t=0,l=0,r=0,b=0))
            st.plotly_chart(fig_tree, use_container_width=True)

    # TAB 2: EMOCIONES
    with tabs[1]:
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("### 📡 Radar de Vibras")
            df_e = df['Vibra'].value_counts().reset_index()
            df_e.columns = ['Vibra', 'Count']
            fig_r = px.line_polar(df_e, r='Count', theta='Vibra', line_close=True, template="plotly_dark")
            fig_r.update_traces(fill='toself', line_color='#00F0FF')
            st.plotly_chart(fig_r, use_container_width=True)
        with c4:
            st.markdown("### 🥧 Share de Medios")
            fig_p = px.pie(df, names='Fuente', hole=0.5, color_discrete_sequence=px.colors.sequential.Cyan)
            fig_p.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_p, use_container_width=True)

    # TAB 3: TÁCTICO (MAPA OSCURO)
    with tabs[2]:
        st.markdown("### 📍 Despliegue Territorial")
        m = folium.Map(location=[-29.90, -71.25], zoom_start=12, tiles="CartoDB dark_matter")
        mc = MarkerCluster().add_to(m)
        for _, r in df.iterrows():
            folium.Marker([random.uniform(-29.95,-29.85), random.uniform(-71.3,-71.2)], popup=r['Titular']).add_to(mc)
        st_folium(m, width="100%", height=500)

    # TAB 4: EMBUDO (GADGET RECUPERADO)
    with tabs[3]:
        st.markdown("### 🌪️ Embudo de Conversión")
        fig_fun = px.funnel(pd.DataFrame({
            'Etapa': ['Alcance Potencial', 'Lecturas Estimadas', 'Interacciones', 'Viralización'],
            'Valor': [df['Alcance'].sum(), df['Alcance'].sum()*0.3, df['Interacciones'].sum(), df['Interacciones'].sum()*0.1]
        }), x='Valor', y='Etapa')
        fig_fun.update_traces(marker=dict(color=["#00F0FF", "#00BFFF", "#1E90FF", "#0000FF"]))
        fig_fun.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_fun, use_container_width=True)

    # TAB 5: ANTECEDENTES
    with tabs[4]:
        st.markdown("### 📝 Ingesta de Antecedentes")
        with st.form("add_data"):
            txt = st.text_area("Texto / Nota")
            src = st.text_input("Fuente")
            if st.form_submit_button("💾 GUARDAR"):
                new = df.iloc[0].to_dict()
                new['Titular'] = txt; new['Fuente'] = src; new['Tipo'] = 'Manual'
                st.session_state.data_master = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
                st.success("Guardado")
                st.rerun()

    # TAB 6: REPORTE
    with tabs[5]:
        st.markdown("### 📄 Generador de Informes")
        if st.button("DESCARGAR PDF"):
            pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", size=12)
            pdf.cell(0, 10, f"INFORME EL FARO: {obj_in}", 0, 1)
            pdf.multi_cell(0, 10, f"Total Menciones: {len(df)}\nAlcance: {df['Alcance'].sum()}")
            out = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            pdf.output(out.name)
            with open(out.name, "rb") as f: st.download_button("📥 BAJAR PDF", f, "reporte.pdf")

else:
    st.info("👋 Inicia el escaneo con el botón 🔥 en el panel lateral.")
