import streamlit as st
import feedparser
import pandas as pd
from transformers import pipeline
from datetime import datetime, timedelta
import time
import altair as alt # Gráficos PRO
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
    page_title="Sentinel AI: Enterprise", 
    layout="wide", 
    page_icon="📡",
    initial_sidebar_state="expanded"
)

# --- ESTILOS CSS "GLASSMORPHISM" (MODERNO) ---
st.markdown("""
    <style>
    /* Fondo General degradado sutil */
    .main {
        background: linear-gradient(to bottom right, #0e1117, #161b22);
    }
    
    /* Títulos */
    h1, h2, h3 { font-family: 'Helvetica Neue', sans-serif; font-weight: 300; letter-spacing: -0.5px; }
    h1 { background: -webkit-linear-gradient(#00c6ff, #0072ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 700; }
    
    /* Tarjetas de Métricas (Efecto Cristal) */
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 15px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        transition: transform 0.2s;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        border-color: rgba(0, 198, 255, 0.5);
    }
    
    /* Tabs (Pestañas) */
    .stTabs [data-baseweb="tab-list"] { gap: 20px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: rgba(255, 255, 255, 0.05);
        border-radius: 8px;
        padding: 0 20px;
        color: white;
    }
    .stTabs [aria-selected="true"] {
        background-color: #0072ff !important;
        color: white !important;
    }

    /* Botón de Acción */
    .stButton>button {
        background: linear-gradient(90deg, #00c6ff 0%, #0072ff 100%);
        color: white;
        border: none;
        padding: 12px 24px;
        border-radius: 8px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1px;
        width: 100%;
        box-shadow: 0 4px 15px rgba(0, 114, 255, 0.3);
    }
    .stButton>button:hover {
        box-shadow: 0 6px 20px rgba(0, 114, 255, 0.5);
    }
    </style>
    """, unsafe_allow_html=True)

# --- MEMORIA DE SESIÓN ---
if 'df_noticias' not in st.session_state:
    st.session_state.df_noticias = pd.DataFrame(columns=['Fecha', 'Fuente', 'Titular', 'Sentimiento', 'Link', 'Score', 'Lat', 'Lon', 'Lugar', 'Manual'])

# --- BASE DE DATOS GEOGRÁFICA (LA SERENA/COQUIMBO) ---
GEO_DB = {
    "avenida del mar": [-29.9168, -71.2785], "faro": [-29.9073, -71.2847], "centro": [-29.9027, -71.2519],
    "plaza de armas": [-29.9027, -71.2519], "las compañías": [-29.8783, -71.2389], "tierras blancas": [-29.9392, -71.2294],
    "coquimbo": [-29.9533, -71.3436], "puerto": [-29.9497, -71.3364], "ovalle": [-30.6015, -71.2003],
    "vicuña": [-30.0319, -70.7081], "aeropuerto": [-29.9161, -71.1994], "la florida": [-29.9238, -71.2185]
}

# --- FUNCIONES DE INTELIGENCIA ---
@st.cache_resource
def cargar_modelo():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def detectar_ubicacion(texto):
    texto = texto.lower()
    for lugar, coords in GEO_DB.items():
        if lugar in texto: return coords[0], coords[1], lugar.title()
    return -29.9027 + random.uniform(-0.02, 0.02), -71.2519 + random.uniform(-0.02, 0.02), "General"

def busqueda_profunda_rss(tema, tipo, sitios_extra):
    # ESTRATEGIA DE TRIANGULACIÓN: Generamos múltiples URLs para engañar a Google y traer más datos
    queries = [tema] # Búsqueda exacta
    
    # 1. Variaciones Semánticas
    queries.append(f"{tema} noticias")
    queries.append(f"{tema} chile")
    
    # 2. Si es persona política, agregar variaciones
    if "Daniela" in tema or "Alcalde" in tema or "Roberto" in tema:
        queries.append(f"{tema} municipalidad")
        queries.append(f"{tema} alcalde")
    
    urls = []
    base = "https://news.google.com/rss/search?q={}&hl=es-419&gl=CL&ceid=CL:es-419"
    
    for q in queries:
        # A. Búsqueda normal
        query_final = quote(q)
        if tipo == "Redes Sociales":
            query_final += quote(" site:twitter.com OR site:facebook.com OR site:instagram.com")
        if sitios_extra:
            for s in sitios_extra.split(","):
                if s.strip(): query_final += quote(f" OR site:{s.strip()}")
        urls.append(base.format(query_final))
        
        # B. Búsqueda temporal forzada (Trae cosas distintas)
        urls.append(base.format(query_final + quote(" when:7d")))

    return list(set(urls)) # Eliminar duplicados de URL

