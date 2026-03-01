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

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Sentinel AI Command Center", layout="wide", page_icon="📡")

# --- ESTILOS CSS "MODO MONITOR" ---
st.markdown("""
    <style>
    /* Fondo y fuentes estilo tecnológico */
    .main {
        background-color: #0e1117;
    }
    h1, h2, h3 {
        font-family: 'Roboto', sans-serif;
        color: #e0e0e0;
    }
    /* Tarjetas de métricas estilo HUD */
    div[data-testid="stMetric"] {
        background-color: #262730;
        border: 1px solid #4e4e4e;
        padding: 15px;
        border-radius: 5px;
        color: #ffffff;
        box-shadow: 0 0 10px rgba(0,255,0,0.1);
    }
    div[data-testid="stMetricValue"] {
        font-size: 24px;
        color: #00ffbf;
    }
    /* Botones */
    .stButton>button {
        background-color: #ff4b4b;
        color: white;
        border-radius: 20px;
        border: none;
        padding: 10px 24px;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# --- CABECERA ---
col_logo, col_titulo = st.columns([1, 5])
with col_logo:
    st.markdown("# 📡")
with col_titulo:
    st.title("SENTINEL AI: MONITOR DE CRISIS")
    st.caption("Sistema de Vigilancia Digital y Reputación en Tiempo Real")

# --- BARRA LATERAL ---
st.sidebar.markdown("### 🎛️ CONFIGURACIÓN DE RASTREO")
st.sidebar.markdown("---")
tema_busqueda = st.sidebar.text_input("OBJETIVO (Tema/Persona)", "La Serena")
tipo_fuente = st.sidebar.selectbox("CANAL DE ESCUCHA", ["Todo Internet", "Solo Prensa", "Redes Sociales (Twitter/TikTok/IG)"])

st.sidebar.markdown("### 📅 RANGO TEMPORAL")
col1, col2 = st.sidebar.columns(2)
fecha_inicio = col1.date_input("Inicio", datetime.now() - timedelta(days=30))
fecha_fin = col2.date_input("Fin", datetime.now())

btn_actualizar = st.sidebar.button("🔴 INICIAR ESCANEO")

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
    # Calculamos un índice de 0 a 100
    if total == 0: return 0
    score = ((pos * 100) + (total - neg - pos) * 50) / total
    
    fig = go.Figure(go.Indicator(
        mode = "gauge+number+delta",
        value = score,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "NIVEL DE REPUTACIÓN", 'font': {'size': 24}},
        delta = {'reference': 50, 'increasing': {'color': "green"}},
        gauge = {
            'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': "white"},
            'bar': {'color': "rgba(0,0,0,0)"}, # Ocultamos la barra normal
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 40], 'color': '#ff4b4b'}, # Rojo
                {'range': [40, 70], 'color': '#f1c40f'}, # Amarillo
                {'range': [70, 100], 'color': '#00ffbf'}], # Verde Neon
            'threshold': {
                'line': {'color': "white", 'width': 4},
                'thickness': 0.75,
                'value': score}}))
    
    fig.update_layout(paper_bgcolor = "rgba(0,0,0,0)", font = {'color': "white", 'family': "Arial"})
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
            
            # Limpieza de Fuente para el gráfico solar
            fuente = item.source.title if 'source' in item else "Web"
            fuente = fuente.split("-")[0].strip() # Limpiar nombres largos
            
            datos.append({
                "Fecha": fecha_obj,
                "Fuente": fuente,
                "Titular": item.title,
                "Sentimiento": sent,
                "Link": item.link,
                "Score": score,
                "Extracto": item.title[:30] + "..." # Para el gráfico solar
            })
        except: pass
        progreso.progress((i + 1) / total)
    progreso.empty()
    return pd.DataFrame(datos)

# --- PDF GENERATOR (Mantenemos tu funcionalidad) ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Sentinel AI - Reporte de Crisis', 0, 1, 'C')
        self.ln(5)
def generar_pdf(df, tema):
    pdf = PDF(); pdf.add_page(); pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Reporte para: {tema} - {datetime.now().date()}", 0, 1)
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

# --- INTERFAZ PRINCIPAL ---
if btn_actualizar:
    with st.spinner(f"📡 Conectando satélites a {tema_busqueda}..."):
        df = analizar_datos(tema_busqueda, tipo_fuente, fecha_inicio, fecha_fin)
        
    if not df.empty:
        pos = len(df[df.Sentimiento=='Positivo'])
        neg = len(df[df.Sentimiento=='Negativo'])
        total = len(df)
        
        # --- FILA 1: VELOCÍMETRO Y KPIs ---
        col_gauge, col_kpis = st.columns([1, 2])
        
        with col_gauge:
            st.plotly_chart(crear_velocimetro(pos, neg, total), use_container_width=True)
            
        with col_kpis:
            st.markdown("#### 📊 MÉTRICAS DE IMPACTO")
            k1, k2, k3 = st.columns(3)
            k1.metric("Volumen Total", total, "Menciones")
            k2.metric("Positivos", pos, delta="Buen Impacto")
            k3.metric("Riesgos/Negativos", neg, delta="-Alerta", delta_color="inverse")
            
            st.info(f"Fuente más activa detectada: **{df['Fuente'].mode()[0]}**")
            
            # Botón PDF
            pdf_file = generar_pdf(df, tema_busqueda)
            with open(pdf_file, "rb") as f:
                st.download_button("📥 Descargar Informe Oficial", f, "reporte.pdf")

        st.divider()

        # --- FILA 2: MAPA CONCEPTUAL INTERACTIVO (SUNBURST) ---
        st.markdown("### 🕸️ MAPA DE CALOR INTERACTIVO (Haz clic para profundizar)")
        st.caption("Navegación: Centro (Sentimiento) -> Anillo Medio (Fuente) -> Anillo Externo (Noticia)")
        
        # Preparamos datos jerárquicos
        fig_sun = px.sunburst(
            df, 
            path=['Sentimiento', 'Fuente', 'Extracto'], 
            values='Score',
            color='Sentimiento',
            color_discrete_map={'Positivo':'#00ffbf', 'Negativo':'#ff4b4b', 'Neutro':'#f1c40f'},
            height=600
        )
        fig_sun.update_layout(margin=dict(t=0, l=0, r=0, b=0), paper_bgcolor="#0e1117")
        st.plotly_chart(fig_sun, use_container_width=True)

        # --- FILA 3: ANÁLISIS SEMÁNTICO (NUBE) ---
        c1, c2 = st.columns([2, 1])
        with c1:
            st.subheader("☁️ Nube de Conceptos Clave")
            text = " ".join(df.Titular)
            wc = WordCloud(width=800, height=400, background_color='#0e1117', colormap='Wistia').generate(text)
            fig, ax = plt.subplots(figsize=(10, 5))
            fig.patch.set_facecolor('#0e1117') # Fondo oscuro
            ax.imshow(wc, interpolation='bilinear')
            ax.axis("off")
            st.pyplot(fig)
            
        with c2:
            st.subheader("🏆 Top Medios/Redes")
            ranking = df['Fuente'].value_counts()
            st.bar_chart(ranking)

        # --- TABLA FINAL ---
        with st.expander("📂 VER REGISTRO BRUTO DE DATOS"):
            st.dataframe(df, use_container_width=True)

    else:
        st.error("No se detectó actividad en el radar bajo estos parámetros.")
