import streamlit as st
import feedparser
import pandas as pd
from transformers import pipeline
from datetime import datetime, timedelta
import time
import altair as alt
from urllib.parse import quote
from wordcloud import WordCloud
import matplotlib.pyplot as plt
from fpdf import FPDF
import tempfile
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap
import random

# --- CONFIGURACIÓN ---
st.set_page_config(
    page_title="Sentinel AI: Strategist", 
    layout="wide", 
    page_icon="📡",
    initial_sidebar_state="expanded"
)

# --- ESTILOS VISUALES ---
st.markdown("""
    <style>
    .main { background: linear-gradient(to bottom, #0e1117, #161b22); }
    h1 { background: -webkit-linear-gradient(#00c6ff, #0072ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    div[data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 10px; padding: 10px;
    }
    .stTabs [aria-selected="true"] { background-color: #0072ff !important; color: white !important; }
    </style>
    """, unsafe_allow_html=True)

# --- MEMORIA ---
if 'data_main' not in st.session_state: st.session_state.data_main = pd.DataFrame()
if 'data_comp' not in st.session_state: st.session_state.data_comp = pd.DataFrame()

# --- FUNCIONES ---
@st.cache_resource
def cargar_modelo():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def construir_url(query, tipo, extra_keys, sitios):
    # Construcción avanzada de Query
    base = query
    if extra_keys: base += f" {extra_keys}" # Agregamos las palabras clave extra
    
    q_encoded = quote(base)
    
    # Filtros
    if tipo == "Redes Sociales":
        q_encoded += quote(" site:twitter.com OR site:facebook.com OR site:instagram.com OR site:tiktok.com")
    elif tipo == "Solo Prensa":
        q_encoded += quote(" when:14d") # Últimos 14 días
        
    if sitios:
        for s in sitios.split(","):
            if s.strip(): q_encoded += quote(f" OR site:{s.strip()}")
            
    return f"https://news.google.com/rss/search?q={q_encoded}&hl=es-419&gl=CL&ceid=CL:es-419"

def ejecutar_busqueda(objetivo, etiqueta, tipo, inicio, fin, extra_keys, sitios):
    analizador = cargar_modelo()
    url = construir_url(objetivo, tipo, extra_keys, sitios)
    feed = feedparser.parse(url)
    data = []
    
    # Barra de progreso visual
    prog = st.progress(0)
    total = len(feed.entries)
    
    for i, item in enumerate(feed.entries):
        try:
            fecha = datetime.fromtimestamp(time.mktime(item.published_parsed)).date()
        except: fecha = datetime.now().date()
        
        if not (inicio <= fecha <= fin): continue

        try:
            pred = analizador(item.title[:512])[0]
            score = int(pred['label'].split()[0])
            sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
            fuente = item.source.title if 'source' in item else "Web"
            
            # Ubicación simple (mockup funcional)
            lat, lon = -29.9027 + random.uniform(-0.05, 0.05), -71.2519 + random.uniform(-0.05, 0.05)
            
            data.append({
                'Fecha': fecha, 'Fuente': fuente, 'Titular': item.title,
                'Sentimiento': sent, 'Link': item.link, 'Score': score,
                'Etiqueta': etiqueta, # Quién es (Candidato A o B)
                'Lat': lat, 'Lon': lon
            })
        except: pass
        if total > 0: prog.progress((i+1)/total)
        
    prog.empty()
    return pd.DataFrame(data)

# --- INTERFAZ SIDEBAR ---
with st.sidebar:
    st.header("🎛️ Centro de Mando")
    
    # 1. SELECTOR DE MODO (CRUCIAL)
    modo = st.radio("MODO DE OPERACIÓN", ["🔍 Análisis Individual", "⚔️ Versus (Comparativa)"], index=0)
    st.markdown("---")
    
    # 2. INPUTS SEGÚN MODO
    if modo == "🔍 Análisis Individual":
        obj1 = st.text_input("OBJETIVO", "Daniela Norambuena")
        obj2 = None
    else:
        c1, c2 = st.columns(2)
        obj1 = c1.text_input("OBJETIVO A", "Daniela Norambuena")
        obj2 = c2.text_input("OBJETIVO B", "Roberto Jacob")
    
    # 3. PALABRAS CLAVE ADICIONALES
    st.markdown("##### ➕ Refinamiento")
    extra = st.text_input("Palabras Clave Extra", placeholder="Ej: Festival, Denuncia, Encuesta")
    st.caption("Se sumarán a la búsqueda principal.")
    
    st.markdown("---")
    tipo = st.selectbox("Fuentes", ["Todo Internet", "Solo Prensa", "Redes Sociales"])
    sitios = st.text_area("Sitios Prioritarios", "elobservatodo.cl, miradiols.cl, biobiochile.cl")
    
    col_d1, col_d2 = st.columns(2)
    ini = col_d1.date_input("Inicio", datetime.now()-timedelta(days=14))
    fin = col_d2.date_input("Fin", datetime.now())
    
    btn_start = st.button("🚀 EJECUTAR ESTRATEGIA", type="primary")

# --- LÓGICA PRINCIPAL ---
st.title("📡 SENTINEL AI: STRATEGIST")