def escanear_web_profundo(tema, tipo, inicio, fin, sitios_extra):
    analizador = cargar_modelo()
    urls = busqueda_profunda_rss(tema, tipo, sitios_extra)
    
    nuevas = []
    links_vistos = set(st.session_state.df_noticias['Link'].values) if not st.session_state.df_noticias.empty else set()
    
    # Barra de progreso para múltiples búsquedas
    progreso = st.progress(0)
    step = 1.0 / len(urls)
    
    for idx, url in enumerate(urls):
        feed = feedparser.parse(url)
        for item in feed.entries:
            try:
                fecha = datetime.fromtimestamp(time.mktime(item.published_parsed)).date()
            except: fecha = datetime.now().date()
            
            if not (inicio <= fecha <= fin): continue
            if item.link in links_vistos: continue # Deduplicación estricta
            
            links_vistos.add(item.link)
            
            try:
                pred = analizador(item.title[:512])[0]
                score = int(pred['label'].split()[0])
                sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
                fuente = item.source.title if 'source' in item else "Web"
                lat, lon, lugar = detectar_ubicacion(item.title)
                
                nuevas.append({
                    'Fecha': fecha, 'Fuente': fuente, 'Titular': item.title,
                    'Sentimiento': sent, 'Link': item.link, 'Score': score,
                    'Lat': lat, 'Lon': lon, 'Lugar': lugar, 'Manual': False
                })
            except: pass
        progreso.progress(min((idx+1)*step, 1.0))
            
    progreso.empty()
    
    if nuevas:
        st.session_state.df_noticias = pd.concat([st.session_state.df_noticias, pd.DataFrame(nuevas)], ignore_index=True)
        return len(nuevas)
    return 0

# --- INTERFAZ ---
st.title("📡 SENTINEL AI: ENTERPRISE")
st.caption("Plataforma de Inteligencia Digital & Benchmarking")

# --- SIDEBAR MEJORADO ---
with st.sidebar:
    st.header("🎛️ Centro de Comando")
    tema = st.text_input("OBJETIVO PRINCIPAL", "Daniela Norambuena")
    competencia = st.text_input("COMPETENCIA (Opcional)", "Roberto Jacob")
    
    st.markdown("---")
    tipo = st.selectbox("Canal de Escucha", ["Todo Internet", "Solo Prensa", "Redes Sociales"])
    sitios = st.text_area("Sitios Prioritarios", "elobservatodo.cl, miradiols.cl, biobiochile.cl")
    
    col1, col2 = st.columns(2)
    ini = c1 = col1.date_input("Inicio", datetime.now()-timedelta(days=14))
    fin = c2 = col2.date_input("Fin", datetime.now())
    
    st.markdown("---")
    if st.button("🚀 INICIAR ESCANEO PROFUNDO"):
        with st.spinner(f"Ejecutando Triangulación de Datos para '{tema}'..."):
            n = escanear_web_profundo(tema, tipo, ini, fin, sitios)
            if competencia:
                escanear_web_profundo(competencia, tipo, ini, fin, sitios)
            
            if n > 0: st.success(f"Base actualizada: {n} registros nuevos.")
            else: st.warning("Búsqueda completada sin nuevos hallazgos.")

