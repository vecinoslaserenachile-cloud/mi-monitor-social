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

# --- CONFIGURACIÓN DE PÁGINA (MOBILE FRIENDLY) ---
st.set_page_config(
    page_title="Sentinel AI Command Center", 
    layout="wide", 
    page_icon="📡",
    initial_sidebar_state="collapsed"
)

# --- ESTILOS CSS ---
st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    h1, h2, h3 { font-family: 'Roboto', sans-serif; color: #e0e0e0; }
    /* Ajustes para móvil */
    .stButton>button {
        background-color: #ff4b4b; color: white; border-radius: 10px;
        border: none; padding: 15px 20px; font-weight: bold; width: 100%;
        font-size: 18px;
    }
    div[data-testid="stMetric"] {
        background-color: #262730; border: 1px solid #4e4e4e;
        padding: 10px; border-radius: 5px; text-align: center;
    }
    </style>
    """, unsafe_allow_html=True)

# --- MEMORIA DE SESIÓN (Para que no se borren tus datos manuales) ---
if 'df_noticias' not in st.session_state:
    st.session_state.df_noticias = pd.DataFrame(columns=['Fecha', 'Fuente', 'Titular', 'Sentimiento', 'Link', 'Score', 'Manual'])

# --- FUNCIONES ---
@st.cache_resource
def cargar_modelo():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def construir_url(tema, tipo, sitios_extra):
    base_query = tema
    # Filtros de búsqueda avanzados
    if tipo == "Redes Sociales":
        base_query += " site:twitter.com OR site:facebook.com OR site:instagram.com OR site:tiktok.com OR site:reddit.com"
    elif tipo == "Solo Prensa":
        base_query += " when:7d"
        
    # Agregar sitios manuales (A quién seguir)
    if sitios_extra:
        sitios_lista = sitios_extra.split(",")
        for sitio in sitios_lista:
            sitio = sitio.strip()
            if sitio:
                base_query += f" OR site:{sitio}"
            
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
        
        # Evitar duplicados revisando el Link
        if not st.session_state.df_noticias.empty:
            if item.link in st.session_state.df_noticias['Link'].values:
                continue

        try:
            # Análisis IA
            pred = analizador(item.title[:512])[0]
            score = int(pred['label'].split()[0])
            sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
            
            nuevas.append({
                'Fecha': fecha,
                'Fuente': item.source.title if 'source' in item else "Web",
                'Titular': item.title,
                'Sentimiento': sent,
                'Link': item.link,
                'Score': score,
                'Manual': False
            })
        except: pass
        
    if nuevas:
        df_new = pd.DataFrame(nuevas)
        st.session_state.df_noticias = pd.concat([st.session_state.df_noticias, df_new], ignore_index=True)
        return len(df_new)
    return 0

# --- CLASE PDF ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, 'Sentinel AI - Informe de Inteligencia', 0, 1, 'C')
        self.ln(5)

def generar_pdf(df, tema):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 10, f"Generado el: {datetime.now().strftime('%d-%m-%Y')}", 0, 1)
    
    # Resumen
    pos = len(df[df.Sentimiento=='Positivo'])
    neg = len(df[df.Sentimiento=='Negativo'])
    neu = len(df[df.Sentimiento=='Neutro'])
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"Resumen Ejecutivo: {len(df)} menciones", 0, 1)
    pdf.set_font("Arial", size=10)
    pdf.cell(0, 10, f"Positivas: {pos} | Negativas: {neg} | Neutras: {neu}", 0, 1)
    pdf.ln(5)
    
    # Detalle
    for i, row in df.iterrows():
        try:
            titulo = row['Titular'].encode('latin-1', 'replace').decode('latin-1')
            fuente = row['Fuente'].encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(0, 6, f"[{row['Sentimiento']}] {fuente}: {titulo}")
            pdf.ln(2)
        except: pass
        
    t = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(t.name)
    return t.name

# --- INTERFAZ ---
st.title("📡 SENTINEL AI: GESTIÓN DE CRISIS")

# BARRA LATERAL
with st.sidebar:
    st.header("🎮 Mando Manual")
    with st.expander("📝 Agregar Noticia Manual (WhatsApp/Radio)"):
        with st.form("manual"):
            m_tit = st.text_input("Texto/Titular")
            m_fuent = st.text_input("Fuente", "Informante")
            m_sent = st.selectbox("Sentimiento", ["Positivo", "Negativo", "Neutro"])
            m_date = st.date_input("Fecha", datetime.now())
            if st.form_submit_button("➕ Agregar"):
                new_data = {'Fecha': m_date, 'Fuente': m_fuent, 'Titular': m_tit, 'Sentimiento': m_sent, 'Link': '#', 'Score':0, 'Manual': True}
                st.session_state.df_noticias = pd.concat([st.session_state.df_noticias, pd.DataFrame([new_data])], ignore_index=True)
                st.success("Agregado")

    st.header("⚙️ Configuración Escáner")
    tema = st.text_input("Objetivo", "La Serena")
    tipo = st.selectbox("Modo", ["Todo Internet", "Solo Prensa", "Redes Sociales"])
    sitios_extra = st.text_area("🌐 Sitios Extra (separar con comas)", placeholder="ej: eldia.cl, miradiols.cl")
    c1, c2 = st.columns(2)
    f_ini = c1.date_input("Desde", datetime.now()-timedelta(days=7))
    f_fin = c2.date_input("Hasta", datetime.now())

# BOTÓN CENTRAL GRANDE
if st.button(f"🔴 ESCANEAR RED: {tema.upper()}"):
    with st.spinner("Rastreando satélites..."):
        n = escanear_web(tema, tipo, f_ini, f_fin, sitios_extra)
        if n > 0: st.success(f"¡{n} hallazgos nuevos!")
        else: st.warning("Sin novedades en este rango.")

# ÁREA DE TRABAJO
if not st.session_state.df_noticias.empty:
    st.divider()
    st.markdown("### 1️⃣ GESTIÓN DE DATOS (Edita la tabla 👇)")
    st.info("Corrige el sentimiento o marca 'Irrelevante' para descartar.")
    
    # EDITOR DE DATOS
    df_edited = st.data_editor(
        st.session_state.df_noticias,
        column_config={
            "Sentimiento": st.column_config.SelectboxColumn("Juicio", options=["Positivo", "Negativo", "Neutro", "Irrelevante"], required=True),
            "Link": st.column_config.LinkColumn("Ver Original"),
            "Score": None, "Manual": None
        },
        use_container_width=True,
        num_rows="dynamic",
        key="editor"
    )
    
    # FILTRAR PARA DASHBOARD
    df_final = df_edited[df_edited.Sentimiento != 'Irrelevante']
    
    if not df_final.empty:
        st.divider()
        st.markdown("### 2️⃣ DASHBOARD EJECUTIVO")
        
        # CÁLCULOS
        pos = len(df_final[df_final.Sentimiento=='Positivo'])
        neg = len(df_final[df_final.Sentimiento=='Negativo'])
        tot = len(df_final)
        
        # VELOCÍMETRO + MÉTRICAS
        c1, c2 = st.columns([1, 2])
        with c1:
            val = ((pos * 100) + (tot - neg - pos) * 50) / tot if tot > 0 else 0
            fig = go.Figure(go.Indicator(
                mode = "gauge+number", value = val, title={'text':"REPUTACIÓN"},
                gauge={'axis':{'range':[None,100]}, 'steps':[
                    {'range':[0,40], 'color':'#ff4b4b'},
                    {'range':[40,70], 'color':'#f1c40f'},
                    {'range':[70,100], 'color':'#00ffbf'}
                ]}
            ))
            fig.update_layout(height=250, margin=dict(t=30,b=20,l=20,r=20), paper_bgcolor="rgba(0,0,0,0)", font={'color':'white'})
            st.plotly_chart(fig, use_container_width=True)
            
        with c2:
            k1, k2, k3 = st.columns(3)
            k1.metric("Volumen", tot)
            k2.metric("Positivos", pos, delta="🟢")
            k3.metric("Negativos", neg, delta="-🔴", delta_color="inverse")
            
            # SUNBURST (Mapa Interactivo)
            st.markdown("**Mapa de Calor (Click para explorar):**")
            fig_sun = px.sunburst(df_final, path=['Sentimiento', 'Fuente', 'Titular'], color='Sentimiento',
                                  color_discrete_map={'Positivo':'#00ffbf', 'Negativo':'#ff4b4b', 'Neutro':'#f1c40f'})
            fig_sun.update_layout(height=300, margin=dict(t=0,b=0,l=0,r=0), paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_sun, use_container_width=True)

        # NUBE Y DESCARGA
        st.divider()
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("#### ☁️ Temas Clave")
            txt = " ".join(df_final['Titular'])
            wc = WordCloud(width=600, height=300, background_color='#0e1117', colormap='Pastel1').generate(txt)
            fig_wc, ax = plt.subplots(); ax.imshow(wc); ax.axis("off"); fig_wc.patch.set_facecolor('#0e1117')
            st.pyplot(fig_wc)
            
        with c4:
            st.markdown("#### 📥 Exportar")
            st.write("Genera un informe oficial con los datos actuales.")
            pdf_path = generar_pdf(df_final, tema)
            with open(pdf_path, "rb") as f:
                st.download_button("📄 DESCARGAR PDF OFICIAL", f, "Reporte_Sentinel.pdf", use_container_width=True)

else:
    st.info("👆 Presiona ESCANEAR para comenzar o agrega noticias manualmente en el menú.")
