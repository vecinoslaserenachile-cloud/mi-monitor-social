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
import os

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="El Faro | Master Intelligence", layout="wide", page_icon="⚓")

# --- 2. ESTILOS PRO (FIX VISIBILIDAD) ---
st.markdown("""
    <style>
    .main { background: #0f172a; color: #f1f5f9; }
    h1 { background: linear-gradient(to right, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 900; }
    
    /* FIX KPIs: Letras blancas y fondos profundos */
    div[data-testid="stMetric"] {
        background: rgba(30, 41, 59, 0.8) !important;
        border: 1px solid rgba(56, 189, 248, 0.3) !important;
        border-radius: 12px;
        padding: 20px;
    }
    div[data-testid="stMetricLabel"] { color: #38bdf8 !important; font-size: 16px !important; font-weight: bold !important; }
    div[data-testid="stMetricValue"] { color: #ffffff !important; font-size: 32px !important; }
    
    /* Botones */
    .stButton>button {
        background: linear-gradient(135deg, #0284c7 0%, #4f46e5 100%);
        color: white; border: none; padding: 15px; border-radius: 10px; font-weight: bold; width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. MEMORIA Y ESTADO ---
if 'data_raw' not in st.session_state:
    st.session_state.data_raw = pd.DataFrame()
if 'informe_txt' not in st.session_state:
    st.session_state.informe_txt = ""

# --- 4. GEODATA ---
GEO_DB = {
    "avenida del mar": [-29.9168, -71.2785], "faro": [-29.9073, -71.2847], "centro": [-29.9027, -71.2519],
    "plaza de armas": [-29.9027, -71.2519], "las compañías": [-29.8783, -71.2389], "tierras blancas": [-29.9392, -71.2294],
    "coquimbo": [-29.9533, -71.3436], "ovalle": [-30.6015, -71.2003], "vicuña": [-30.0319, -70.7081],
    "municipalidad": [-29.9045, -71.2489], "el milagro": [-29.9333, -71.2333]
}

# --- 5. MOTOR SENTINEL ---
@st.cache_resource
def cargar_ia():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def detectar_geo(texto):
    t = texto.lower()
    for l, c in GEO_DB.items():
        if l in t: return c[0], c[1], l.title()
    return -29.9027 + random.uniform(-0.02, 0.02), -71.2519 + random.uniform(-0.02, 0.02), "General"

def clasificar_fuente(link, nombre):
    l, n = link.lower(), nombre.lower()
    social = ['twitter', 'facebook', 'instagram', 'tiktok', 'x.com', 'youtube', 'linkedin']
    if any(x in l or x in n for x in social): return "Red Social"
    return "Prensa/Medios"

def escanear_web(obj, ini, fin):
    ia = cargar_ia()
    # ESTRATEGIA HYDRA: Búsqueda múltiple
    queries = [obj, f'"{obj}"', f'{obj} noticias', f'{obj} La Serena']
    medios = ["diarioeldia.cl", "semanariotiempo.cl", "elobservatodo.cl", "miradiols.cl", "diariolaregion.cl"]
    
    urls = []
    for q in queries:
        urls.append(f"https://news.google.com/rss/search?q={quote(q)}&hl=es-419&gl=CL&ceid=CL:es-419")
    for m in medios:
        urls.append(f"https://news.google.com/rss/search?q={quote(f'site:{m} {obj}')}&hl=es-419&gl=CL&ceid=CL:es-419")
    
    resultados = []
    vistos = set()
    prog = st.progress(0)
    for i, u in enumerate(urls):
        feed = feedparser.parse(u)
        for entry in feed.entries:
            try: f_date = datetime.fromtimestamp(time.mktime(entry.published_parsed)).date()
            except: f_date = datetime.now().date()
            if not (ini <= f_date <= fin) or entry.link in vistos: continue
            vistos.add(entry.link)
            
            pred = ia(entry.title[:512])[0]
            s_val = int(pred['label'].split()[0])
            sent = "Negativo" if s_val <= 2 else "Neutro" if s_val == 3 else "Positivo"
            lat, lon, lug = detectar_geo(entry.title)
            
            resultados.append({
                'Fecha': f_date, 'Fuente': entry.source.title if 'source' in entry else "Web",
                'Titular': entry.title, 'Sentimiento': sent, 'Link': entry.link,
                'Tipo': clasificar_fuente(entry.link, entry.source.title if 'source' in entry else ""),
                'Lat': lat, 'Lon': lon, 'Lugar': lug
            })
        prog.progress((i+1)/len(urls))
    prog.empty()
    return pd.DataFrame(resultados)

# --- 6. SIDEBAR ---
with st.sidebar:
    st.markdown("# ⚓ EL FARO")
    obj_input = st.text_input("Objetivo", "Daniela Norambuena")
    c1, c2 = st.columns(2)
    f_ini = c1.date_input("Inicio", datetime.now()-timedelta(days=30))
    f_fin = c2.date_input("Fin", datetime.now())
    
    if st.button("🚀 ENCENDER EL FARO"):
        with st.spinner("Triangulando información..."):
            st.session_state.data_raw = escanear_web(obj_input, f_ini, f_fin)

# --- 7. DASHBOARD ---
if not st.session_state.data_raw.empty:
    tabs = st.tabs(["📝 GESTIÓN", "📊 ESTRATEGIA 360", "🗺️ GEO-TACTICAL", "📱 FUENTES", "📄 INFORME IA"])
    
    # --- TAB 1: GESTIÓN (EDITABLE) ---
    with tabs[0]:
        st.subheader("Validación Humana")
        # El data_editor ahora actualiza directamente el session_state
        df_edited = st.data_editor(
            st.session_state.data_raw, 
            column_config={
                "Link": st.column_config.LinkColumn("Enlace"),
                "Sentimiento": st.column_config.SelectboxColumn("Sentimiento", options=["Positivo","Negativo","Neutro","Irrelevante"])
            },
            use_container_width=True,
            num_rows="dynamic",
            key="master_editor"
        )
        st.session_state.data_raw = df_edited
        df_clean = df_edited[df_edited.Sentimiento != "Irrelevante"]

    # --- TAB 2: ESTRATEGIA ---
    with tabs[1]:
        vol = len(df_clean); pos = len(df_clean[df_clean.Sentimiento=='Positivo']); neg = len(df_clean[df_clean.Sentimiento=='Negativo'])
        k1, k2, k3 = st.columns(3)
        k1.metric("Menciones Totales", vol)
        k2.metric("Positividad", f"{int(pos/vol*100) if vol>0 else 0}%", "🟢")
        k3.metric("Riesgo Crítico", f"{int(neg/vol*100) if vol>0 else 0}%", "-🔴", delta_color="inverse")
        
        col_left, col_right = st.columns([2, 1])
        with col_left:
            st.subheader("🕸️ Sunburst Interactivo")
            fig_sun = px.sunburst(df_clean, path=['Sentimiento', 'Fuente', 'Titular'], color='Sentimiento', 
                                  color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
            fig_sun.update_layout(height=500, margin=dict(t=0,b=0,l=0,r=0), paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_sun, use_container_width=True)
            
            with st.expander("🔍 Ver Detalle y Links del Círculo"):
                st.dataframe(df_clean[['Fuente','Titular','Link']], use_container_width=True)

        with col_right:
            st.subheader("🌡️ Velocímetro de Reputación")
            sc = ((pos*100)+(vol-neg-pos)*50)/vol if vol>0 else 0
            fig_g = go.Figure(go.Indicator(
                mode="gauge+number", value=sc,
                gauge={'axis':{'range':[0,100], 'tickcolor':"white"}, 'bar':{'color':"#38bdf8"},
                       'steps':[{'range':[0,40],'color':'#ef4444'},{'range':[40,60],'color':'#f59e0b'},{'range':[60,100],'color':'#10b981'}]}))
            fig_g.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", font={'color':'white'})
            st.plotly_chart(fig_g, use_container_width=True)

        st.subheader("🌳 Treemap de Lugares e Impacto")
        fig_tree = px.treemap(df_clean, path=['Lugar', 'Fuente', 'Titular'], color='Sentimiento', 
                              color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
        fig_tree.update_layout(height=400)
        st.plotly_chart(fig_tree, use_container_width=True)

    # --- TAB 3: MAPA (GEO) ---
    with tabs[2]:
        st.subheader("Despliegue Territorial")
        m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
        for _, r in df_clean.iterrows():
            c = "green" if r.Sentimiento=='Positivo' else "red" if r.Sentimiento=='Negativo' else "orange"
            folium.Marker([r.Lat, r.Lon], popup=f"<a href='{r.Link}' target='_blank'>{r.Fuente}</a>", icon=folium.Icon(color=c)).add_to(m)
        st_folium(m, width="100%", height=550)

    # --- TAB 4: FUENTES ---
    with tabs[3]:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📰 Top 10 Medios de Prensa")
            st.bar_chart(df_clean[df_clean.Tipo != 'Red Social']['Fuente'].value_counts().head(10))
        with c2:
            st.subheader("📱 Top Redes Sociales")
            social_counts = df_clean[df_clean.Tipo == 'Red Social']['Fuente'].value_counts()
            if not social_counts.empty:
                st.bar_chart(social_counts.head(10))
                fig_p = px.pie(names=social_counts.index, values=social_counts.values, hole=0.5, title="Share Social")
                st.plotly_chart(fig_p, use_container_width=True)
            else: st.info("Buscando más datos sociales...")

    # --- TAB 5: INFORME IA ---
    with tabs[4]:
        st.subheader("🤖 Informe Narrativo de Inteligencia")
        if st.button("✍️ GENERAR ANÁLISIS ESTRATÉGICO"):
            p_perc = int(pos/vol*100); n_perc = int(neg/vol*100)
            txt = f"""
            INFORME EJECUTIVO DE INTELIGENCIA - EL FARO
            ------------------------------------------
            OBJETIVO DE MONITOREO: {obj_input.upper()}
            FECHA DE EMISIÓN: {datetime.now().strftime('%d/%m/%Y')}
            
            1. RESUMEN DE LA SITUACIÓN ACTUAL:
            Durante el periodo de análisis, el motor Sentinel ha procesado un total de {vol} menciones validadas. 
            El clima de opinión presenta una tendencia hacia lo {('Positivo' if pos>neg else 'Negativo')}, 
            con un índice de favorabilidad del {p_perc}% frente a un {n_perc}% de menciones de riesgo o críticas.
            
            2. ANÁLISIS DE FUENTES Y CANALES:
            La conversación está liderada por medios regionales, destacando la actividad en '{df_clean['Fuente'].mode()[0]}'. 
            Se observa que las Redes Sociales representan una porción activa pero volátil del discurso público.
            
            3. FOCOS GEOGRÁFICOS:
            Los temas más relevantes se concentran geográficamente en {', '.join(df_clean['Lugar'].unique()[:3])}. 
            Se recomienda prestar atención especial a los sucesos reportados en {df_clean['Lugar'].mode()[0]}.
            
            4. CONCLUSIONES Y RECOMENDACIONES:
            {('Se sugiere una estrategia de contención inmediata ante el aumento de críticas.' if n_perc > 30 else 'El escenario es de estabilidad. Se recomienda potenciar los mensajes positivos detectados.')} 
            Es vital mantener la vigilancia sobre las fuentes de prensa regional que han mostrado mayor neutralidad.
            
            Informe generado automáticamente por El Faro Intelligence Suite v14.0.
            """
            st.session_state.informe_txt = txt
            st.text_area("Borrador del Informe:", txt, height=350)
            
            # PDF CON GRÁFICO
            pdf = FPDF()
            pdf.add_page(); pdf.set_font("Arial", 'B', 16); pdf.cell(0, 10, "INFORME ESTRATEGICO EL FARO", 0, 1, 'C')
            pdf.ln(5); pdf.set_font("Arial", size=11); pdf.multi_cell(0, 7, txt.encode('latin-1','replace').decode('latin-1'))
            
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            pdf.output(tmp.name)
            with open(tmp.name, "rb") as f:
                st.download_button("📥 DESCARGAR INFORME OFICIAL (PDF)", f, "Informe_Faro_Master.pdf")
else:
    st.info("👋 Radar en espera. Configura el objetivo y presiona 'ENCENDER EL FARO'.")
