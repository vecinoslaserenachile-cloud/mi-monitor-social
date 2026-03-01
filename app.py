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

# --- CONFIGURACIÓN DE LA PÁGINA (MOBILE FRIENDLY) ---
st.set_page_config(
    page_title="Sentinel AI Command Center", 
    layout="wide", 
    page_icon="📡",
    initial_sidebar_state="expanded" # <--- ESTO FORZA QUE EL MENÚ SE ABRA AL INICIO
)

# --- ESTILOS CSS PARA MÓVIL Y MONITOR ---
st.markdown("""
    <style>
    /* Fondo oscuro profesional */
    .main { background-color: #0e1117; }
    h1, h2, h3 { font-family: 'Roboto', sans-serif; color: #e0e0e0; }
    
    /* Ajuste para móviles: Que nada se salga del ancho */
    .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 100%;
    }
    
    /* Tarjetas de métricas estilo HUD */
    div[data-testid="stMetric"] {
        background-color: #262730;
        border: 1px solid #4e4e4e;
        padding: 10px;
        border-radius: 5px;
        color: #ffffff;
        text-align: center; /* Centrado para móvil */
    }
    
    /* Botón Gigante de Acción */
    .stButton>button {
        background-color: #ff4b4b;
        color: white;
        border-radius: 10px;
        border: none;
        padding: 15px 30px;
        font-size: 20px;
        width: 100%; /* Ocupa todo el ancho en celular */
        font-weight: bold;
        box-shadow: 0 4px 15px rgba(255, 75, 75, 0.4);
    }
    </style>
    """, unsafe_allow_html=True)

# --- CABECERA ---
st.markdown("# 📡 SENTINEL AI")
st.caption("Sistema de Vigilancia Digital y Reputación")

# --- BARRA LATERAL (CONFIGURACIÓN) ---
with st.sidebar:
    st.markdown("### ⚙️ CONFIGURACIÓN")
    st.info("Configura aquí tu búsqueda 👇")
    tema_busqueda = st.text_input("OBJETIVO", "La Serena")
    tipo_fuente = st.selectbox("CANAL", ["Todo Internet", "Solo Prensa", "Redes Sociales (Twitter/TikTok/IG)"])
    
    st.markdown("---")
    st.markdown("### 📅 FECHAS")
    col1, col2 = st.columns(2)
    fecha_inicio = col1.date_input("Inicio", datetime.now() - timedelta(days=30))
    fecha_fin = col2.date_input("Fin", datetime.now())
    
    st.markdown("---")
    st.caption("Sentinel AI v3.0 Mobile")

# --- BOTÓN DE ACCIÓN (AHORA EN EL CENTRO) ---
# Esto soluciona el problema del móvil: el botón siempre está visible
st.markdown("---")
col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
with col_btn2:
    btn_actualizar = st.button(f"🔴 ESCANEAR: {tema_busqueda.upper()}")
st.markdown("---")

# --- FUNCIONES ---
@st.cache_resource
def cargar_modelo():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def construir_url(tema, tipo):
    if tipo == "Redes Sociales (Twitter/TikTok/IG)":
        query_raw = f"{tema} site:twitter.com OR site:facebook.com OR site:instagram.com OR site:tiktok.com OR site:reddit.com"
    elif tipo == "Solo Prensa":
        query_raw = f"{tema} when:14d"
    else:
        query_raw = tema
    return f"https://news.google.com/rss/search?q={quote(query_raw)}&hl=es-419&gl=CL&ceid=CL:es-419"

def crear_velocimetro(pos, neg, total):
    if total == 0: return 0
    score = ((pos * 100) + (total - neg - pos) * 50) / total
    
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = score,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "REPUTACIÓN", 'font': {'size': 20}},
        gauge = {
            'axis': {'range': [None, 100]},
            'bar': {'color': "rgba(0,0,0,0)"},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 40], 'color': '#ff4b4b'},
                {'range': [40, 70], 'color': '#f1c40f'},
                {'range': [70, 100], 'color': '#00ffbf'}],
            'threshold': {
                'line': {'color': "black", 'width': 4},
                'thickness': 0.75,
                'value': score}}))
    
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=50, b=20), paper_bgcolor="rgba(0,0,0,0)", font={'color': "white"})
    return fig

