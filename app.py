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

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sentinel AI: Command Center", 
    layout="wide", 
    page_icon="📡",
    initial_sidebar_state="collapsed"
)

# --- ESTILOS CSS "PREMIUM DARK" ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    h1, h2, h3 { font-family: 'Roboto', sans-serif; color: #e0e0e0; font-weight: 300; }
    h1 { font-weight: 700; background: -webkit-linear-gradient(#00ffbf, #00b8ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    div[data-testid="stMetric"] {
        background-color: rgba(38, 39, 48, 0.7);
        border: 1px solid #4e4e4e;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .stButton>button {
        background: linear-gradient(45deg, #ff4b4b, #ff0055);
        color: white;
        border-radius: 8px;
        border: none;
        padding: 12px 24px;
        font-weight: bold;
        width: 100%;
    }
    </style>
    """, unsafe_allow_html=True)

# --- MEMORIA DE SESIÓN ---
if 'df_noticias' not in st.session_state:
    st.session_state.df_noticias = pd.DataFrame(columns=['Fecha', 'Fuente', 'Titular', 'Sentimiento', 'Link', 'Score', 'Alcance', 'Lat', 'Lon', 'Lugar', 'Manual'])

# --- BASE DE DATOS GEOGRÁFICA (Coquimbo/La Serena) ---
GEO_DB = {
    "avenida del mar": [-29.9168, -71.2785],
    "faro": [-29.9073, -71.2847],
    "centro": [-29.9027, -71.2519],
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

# --- FUNCIONES ---
@st.cache_resource
def cargar_modelo():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def clasificar_alcance(fuente):
    fuente = fuente.lower()
    regionales = ['el día', 'el observatodo', 'mi radio', 'laserenaonline', 'diario la región', 'norte visión', 'guayacán']
    nacionales = ['biobio', 'emol', 'la tercera', 'cooperativa', '24 horas', 'meganoticias', 'cnn']
    if any(x in fuente for x in regionales): return "Regional"
    if any(x in fuente for x in nacionales): return "Nacional"
    return "Internacional/Web"

def detectar_ubicacion(texto):
    texto = texto.lower()
    for lugar, coords in GEO_DB.items():
        if lugar in texto:
            return coords[0], coords[1], lugar.title()
    # Ubicación por defecto (La Serena) con pequeña variación para no encimar puntos
    base_lat, base_lon = -29.9027, -71.2519
    return base_lat + random.uniform(-0.02, 0.02), base_lon + random.uniform(-0.02, 0.02), "General"

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
            pred = analizador(item.title[:512])[0]
            score = int(pred['label'].split()[0])
            sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
            fuente = item.source.title if 'source' in item else "Web"
            
            lat, lon, lugar = detectar_ubicacion(item.title + " " + (item.description if 'description' in item else ""))
            
            nuevas.append({
                'Fecha': fecha, 'Fuente': fuente, 'Titular': item.title,
                'Sentimiento': sent, 'Link': item.link, 'Score': score,
                'Alcance': clasificar_alcance(fuente), 'Lat': lat, 'Lon': lon, 'Lugar': lugar,
                'Manual': False
            })
        except: pass
        
    if nuevas:
        st.session_state.df_noticias = pd.concat([st.session_state.df_noticias, pd.DataFrame(nuevas)], ignore_index=True)
        return len(nuevas)
    return 0

# --- MAPA ---
def generar_mapa(df):
    m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
    HeatMap([[row['Lat'], row['Lon']] for i, row in df.iterrows()], radius=15).add_to(m)
    mc = MarkerCluster().add_to(m)
    for i, row in df.iterrows():
        color = "green" if row['Sentimiento']=='Positivo' else "red" if row['Sentimiento']=='Negativo' else "orange"
        folium.Marker([row['Lat'], row['Lon']], popup=row['Titular'], icon=folium.Icon(color=color)).add_to(mc)
    return m

# --- PDF ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'SENTINEL AI - REPORTE DE INTELIGENCIA', 0, 1, 'C')
        self.ln(5)
def generar_pdf(df, tema):
    pdf = PDF(); pdf.add_page(); pdf.set_font("Arial", size=10)
    pdf.cell(0, 10, f"Reporte: {tema} | Fecha: {datetime.now().date()}", 0, 1)
    for i, row in df.iterrows():
        try:
            txt = f"[{row['Sentimiento']}] {row['Fuente']}: {row['Titular']}"
            txt = txt.encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(0, 6, txt); pdf.ln(1)
        except: pass
    t = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(t.name)
    return t.name

# --- INTERFAZ ---
st.title("📡 SENTINEL AI: COMMAND CENTER")

with st.sidebar:
    st.header("🎛️ Configuración")
    tema = st.text_input("Objetivo", "La Serena")
    tipo = st.selectbox("Modo", ["Todo Internet", "Solo Prensa", "Redes Sociales"])
    sitios = st.text_area("Sitios Extra", "elobservatodo.cl, miradiols.cl")
    c1, c2 = st.columns(2)
    ini = c1.date_input("Inicio", datetime.now()-timedelta(days=7))
    fin = c2.date_input("Fin", datetime.now())
    
    with st.expander("📍 Ingreso Manual"):
        with st.form("manual"):
            m_tit = st.text_input("Suceso")
            m_lug = st.selectbox("Lugar", list(GEO_DB.keys()))
            m_sen = st.selectbox("Sentimiento", ["Positivo", "Negativo"])
            if st.form_submit_button("Guardar"):
                c = GEO_DB[m_lug]
                new = {'Fecha':datetime.now().date(), 'Fuente':"Manual", 'Titular':m_tit, 'Sentimiento':m_sen, 
                       'Link':'#', 'Score':0, 'Alcance':"Regional", 'Lat':c[0], 'Lon':c[1], 'Lugar':m_lug.title(), 'Manual':True}
                st.session_state.df_noticias = pd.concat([st.session_state.df_noticias, pd.DataFrame([new])], ignore_index=True)
                st.success("Guardado")

if st.button(f"🔴 ESCANEAR RED: {tema.upper()}"):
    with st.spinner("Rastreando..."):
        escanear_web(tema, tipo, ini, fin, sitios)

if not st.session_state.df_noticias.empty:
    # 1. DATA EDITOR
    with st.expander("🛠️ GESTIÓN DE DATOS", expanded=True):
        df_ed = st.data_editor(st.session_state.df_noticias, use_container_width=True, num_rows="dynamic")
    
    # 2. DASHBOARD
    st.divider()
    pos = len(df_ed[df_ed.Sentimiento=='Positivo'])
    neg = len(df_ed[df_ed.Sentimiento=='Negativo'])
    tot = len(df_ed)
    score = ((pos * 100) + (tot - neg - pos) * 50) / tot if tot > 0 else 0
    
    c1, c2 = st.columns([1, 2])
    with c1:
        fig = go.Figure(go.Indicator(
            mode = "gauge+number", value = score, title={'text':"REPUTACIÓN"},
            gauge={'axis':{'range':[None,100]}, 'bar':{'color':"rgba(0,0,0,0)"}, 
                   'steps':[{'range':[0,40],'color':'#ff4b4b'},{'range':[40,70],'color':'#f1c40f'},{'range':[70,100],'color':'#00ffbf'}]}
        ))
        fig.update_layout(height=250, margin=dict(t=30,b=20,l=20,r=20), paper_bgcolor="rgba(0,0,0,0)", font={'color':'white'})
        st.plotly_chart(fig, use_container_width=True)
        
    with c2:
        k1, k2, k3 = st.columns(3)
        k1.metric("Total", tot)
        k2.metric("Positivos", pos, delta="🟢")
        k3.metric("Negativos", neg, delta="-🔴", delta_color="inverse")
        
        # SUNBURST
        fig_sun = px.sunburst(df_ed, path=['Alcance', 'Sentimiento', 'Fuente'], color='Sentimiento',
                              color_discrete_map={'Positivo':'#00ffbf', 'Negativo':'#ff4b4b', 'Neutro':'#f1c40f'})
        fig_sun.update_layout(height=250, margin=dict(t=0,b=0,l=0,r=0), paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_sun, use_container_width=True)

    # 3. MAPA Y NUBE
    st.divider()
    c3, c4 = st.columns(2)
    with c3:
        st.markdown("### 🗺️ Mapa Táctico")
        st_folium(generar_mapa(df_ed), height=400, width="100%")
    with c4:
        st.markdown("### ☁️ Conceptos")
        wc = WordCloud(width=600, height=400, background_color='#0e1117', colormap='Wistia').generate(" ".join(df_ed['Titular']))
        fig, ax = plt.subplots(); ax.imshow(wc); ax.axis("off"); fig.patch.set_facecolor('#0e1117')
        st.pyplot(fig)
        
        if st.button("📄 Descargar PDF"):
            f = generar_pdf(df_ed, tema)
            with open(f, "rb") as file:
                st.download_button("Descargar Informe", file, "Sentinel.pdf")

else:
    st.info("Sistema listo. Inicie escaneo.")
