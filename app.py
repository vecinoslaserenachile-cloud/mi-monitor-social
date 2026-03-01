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

# --- 1. CONFIGURACIÓN ---
st.set_page_config(
    page_title="Sentinel AI: Deep Mining", 
    layout="wide", 
    page_icon="📡",
    initial_sidebar_state="expanded"
)

# --- 2. ESTILOS CSS (Mejorados para Móvil y Escritorio) ---
st.markdown("""
    <style>
    .main { background: linear-gradient(180deg, #0e1117 0%, #161b22 100%); }
    h1 { background: -webkit-linear-gradient(#00c6ff, #0072ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    
    /* Métricas */
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 10px;
        padding: 10px;
        border: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    /* Botón de Acción */
    .stButton>button {
        background: linear-gradient(90deg, #0062cc 0%, #00c6ff 100%);
        color: white; border: none; padding: 15px; border-radius: 8px;
        font-weight: bold; width: 100%; letter-spacing: 1px;
    }
    
    /* Tabs */
    .stTabs [aria-selected="true"] {
        background-color: #0072ff !important;
        color: white !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. MEMORIA ---
if 'data_mining' not in st.session_state:
    st.session_state.data_mining = pd.DataFrame(columns=['Fecha', 'Fuente', 'Titular', 'Sentimiento', 'Link', 'Score', 'Tipo', 'Lat', 'Lon', 'Lugar', 'Manual'])

# --- 4. DATA GEOESPACIAL ---
GEO_DB = {
    "avenida del mar": [-29.9168, -71.2785], "faro": [-29.9073, -71.2847], "centro": [-29.9027, -71.2519],
    "plaza de armas": [-29.9027, -71.2519], "las compañías": [-29.8783, -71.2389], "tierras blancas": [-29.9392, -71.2294],
    "coquimbo": [-29.9533, -71.3436], "ovalle": [-30.6015, -71.2003], "vicuña": [-30.0319, -70.7081],
    "aeropuerto": [-29.9161, -71.1994], "la florida": [-29.9238, -71.2185], "el milagro": [-29.9333, -71.2333],
    "serena": [-29.9027, -71.2519]
}

# --- 5. INTELIGENCIA & MINERÍA DE DATOS ---
@st.cache_resource
def cargar_modelo():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def detectar_ubicacion(texto):
    texto = texto.lower()
    for lugar, coords in GEO_DB.items():
        if lugar in texto: return coords[0], coords[1], lugar.title()
    # Coordenada aleatoria cerca del centro para evitar superposición
    return -29.9027 + random.uniform(-0.03, 0.03), -71.2519 + random.uniform(-0.03, 0.03), "General"

def clasificar_fuente(link):
    if any(x in link for x in ['twitter', 'facebook', 'instagram', 'tiktok', 'reddit']): return "Red Social"
    return "Prensa/Web"

def generar_busqueda_profunda(objetivo, extra):
    # ESTRATEGIA HYDRA: Multiplicar las búsquedas por sitio específico para romper el filtro de Google
    urls = []
    base_rss = "https://news.google.com/rss/search?q={}&hl=es-419&gl=CL&ceid=CL:es-419"
    
    # 1. Medios Clave (Búsqueda dirigida sitio por sitio)
    medios_norte = [
        "diarioeldia.cl", "elobservatodo.cl", "miradiols.cl", "laserenaonline.cl", 
        "biobiochile.cl", "emol.com", "latercera.com", "davidnoticias.cl", "limari.cl"
    ]
    
    # Generar queries específicas: "Daniela Norambuena site:diarioeldia.cl"
    for medio in medios_norte:
        query = f'"{objetivo}" site:{medio}'
        urls.append(base_rss.format(quote(query)))
        
    # 2. Búsqueda General Amplia
    queries_gen = [
        f'{objetivo}',
        f'{objetivo} La Serena',
        f'{objetivo} Coquimbo',
        f'{objetivo} noticias'
    ]
    
    # 3. Extras
    if extra:
        for k in extra.split(","):
            queries_gen.append(f'{objetivo} {k.strip()}')
            
    for q in queries_gen:
        urls.append(base_rss.format(quote(q)))
        
    return list(set(urls)) # Eliminar duplicados

def minar_datos(objetivo, inicio, fin, extra):
    analizador = cargar_modelo()
    urls = generar_busqueda_profunda(objetivo, extra)
    resultados = []
    vistos = set()
    
    # Barra de progreso
    bar = st.progress(0)
    status = st.empty()
    
    total_urls = len(urls)
    
    for i, url in enumerate(urls):
        status.text(f"Minando fuente {i+1} de {total_urls}...")
        try:
            feed = feedparser.parse(url)
            for item in feed.entries:
                try:
                    fecha = datetime.fromtimestamp(time.mktime(item.published_parsed)).date()
                except: fecha = datetime.now().date()
                
                if not (inicio <= fecha <= fin): continue
                if item.link in vistos: continue
                vistos.add(item.link)
                
                # Análisis
                pred = analizador(item.title[:512])[0]
                score = int(pred['label'].split()[0])
                sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
                fuente = item.source.title if 'source' in item else "Web"
                tipo = clasificar_fuente(item.link)
                lat, lon, lugar = detectar_ubicacion(item.title)
                
                resultados.append({
                    'Fecha': fecha, 'Fuente': fuente, 'Titular': item.title,
                    'Sentimiento': sent, 'Link': item.link, 'Score': score,
                    'Tipo': tipo, 'Lat': lat, 'Lon': lon, 'Lugar': lugar, 'Manual': False
                })
        except: pass
        bar.progress((i + 1) / total_urls)
        
    status.empty()
    bar.empty()
    return pd.DataFrame(resultados)

# --- 6. BARRA LATERAL (ORDEN CORREGIDO) ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3208/3208726.png", width=50)
    st.title("PANEL DE MANDO")
    
    st.header("1. Configuración de Búsqueda")
    objetivo = st.text_input("Objetivo Principal", "Daniela Norambuena")
    extra_kw = st.text_input("Palabras Clave Extra", placeholder="Ej: seguridad, festival, obras")
    
    fechas = st.columns(2)
    ini = fechas[0].date_input("Inicio", datetime.now() - timedelta(days=30))
    fin = fechas[1].date_input("Fin", datetime.now())
    
    btn_scan = st.button("🚀 EJECUTAR MINERÍA PROFUNDA")
    
    st.markdown("---")
    
    # Ingreso Manual al final
    with st.expander("📝 Ingreso Manual de Datos"):
        with st.form("manual"):
            m_txt = st.text_input("Titular/Dato")
            m_src = st.text_input("Fuente")
            m_sen = st.selectbox("Sentimiento", ["Positivo", "Negativo"])
            if st.form_submit_button("Guardar"):
                new = {'Fecha': datetime.now().date(), 'Fuente': m_src, 'Titular': m_txt, 'Sentimiento': m_sen, 'Link':'#', 'Score':0, 'Tipo': 'Manual', 'Lat':-29.90, 'Lon':-71.25, 'Lugar':'Manual', 'Manual':True}
                st.session_state.data_mining = pd.concat([st.session_state.data_mining, pd.DataFrame([new])], ignore_index=True)
                st.success("Guardado")

# --- 7. LOGICA PRINCIPAL ---
if btn_scan:
    st.session_state.data_mining = pd.DataFrame()
    with st.spinner("Iniciando Motores de Búsqueda... Esto puede tomar unos segundos para maximizar resultados."):
        df_new = minar_datos(objetivo, ini, fin, extra_kw)
        st.session_state.data_mining = df_new

# --- 8. DASHBOARD VISUAL ---
df = st.session_state.data_mining

if not df.empty:
    # --- ENCABEZADO ---
    st.markdown(f"## 📡 Informe de Inteligencia: *{objetivo}*")
    
    # KPIs
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Volumen Total", len(df), delta="Datos en tiempo real")
    k2.metric("Positivos", len(df[df.Sentimiento=='Positivo']), delta="🟢")
    k3.metric("Negativos", len(df[df.Sentimiento=='Negativo']), delta="-🔴", delta_color="inverse")
    k4.metric("Fuentes Únicas", df['Fuente'].nunique())
    
    # --- PESTAÑAS ---
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Estadísticas & Conceptos", "🗺️ Mapa Geo-Táctico", "🏆 Ranking de Fuentes", "📝 Datos Brutos"])
    
    # 1. ESTADÍSTICAS
    with tab1:
        c1, c2 = st.columns([2, 1])
        
        with c1:
            st.subheader("🕸️ Mapa Conceptual (Haz clic para explorar)")
            # SUNBURST: Sentimiento -> Fuente -> Noticia
            fig_sun = px.sunburst(
                df, path=['Sentimiento', 'Fuente', 'Titular'], 
                color='Sentimiento',
                color_discrete_map={'Positivo':'#00c853', 'Negativo':'#d50000', 'Neutro':'#ffab00'},
                height=500
            )
            st.plotly_chart(fig_sun, use_container_width=True)
            
            st.subheader("📈 Evolución Temporal")
            df_trend = df.groupby(['Fecha', 'Sentimiento']).size().reset_index(name='Count')
            fig_line = px.area(df_trend, x='Fecha', y='Count', color='Sentimiento', 
                               color_discrete_map={'Positivo':'#00c853', 'Negativo':'#d50000', 'Neutro':'#ffab00'})
            st.plotly_chart(fig_line, use_container_width=True)
            
        with c2:
            st.subheader("🚦 Termómetro de Marca")
            # GAUGE
            pos = len(df[df.Sentimiento=='Positivo'])
            neg = len(df[df.Sentimiento=='Negativo'])
            total = len(df)
            score = ((pos * 100) + (total - neg - pos) * 50) / total if total > 0 else 0
            
            fig_gauge = go.Figure(go.Indicator(
                mode = "gauge+number", value = score,
                gauge = {
                    'axis': {'range': [None, 100]}, 'bar': {'color': "rgba(0,0,0,0)"},
                    'steps': [{'range': [0, 40], 'color': "#d50000"}, {'range': [40, 70], 'color': "#ffab00"}, {'range': [70, 100], 'color': "#00c853"}],
                    'threshold': {'line': {'color': "white", 'width': 4}, 'thickness': 0.75, 'value': score}
                }
            ))
            fig_gauge.update_layout(height=300, margin=dict(t=0, b=0, l=0, r=0), paper_bgcolor="rgba(0,0,0,0)", font={'color':"white"})
            st.plotly_chart(fig_gauge, use_container_width=True)
            
            st.markdown("##### ☁️ Nube Semántica")
            wc = WordCloud(width=400, height=300, background_color='#0e1117', colormap='Wistia').generate(" ".join(df['Titular']))
            fig_wc, ax = plt.subplots(); ax.imshow(wc); ax.axis("off"); fig_wc.patch.set_facecolor('#0e1117')
            st.pyplot(fig_wc)

    # 2. MAPA (Arreglado)
    with tab2:
        st.subheader("📍 Mapa de Calor Regional (OpenStreetMap)")
        # Forzar mapa base
        m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12)
        HeatMap([[r['Lat'], r['Lon']] for i, r in df.iterrows()], radius=15).add_to(m)
        mc = MarkerCluster().add_to(m)
        for i, r in df.iterrows():
            folium.Marker(
                [r['Lat'], r['Lon']], popup=r['Titular'], 
                icon=folium.Icon(color="green" if r['Sentimiento']=='Positivo' else "red")
            ).add_to(mc)
        
        # Renderizado con ancho completo
        st_folium(m, width="100%", height=600)

    # 3. RANKING DE FUENTES (Separado)
    with tab3:
        c_prensa, c_social = st.columns(2)
        
        with c_prensa:
            st.markdown("### 📰 Top 10 Prensa/Web")
            prensa_df = df[df.Tipo != 'Red Social']['Fuente'].value_counts().head(10).reset_index()
            prensa_df.columns = ['Medio', 'Menciones']
            fig_p = px.bar(prensa_df, x='Menciones', y='Medio', orientation='h', color='Menciones', color_continuous_scale='Blues')
            fig_p.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig_p, use_container_width=True)
            
        with c_social:
            st.markdown("### 📱 Top Redes Sociales")
            social_df = df[df.Tipo == 'Red Social']['Fuente'].value_counts().head(10).reset_index()
            if not social_df.empty:
                social_df.columns = ['Red', 'Menciones']
                fig_s = px.pie(social_df, names='Red', values='Menciones', hole=0.4)
                st.plotly_chart(fig_s, use_container_width=True)
            else:
                st.info("No se detectaron suficientes datos de redes sociales en esta búsqueda.")

    # 4. DATOS Y PDF
    with tab4:
        st.dataframe(df, use_container_width=True)
        if st.button("📄 Descargar Reporte PDF"):
            pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", size=10)
            pdf.cell(0, 10, f"Informe Sentinel: {objetivo}", 0, 1)
            for i, r in df.iterrows():
                try: pdf.multi_cell(0, 5, f"[{r['Sentimiento']}] {r['Fuente']}: {r['Titular']}".encode('latin-1','replace').decode('latin-1')); pdf.ln(1)
                except: pass
            t = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); pdf.output(t.name)
            with open(t.name, "rb") as f: st.download_button("Descargar Archivo", f, "reporte.pdf")

else:
    st.info("👋 Configura tu búsqueda a la izquierda. El sistema usará minería profunda en múltiples medios locales.")
