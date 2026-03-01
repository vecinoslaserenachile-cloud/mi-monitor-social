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
import re
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap, MarkerCluster

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sentinel AI: Geo-Tactical", 
    layout="wide", 
    page_icon="📡",
    initial_sidebar_state="collapsed"
)

# --- ESTILOS CSS PRO ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    h1, h2, h3 { font-family: 'Roboto', sans-serif; color: #e0e0e0; }
    /* Ajuste Mapas */
    iframe { border-radius: 10px; border: 1px solid #333; }
    </style>
    """, unsafe_allow_html=True)

# --- MEMORIA DE SESIÓN ---
if 'df_noticias' not in st.session_state:
    st.session_state.df_noticias = pd.DataFrame(columns=['Fecha', 'Fuente', 'Titular', 'Sentimiento', 'Link', 'Score', 'Lat', 'Lon', 'Lugar'])

# --- MOTOR DE INTELIGENCIA GEOESPACIAL ---
# Diccionario de coordenadas estratégicas (Puedes agregar más)
GEO_DB = {
    "avenida del mar": [-29.9168, -71.2785],
    "faro": [-29.9073, -71.2847],
    "centro de la serena": [-29.9027, -71.2519],
    "plaza de armas": [-29.9027, -71.2519],
    "las compañías": [-29.8783, -71.2389],
    "tierras blancas": [-29.9392, -71.2294],
    "coquimbo": [-29.9533, -71.3436],
    "puerto": [-29.9497, -71.3364],
    "ovalle": [-30.6015, -71.2003],
    "vicuña": [-30.0319, -70.7081],
    "paihuano": [-30.0167, -70.5167],
    "aeropuerto": [-29.9161, -71.1994],
    "la florida": [-29.9238, -71.2185],
    "antena": [-29.9079, -71.2369]
}

def detectar_ubicacion(texto):
    texto = texto.lower()
    for lugar, coords in GEO_DB.items():
        if lugar in texto:
            return coords[0], coords[1], lugar.title()
    # Si no encuentra nada específico, por defecto marca "La Serena Centro" con un pequeño random para que no se amontonen
    import random
    base_lat, base_lon = -29.9027, -71.2519
    return base_lat + random.uniform(-0.01, 0.01), base_lon + random.uniform(-0.01, 0.01), "General"

@st.cache_resource
def cargar_modelo():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def construir_url(tema, tipo, sitios_extra):
    base_query = tema
    if tipo == "Redes Sociales":
        base_query += " site:twitter.com OR site:facebook.com OR site:instagram.com OR site:tiktok.com"
    elif tipo == "Solo Prensa":
        base_query += " when:7d"
    if sitios_extra:
        for s in sitios_extra.split(","):
            if s.strip(): base_query += f" OR site:{s.strip()}"
    return f"https://news.google.com/rss/search?q={quote(base_query)}&hl=es-419&gl=CL&ceid=CL:es-419"

def escanear_web(tema, tipo, inicio, fin, sitios_extra):
    analizador = cargar_modelo()
    url = construir_url(tema, tipo, sitios_extra)
    feed = feedparser.parse(url)
    nuevas = []
    
    for item in feed.entries:
        try:
            fecha = datetime.fromtimestamp(time.mktime(item.published_parsed)).date()
        except: fecha = datetime.now().date()
            
        if not (inicio <= fecha <= fin): continue
        if not st.session_state.df_noticias.empty:
            if item.link in st.session_state.df_noticias['Link'].values: continue

        try:
            # Análisis IA
            pred = analizador(item.title[:512])[0]
            score = int(pred['label'].split()[0])
            sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
            
            # Análisis Geoespacial
            lat, lon, lugar = detectar_ubicacion(item.title + " " + item.description if 'description' in item else item.title)
            
            nuevas.append({
                'Fecha': fecha,
                'Fuente': item.source.title if 'source' in item else "Web",
                'Titular': item.title,
                'Sentimiento': sent,
                'Link': item.link,
                'Score': score,
                'Lat': lat, 'Lon': lon, 'Lugar': lugar,
                'Manual': False
            })
        except: pass
        
    if nuevas:
        st.session_state.df_noticias = pd.concat([st.session_state.df_noticias, pd.DataFrame(nuevas)], ignore_index=True)
        return len(nuevas)
    return 0

# --- MAPA INTERACTIVO ---
def generar_mapa_táctico(df):
    # Centro en La Serena
    m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
    
    # Capa de Calor
    heat_data = [[row['Lat'], row['Lon']] for index, row in df.iterrows()]
    HeatMap(heat_data, radius=15).add_to(m)
    
    # Marcadores
    marker_cluster = MarkerCluster().add_to(m)
    
    for index, row in df.iterrows():
        color = "green" if row['Sentimiento'] == 'Positivo' else "red" if row['Sentimiento'] == 'Negativo' else "orange"
        
        html = f"""
        <div style='font-family:Arial; width:200px'>
            <b>{row['Fuente']}</b><br>
            <span style='color:{color}'><b>{row['Sentimiento']}</b></span><br>
            <small>{row['Titular'][:50]}...</small>
        </div>
        """
        
        folium.Marker(
            [row['Lat'], row['Lon']],
            popup=folium.Popup(html, max_width=250),
            icon=folium.Icon(color=color, icon="info-sign")
        ).add_to(marker_cluster)
        
    return m

# --- PDF GENERATOR ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'SENTINEL AI - REPORTE GEO-TACTICO', 0, 1, 'C')
        self.ln(5)
def generar_pdf(df, tema):
    pdf = PDF(); pdf.add_page(); pdf.set_font("Arial", size=10)
    pdf.cell(0, 10, f"Generado: {datetime.now().date()} | Objetivo: {tema}", 0, 1)
    for i, row in df.iterrows():
        try:
            txt = f"[{row['Sentimiento']}] ({row['Lugar']}) {row['Titular']}"
            txt = txt.encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(0, 6, txt); pdf.ln(1)
        except: pass
    t = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(t.name)
    return t.name

# --- INTERFAZ ---
st.title("📡 SENTINEL AI: MAPA DE CALOR")
st.caption("Monitoreo Geoespacial de Crisis")

# BARRA LATERAL
with st.sidebar:
    st.header("🗺️ Configuración")
    tema = st.text_input("Objetivo", "La Serena")
    tipo = st.selectbox("Fuente", ["Todo Internet", "Solo Prensa", "Redes Sociales"])
    sitios = st.text_area("Sitios Extra", "elobservatodo.cl, miradiols.cl")
    col1, col2 = st.columns(2)
    f_ini = col1.date_input("Inicio", datetime.now()-timedelta(days=7))
    f_fin = col2.date_input("Fin", datetime.now())
    
    # INGRESO MANUAL GEOLOCALIZADO
    with st.expander("📍 Ingreso Manual + GPS"):
        with st.form("geo_manual"):
            m_tit = st.text_input("Suceso")
            m_lugar = st.selectbox("Ubicación", list(GEO_DB.keys()))
            m_sen = st.selectbox("Sentimiento", ["Positivo", "Negativo"])
            if st.form_submit_button("Guardar en Mapa"):
                coords = GEO_DB[m_lugar]
                new = {'Fecha':datetime.now().date(), 'Fuente':"Manual", 'Titular':m_tit, 'Sentimiento':m_sen, 'Link':'#', 'Score':0, 'Lat':coords[0], 'Lon':coords[1], 'Lugar':m_lugar.title(), 'Manual':True}
                st.session_state.df_noticias = pd.concat([st.session_state.df_noticias, pd.DataFrame([new])], ignore_index=True)
                st.success("Evento Geolocalizado")

if st.button(f"🔴 ESCANEAR ZONA: {tema.upper()}"):
    with st.spinner("Triangulando información..."):
        escanear_web(tema, tipo, f_ini, f_fin, sitios)

# VISUALIZACIÓN
if not st.session_state.df_noticias.empty:
    
    # 1. EL MAPA (LA JOYA DE LA CORONA)
    st.markdown("### 🗺️ Mapa de Calor y Conflictos")
    mapa = generar_mapa_táctico(st.session_state.df_noticias)
    st_folium(mapa, width="100%", height=500)
    
    st.divider()
    
    # 2. MÉTRICAS Y EDICIÓN
    c1, c2 = st.columns([1,1])
    with c1:
        st.markdown("#### 📊 Distribución por Lugar")
        lugar_counts = st.session_state.df_noticias['Lugar'].value_counts()
        st.bar_chart(lugar_counts)
    
    with c2:
        st.markdown("#### 📥 Exportar Inteligencia")
        if st.button("Generar Reporte Geo-PDF"):
            f = generar_pdf(st.session_state.df_noticias, tema)
            with open(f, "rb") as file:
                st.download_button("Descargar PDF", file, "Sentinel_Geo.pdf")
    
    with st.expander("📂 Ver Datos Brutos"):
        st.dataframe(st.session_state.df_noticias)