def analizar_datos(tema, tipo, f_inicio, f_fin):
    analizador = cargar_modelo()
    url = construir_url(tema, tipo)
    noticias = feedparser.parse(url)
    datos = []
    
    if not noticias.entries: return pd.DataFrame()
    progreso = st.progress(0)
    total = len(noticias.entries)
    
    for i, item in enumerate(noticias.entries):
        try:
            fecha_obj = datetime.fromtimestamp(time.mktime(item.published_parsed)).date()
        except: fecha_obj = datetime.now().date()
            
        if not (f_inicio <= fecha_obj <= f_fin): continue
            
        try:
            pred = analizador(item.title[:512])[0]
            score = int(pred['label'].split()[0])
            sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
            
            fuente = item.source.title if 'source' in item else "Web"
            fuente = fuente.split("-")[0].strip()
            
            datos.append({
                "Fecha": fecha_obj,
                "Fuente": fuente,
                "Titular": item.title,
                "Sentimiento": sent,
                "Link": item.link,
                "Score": score,
                "Extracto": item.title[:30] + "..."
            })
        except: pass
        progreso.progress((i + 1) / total)
    progreso.empty()
    return pd.DataFrame(datos)

class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Sentinel AI - Reporte', 0, 1, 'C')
        self.ln(5)
def generar_pdf(df, tema):
    pdf = PDF(); pdf.add_page(); pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Reporte: {tema} - {datetime.now().date()}", 0, 1)
    pdf.ln(10)
    for i, row in df.iterrows():
        try:
            txt = f"[{row['Sentimiento']}] {row['Fuente']}: {row['Titular']}"
            txt = txt.encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(0, 8, txt); pdf.ln(2)
        except: pass
    t = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(t.name)
    return t.name

# --- LÓGICA PRINCIPAL ---
if btn_actualizar:
    with st.spinner(f"📡 Rastreando red..."):
        df = analizar_datos(tema_busqueda, tipo_fuente, fecha_inicio, fecha_fin)
        
    if not df.empty:
        pos = len(df[df.Sentimiento=='Positivo'])
        neg = len(df[df.Sentimiento=='Negativo'])
        total = len(df)
        
        # --- SECCIÓN 1: SALUD DE MARCA ---
        st.markdown("### 🚦 ESTADO ACTUAL")
        col_gauge, col_resumen = st.columns([1, 1])
        
        with col_gauge:
            # Gráfico de Velocímetro
            st.plotly_chart(crear_velocimetro(pos, neg, total), use_container_width=True)
            
        with col_resumen:
            # Métricas en Bloque (Mejor para móvil)
            st.metric("Total Menciones", total)
            c1, c2 = st.columns(2)
            c1.metric("Positivos", pos, delta="🟢")
            c2.metric("Negativos", neg, delta="-🔴", delta_color="inverse")
            
            # Botón PDF pequeño
            pdf_file = generar_pdf(df, tema_busqueda)
            with open(pdf_file, "rb") as f:
                st.download_button("📥 PDF", f, "reporte.pdf", use_container_width=True)

        st.divider()

        # --- SECCIÓN 2: MAPA SOLAR (SUNBURST) ---
        st.markdown("### 🕸️ PROFUNDIDAD (Toca el gráfico)")
        fig_sun = px.sunburst(
            df, 
            path=['Sentimiento', 'Fuente', 'Extracto'], 
            values='Score',
            color='Sentimiento',
            color_discrete_map={'Positivo':'#00ffbf', 'Negativo':'#ff4b4b', 'Neutro':'#f1c40f'},
            height=500
        )
        fig_sun.update_layout(margin=dict(t=0, l=0, r=0, b=0), paper_bgcolor="#0e1117")
        st.plotly_chart(fig_sun, use_container_width=True)

        # --- SECCIÓN 3: NUBE DE PALABRAS ---
        st.markdown("### ☁️ CONCEPTOS CLAVE")
        text = " ".join(df.Titular)
        wc = WordCloud(width=800, height=400, background_color='#0e1117', colormap='Wistia').generate(text)
        fig, ax = plt.subplots(figsize=(6, 3)) # Tamaño ajustado para móvil
        fig.patch.set_facecolor('#0e1117')
        ax.imshow(wc, interpolation='bilinear')
        ax.axis("off")
        st.pyplot(fig)
        
        # --- TABLA DESPLEGABLE ---
        with st.expander("📂 VER LISTA COMPLETA"):
            st.dataframe(df[['Fecha','Fuente','Titular']], use_container_width=True)

    else:
        st.warning("Sin datos. Intenta ampliar el rango de fechas.")