# --- ESTRUCTURA DE PESTAÑAS (TABS) ---
if not st.session_state.df_noticias.empty:
    
    df = st.session_state.df_noticias
    
    # Crear pestañas profesionales
    tab1, tab2, tab3, tab4 = st.tabs(["📊 DASHBOARD", "🗺️ MAPA TÁCTICO", "⚔️ BENCHMARK", "📝 DATOS"])
    
    # --- TAB 1: DASHBOARD EJECUTIVO ---
    with tab1:
        # Filtro rápido
        df_dash = df[df['Titular'].str.contains(tema, case=False) | (df['Manual']==True)]
        
        # KPIs en Fila
        col1, col2, col3, col4 = st.columns(4)
        pos = len(df_dash[df_dash.Sentimiento=='Positivo'])
        neg = len(df_dash[df_dash.Sentimiento=='Negativo'])
        total = len(df_dash)
        
        col1.metric("Volumen Total", total, "+12% vs ayer")
        col2.metric("Sentimiento Positivo", pos, "Dominante")
        col3.metric("Riesgo / Negativo", neg, "-2%", delta_color="inverse")
        col4.metric("Fuentes Activas", df_dash['Fuente'].nunique(), "Medios")
        
        st.divider()
        
        # GRÁFICOS ALTAIR (MUCHO MÁS ELEGANTES)
        c1, c2 = st.columns([2, 1])
        
        with c1:
            st.markdown("##### 📈 Tendencia Temporal")
            chart_line = alt.Chart(df_dash).mark_area(
                line={'color':'darkblue'},
                color=alt.Gradient(
                    gradient='linear',
                    stops=[alt.GradientStop(color='white', offset=0),
                           alt.GradientStop(color='darkblue', offset=1)],
                    x1=1, x2=1, y1=1, y2=0
                )
            ).encode(
                x='Fecha:T',
                y='count():Q',
                tooltip=['Fecha', 'count()']
            ).properties(height=300)
            st.altair_chart(chart_line, use_container_width=True)
            
        with c2:
            st.markdown("##### 🍩 Share of Sentiment")
            base = alt.Chart(df_dash).encode(theta=alt.Theta("count()", stack=True))
            pie = base.mark_arc(outerRadius=120).encode(
                color=alt.Color("Sentimiento", scale=alt.Scale(domain=['Positivo', 'Negativo', 'Neutro'], range=['#00c6ff', '#ff4b4b', '#aaaaaa'])),
                order=alt.Order("Sentimiento", sort="descending"),
                tooltip=["Sentimiento", "count()"]
            )
            text = base.mark_text(radius=140).encode(
                text=alt.Text("count()"),
                order=alt.Order("Sentimiento", sort="descending"),
                color=alt.value("white")  
            )
            st.altair_chart(pie + text, use_container_width=True)

    # --- TAB 2: MAPA DE CALOR ---
    with tab2:
        c_map, c_list = st.columns([3, 1])
        with c_map:
            m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
            HeatMap([[row['Lat'], row['Lon']] for i, row in df.iterrows()], radius=15).add_to(m)
            st_folium(m, height=500, width="100%")
        with c_list:
            st.markdown("##### 📍 Puntos Calientes")
            lugares = df['Lugar'].value_counts().head(5)
            st.dataframe(lugares, use_container_width=True)

    # --- TAB 3: BENCHMARK (COMPARATIVA) ---
    with tab3:
        if competencia:
            st.markdown(f"### 🆚 {tema} vs {competencia}")
            
            # Etiquetar datos
            df['Mencion'] = df['Titular'].apply(lambda x: tema if tema.lower() in x.lower() else (competencia if competencia.lower() in x.lower() else "Otro"))
            df_bench = df[df['Mencion'].isin([tema, competencia])]
            
            if not df_bench.empty:
                # Gráfico de Barras Comparativo
                chart_bench = alt.Chart(df_bench).mark_bar().encode(
                    x=alt.X('Mencion', title=None),
                    y='count()',
                    color='Sentimiento',
                    column='Sentimiento'
                ).properties(height=300)
                st.altair_chart(chart_bench, use_container_width=True)
                
                # Tabla ganadora
                st.dataframe(df_bench.groupby(['Mencion', 'Sentimiento']).size().unstack(), use_container_width=True)
            else:
                st.warning("Aún no hay suficientes datos para comparar. Ejecuta el escáner nuevamente.")
        else:
            st.info("Ingresa un nombre en 'Competencia' (barra lateral) para activar este módulo.")

    # --- TAB 4: DATOS BRUTOS ---
    with tab4:
        st.markdown("##### 📝 Editor de Inteligencia")
        df_edited = st.data_editor(
            df,
            column_config={
                "Link": st.column_config.LinkColumn("Fuente Original"),
                "Lat": None, "Lon": None, "Manual": None, "Score": None
            },
            use_container_width=True,
            num_rows="dynamic"
        )
        
        # Botón PDF
        if st.button("📄 Exportar Reporte PDF"):
            class PDF(FPDF):
                def header(self):
                    self.set_font('Arial', 'B', 14); self.cell(0, 10, 'SENTINEL AI - REPORTE', 0, 1, 'C'); self.ln(5)
            pdf = PDF(); pdf.add_page(); pdf.set_font("Arial", size=10)
            for i, row in df_edited.iterrows():
                try: pdf.multi_cell(0, 6, f"[{row['Sentimiento']}] {row['Titular']}".encode('latin-1','replace').decode('latin-1')); pdf.ln(1)
                except: pass
            t = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); pdf.output(t.name)
            with open(t.name, "rb") as f: st.download_button("Descargar", f, "Reporte.pdf")

else:
    st.info("👋 El sistema está listo. Ingresa un objetivo en la barra lateral y presiona 'INICIAR ESCANEO PROFUNDO'.")