if btn_start:
    st.session_state.data_main = pd.DataFrame() # Limpiar
    
    # Búsqueda 1
    with st.status(f"Analizando a {obj1}...") as status:
        df1 = ejecutar_busqueda(obj1, obj1, tipo, ini, fin, extra, sitios)
        st.session_state.data_main = df1
        status.update(label="Objetivo A completado", state="complete")
        
    # Búsqueda 2 (Solo si es Versus)
    if modo == "⚔️ Versus (Comparativa)" and obj2:
        with st.status(f"Analizando a {obj2}...") as status:
            df2 = ejecutar_busqueda(obj2, obj2, tipo, ini, fin, extra, sitios)
            # Unimos ambas bases de datos
            st.session_state.data_main = pd.concat([df1, df2], ignore_index=True)
            status.update(label="Objetivo B completado", state="complete")

# --- VISUALIZACIÓN DE RESULTADOS ---
df = st.session_state.data_main

if not df.empty:
    
    # === MODO 1: INDIVIDUAL ===
    if modo == "🔍 Análisis Individual":
        st.subheader(f"Informe de Situación: {obj1}")
        
        # KPIs
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Volumen", len(df))
        k2.metric("Positivos", len(df[df.Sentimiento=='Positivo']), delta="🟢")
        k3.metric("Negativos", len(df[df.Sentimiento=='Negativo']), delta="-🔴", delta_color="inverse")
        k4.metric("Fuentes", df['Fuente'].nunique())
        
        st.divider()
        
        # Gráficos
        c1, c2 = st.columns([2,1])
        with c1:
            st.markdown("##### 📈 Evolución Temporal")
            chart = alt.Chart(df).mark_line(point=True).encode(
                x='Fecha', y='count()', color='Sentimiento', tooltip=['Fecha', 'Sentimiento', 'count()']
            ).properties(height=350)
            st.altair_chart(chart, use_container_width=True)
        with c2:
            st.markdown("##### 🍩 Distribución")
            chart_pie = alt.Chart(df).mark_arc(innerRadius=50).encode(
                theta='count()', color=alt.Color('Sentimiento', scale=alt.Scale(domain=['Positivo', 'Negativo', 'Neutro'], range=['#00c6ff', '#ff4b4b', '#aaaaaa']))
            )
            st.altair_chart(chart_pie, use_container_width=True)
            
    # === MODO 2: VERSUS (COMPARATIVA) ===
    elif modo == "⚔️ Versus (Comparativa)":
        st.subheader(f"⚔️ {obj1} vs {obj2}")
        
        # Comparativa Directa (Barras lado a lado)
        st.markdown("##### 📊 Dominio de la Conversación (Share of Voice)")
        
        # Gráfico de Barras Agrupado
        chart_vs = alt.Chart(df).mark_bar().encode(
            x=alt.X('Etiqueta', title=None), # Eje X: Los candidatos
            y=alt.Y('count()', title='Menciones'),
            color=alt.Color('Etiqueta', scale=alt.Scale(scheme='set1')), # Color por candidato
            column=alt.Column('Sentimiento', header=alt.Header(titleFontSize=15)) # Columnas por sentimiento
        ).properties(width=200, height=300)
        
        st.altair_chart(chart_vs)
        
        st.divider()
        
        # Tabla de Ganadores
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🏆 Ranking de Positividad")
            pos_df = df[df.Sentimiento=='Positivo'].groupby('Etiqueta').size().reset_index(name='Votos Positivos')
            st.dataframe(pos_df, use_container_width=True)
            
        with c2:
            st.markdown("##### ⚠️ Ranking de Crisis (Negatividad)")
            neg_df = df[df.Sentimiento=='Negativo'].groupby('Etiqueta').size().reset_index(name='Menciones Negativas')
            st.dataframe(neg_df, use_container_width=True)

    # === SECCIONES COMUNES (MAPA Y DATOS) ===
    st.divider()
    tabs = st.tabs(["🗺️ Mapa de Impacto", "☁️ Nube de Contexto", "📝 Datos Brutos"])
    
    with tabs[0]:
        m = folium.Map(location=[-29.9027, -71.2519], zoom_start=11, tiles="CartoDB dark_matter")
        HeatMap([[r['Lat'], r['Lon']] for i, r in df.iterrows()], radius=15).add_to(m)
        st_folium(m, width="100%", height=400)
        
    with tabs[1]:
        text = " ".join(df['Titular'])
        wc = WordCloud(width=800, height=300, background_color='#0e1117', colormap='Wistia').generate(text)
        fig, ax = plt.subplots(); ax.imshow(wc); ax.axis("off"); fig.patch.set_facecolor('#0e1117')
        st.pyplot(fig)
        
    with tabs[2]:
        st.dataframe(df[['Fecha', 'Etiqueta', 'Fuente', 'Sentimiento', 'Titular', 'Link']], use_container_width=True)
        
        # Exportar PDF
        if st.button("📄 Descargar Reporte"):
            pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", size=10)
            pdf.cell(0,10, f"Reporte Sentinel - {datetime.now().date()}",0,1)
            for i,r in df.iterrows():
                try: pdf.multi_cell(0,5, f"[{r['Etiqueta']}] {r['Titular']}".encode('latin-1','replace').decode('latin-1')); pdf.ln(1)
                except: pass
            t = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); pdf.output(t.name)
            with open(t.name, "rb") as f: st.download_button("Descargar PDF", f, "reporte.pdf")

else:
    st.info("👈 Selecciona el modo y ejecuta la estrategia desde el menú lateral.")
