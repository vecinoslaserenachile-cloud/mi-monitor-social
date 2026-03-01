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
from folium.plugins import HeatMap, MarkerCluster
import random

# --- 1. CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sentinel AI: Titan Edition", 
    layout="wide", 
    page_icon="📡",
    initial_sidebar_state="expanded"
)

# --- 2. ESTILOS CSS "GLASSMORPHISM" (RECUPERADO) ---
st.markdown("""
    <style>
    /* Fondo Degradado Tecnológico */
    .main {
        background: linear-gradient(135deg, #0f2027, #203a43, #2c5364);
    }
    h1 {
        background: -webkit-linear-gradient(#00c6ff, #0072ff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
    }
    h2, h3 { color: #e0e0e0; font-family: 'Helvetica Neue', sans-serif; }
    
    /* Tarjetas de Métricas Transparentes */
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 15px;
        padding: 15px;
        transition: transform 0.3s ease;
    }
    div[data-testid="stMetric"]:hover {
        transform: translateY(-5px);
        border-color: #00c6ff;
    }
    
    /* Botones Neón */
    .stButton>button {
        background: linear-gradient(90deg, #00c6ff 0%, #0072ff 100%);
        color: white;
        border: none;
        padding: 12px 24px;
        border-radius: 8px;
        font-weight: bold;
        text-transform: uppercase;
        width: 100%;
        box-shadow: 0 0 15px rgba(0, 114, 255, 0.4);
    }
    
    /* Pestañas */
    .stTabs [aria-selected="true"] {
        background-color: #0072ff !important;
        color: white !important;
        border-radius: 5px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. MEMORIA DE SESIÓN ---
if 'data_master' not in st.session_state:
    st.session_state.data_master = pd.DataFrame(columns=['Fecha', 'Fuente', 'Titular', 'Sentimiento', 'Link', 'Score', 'Etiqueta', 'Lat', 'Lon', 'Lugar', 'Manual'])

# --- 4. BASE DE DATOS GEOGRÁFICA (RECUPERADA) ---
GEO_DB = {
    "avenida del mar": [-29.9168, -71.2785], "faro": [-29.9073, -71.2847], "centro": [-29.9027, -71.2519],
    "plaza de armas": [-29.9027, -71.2519], "las compañías": [-29.8783, -71.2389], "tierras blancas": [-29.9392, -71.2294],
    "coquimbo": [-29.9533, -71.3436], "puerto": [-29.9497, -71.3364], "ovalle": [-30.6015, -71.2003],
    "vicuña": [-30.0319, -70.7081], "aeropuerto": [-29.9161, -71.1994], "la florida": [-29.9238, -71.2185],
    "cuatro esquinas": [-29.9263, -71.2687], "peñuelas": [-29.9442, -71.2872]
}

# --- 5. FUNCIONES DE INTELIGENCIA ---
@st.cache_resource
def cargar_modelo():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def detectar_ubicacion(texto):
    texto = texto.lower()
    for lugar, coords in GEO_DB.items():
        if lugar in texto:
            return coords[0], coords[1], lugar.title()
    # Coordenada base La Serena con dispersión
    return -29.9027 + random.uniform(-0.03, 0.03), -71.2519 + random.uniform(-0.03, 0.03), "General"

def construir_urls_ampliadas(objetivo, tipo, extra_keys, sitios):
    # Generamos múltiples URLs para capturar más datos (Triangulación)
    base_queries = [objetivo]
    
    # Variaciones automáticas
    if len(objetivo.split()) > 1: # Si es nombre compuesto (Ej: Daniela Norambuena)
        base_queries.append(f'"{objetivo}"') # Búsqueda exacta
    
    urls = []
    base_url = "https://news.google.com/rss/search?q={}&hl=es-419&gl=CL&ceid=CL:es-419"
    
    for q in base_queries:
        query = q
        if extra_keys: query += f" {extra_keys}"
        
        q_encoded = quote(query)
        
        # Filtros
        if tipo == "Redes Sociales":
            q_encoded += quote(" site:twitter.com OR site:facebook.com OR site:instagram.com OR site:tiktok.com")
        elif tipo == "Solo Prensa":
            q_encoded += quote(" when:14d")
            
        if sitios:
            for s in sitios.split(","):
                if s.strip(): q_encoded += quote(f" OR site:{s.strip()}")
        
        urls.append(base_url.format(q_encoded))
        
    return list(set(urls)) # Eliminar duplicados

def ejecutar_escaneo_profundo(objetivo, etiqueta, tipo, inicio, fin, extra, sitios):
    analizador = cargar_modelo()
    urls = construir_urls_ampliadas(objetivo, tipo, extra, sitios)
    resultados = []
    links_procesados = set()
    
    progreso = st.progress(0)
    step = 1.0 / len(urls)
    
    for idx, url in enumerate(urls):
        feed = feedparser.parse(url)
        for item in feed.entries:
            try:
                fecha = datetime.fromtimestamp(time.mktime(item.published_parsed)).date()
            except: fecha = datetime.now().date()
            
            if not (inicio <= fecha <= fin): continue
            if item.link in links_procesados: continue
            
            links_procesados.add(item.link)
            
            try:
                # IA
                pred = analizador(item.title[:512])[0]
                score = int(pred['label'].split()[0])
                sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
                fuente = item.source.title if 'source' in item else "Web"
                
                # Geo
                lat, lon, lugar = detectar_ubicacion(item.title + " " + (item.description if 'description' in item else ""))
                
                resultados.append({
                    'Fecha': fecha, 'Fuente': fuente, 'Titular': item.title,
                    'Sentimiento': sent, 'Link': item.link, 'Score': score,
                    'Etiqueta': etiqueta, 'Lat': lat, 'Lon': lon, 'Lugar': lugar,
                    'Manual': False
                })
            except: pass
        progreso.progress(min((idx + 1) * step, 1.0))
            
    progreso.empty()
    return pd.DataFrame(resultados)

# --- 6. BARRA LATERAL (CONTROL TOTAL) ---
with st.sidebar:
    st.title("🎛️ MANDO CENTRAL")
    
    # SECCIÓN 1: INGRESO MANUAL (RECUPERADO)
    with st.expander("📝 Ingreso Manual de Datos"):
        with st.form("manual_form"):
            m_tit = st.text_input("Suceso / Comentario")
            m_src = st.text_input("Fuente (Radio, WhatsApp)", "Informante")
            m_lug = st.selectbox("Ubicación", list(GEO_DB.keys()) + ["Otro"])
            m_sent = st.selectbox("Sentimiento", ["Positivo", "Negativo", "Neutro"])
            m_target = st.text_input("Asignar a Objetivo (Nombre)", "General")
            
            if st.form_submit_button("💾 Guardar en Sistema"):
                coords = GEO_DB.get(m_lug, [-29.9027, -71.2519])
                new_row = {
                    'Fecha': datetime.now().date(), 'Fuente': m_src, 'Titular': m_tit,
                    'Sentimiento': m_sent, 'Link': '#', 'Score': 0, 'Etiqueta': m_target,
                    'Lat': coords[0], 'Lon': coords[1], 'Lugar': m_lug.title(), 'Manual': True
                }
                st.session_state.data_master = pd.concat([st.session_state.data_master, pd.DataFrame([new_row])], ignore_index=True)
                st.success("Dato Agregado Exitosamente")

    st.markdown("---")
    
    # SECCIÓN 2: ESTRATEGIA
    st.header("🔍 Configuración de Búsqueda")
    modo = st.radio("Modo Operativo", ["Análisis Individual", "Versus (Comparativa)"])
    
    if modo == "Análisis Individual":
        obj_a = st.text_input("Objetivo Principal", "Daniela Norambuena")
        obj_b = None
    else:
        c1, c2 = st.columns(2)
        obj_a = c1.text_input("Objetivo A", "Daniela Norambuena")
        obj_b = c2.text_input("Objetivo B", "Roberto Jacob")
        
    extra_keywords = st.text_input("Palabras Clave Extra", placeholder="Ej: Festival, Encuesta, Delincuencia")
    
    st.markdown("---")
    fuente_tipo = st.selectbox("Filtro de Fuente", ["Todo Internet", "Solo Prensa", "Redes Sociales"])
    sitios_prio = st.text_area("Sitios Prioritarios", "elobservatodo.cl, miradiols.cl, biobiochile.cl, eldia.cl")
    
    fechas = st.columns(2)
    f_inicio = fechas[0].date_input("Desde", datetime.now() - timedelta(days=14))
    f_fin = fechas[1].date_input("Hasta", datetime.now())
    
    btn_run = st.button("🚀 EJECUTAR ESCANEO TITAN", type="primary")

# --- 7. LÓGICA DE EJECUCIÓN ---
if btn_run:
    st.session_state.data_master = pd.DataFrame() # Limpiar anterior
    
    # Escaneo A
    with st.status(f"Rastreando a {obj_a}...") as status:
        df_a = ejecutar_escaneo_profundo(obj_a, obj_a, fuente_tipo, f_inicio, f_fin, extra_keywords, sitios_prio)
        st.session_state.data_master = pd.concat([st.session_state.data_master, df_a], ignore_index=True)
        status.update(label=f"Datos de {obj_a} cargados.", state="complete")
        
    # Escaneo B (Solo Versus)
    if modo == "Versus (Comparativa)" and obj_b:
        with st.status(f"Rastreando a {obj_b}...") as status:
            df_b = ejecutar_escaneo_profundo(obj_b, obj_b, fuente_tipo, f_inicio, f_fin, extra_keywords, sitios_prio)
            st.session_state.data_master = pd.concat([st.session_state.data_master, df_b], ignore_index=True)
            status.update(label=f"Datos de {obj_b} cargados.", state="complete")

# --- 8. VISUALIZACIÓN DE RESULTADOS ---
df = st.session_state.data_master

if not df.empty:
    st.title("📡 SENTINEL AI: DASHBOARD")
    
    # TABS PARA ORGANIZACIÓN LIMPIA
    tab_dash, tab_map, tab_cloud, tab_data = st.tabs(["📊 Estadísticas", "🗺️ Mapa Táctico", "☁️ Semántica", "📝 Datos Brutos"])
    
    # === TAB 1: DASHBOARD ===
    with tab_dash:
        if modo == "Versus (Comparativa)":
            st.subheader("⚔️ Arena de Comparación")
            
            # Gráfico de Barras Comparativo
            chart_vs = alt.Chart(df).mark_bar().encode(
                x=alt.X('Etiqueta', title=None),
                y='count()',
                color=alt.Color('Etiqueta', scale=alt.Scale(scheme='category10')),
                column='Sentimiento'
            ).properties(width=150, height=300)
            st.altair_chart(chart_vs)
            
            # Tabla Pivote
            st.markdown("##### Detalles Numéricos")
            pivot = df.groupby(['Etiqueta', 'Sentimiento']).size().unstack().fillna(0)
            st.dataframe(pivot, use_container_width=True)
            
        else: # Individual
            st.subheader(f"Informe: {obj_a}")
            k1, k2, k3 = st.columns(3)
            k1.metric("Volumen", len(df))
            k2.metric("Positivos", len(df[df.Sentimiento=='Positivo']), delta="🟢")
            k3.metric("Negativos", len(df[df.Sentimiento=='Negativo']), delta="-🔴", delta_color="inverse")
            
            # Gráfico de Línea Temporal
            line_c = alt.Chart(df).mark_line(point=True).encode(
                x='Fecha', y='count()', color='Sentimiento', tooltip=['Fecha', 'count()']
            ).interactive()
            st.altair_chart(line_c, use_container_width=True)
            
    # === TAB 2: MAPA TÁCTICO (GEO-INT) ===
    with tab_map:
        st.subheader("📍 Mapa de Calor Regional")
        m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
        
        # Capa de Calor
        HeatMap([[r['Lat'], r['Lon']] for i, r in df.iterrows()], radius=15).add_to(m)
        
        # Clusters de Marcadores
        mc = MarkerCluster().add_to(m)
        for i, r in df.iterrows():
            color = "green" if r['Sentimiento']=='Positivo' else "red" if r['Sentimiento']=='Negativo' else "orange"
            folium.Marker(
                [r['Lat'], r['Lon']], 
                popup=f"[{r['Etiqueta']}] {r['Titular']}", 
                icon=folium.Icon(color=color)
            ).add_to(mc)
            
        st_folium(m, width="100%", height=500)
        
    # === TAB 3: NUBE DE PALABRAS ===
    with tab_cloud:
        c_cloud, c_top = st.columns([2, 1])
        with c_cloud:
            st.markdown("##### Temas Recurrentes")
            text = " ".join(df['Titular'])
            if text:
                wc = WordCloud(width=800, height=400, background_color='#0f2027', colormap='rainbow').generate(text)
                fig, ax = plt.subplots()
                ax.imshow(wc, interpolation='bilinear')
                ax.axis("off")
                fig.patch.set_facecolor('#0f2027')
                st.pyplot(fig)
        with c_top:
            st.markdown("##### Top Fuentes")
            st.dataframe(df['Fuente'].value_counts().head(10), use_container_width=True)
            
    # === TAB 4: DATOS Y PDF ===
    with tab_data:
        st.markdown("##### 📝 Registro Detallado")
        
        # Editor de Datos
        edited_df = st.data_editor(
            df,
            column_config={
                "Link": st.column_config.LinkColumn("Fuente Original"),
                "Lat": None, "Lon": None, "Manual": None, "Score": None
            },
            use_container_width=True,
            num_rows="dynamic"
        )
        
        st.divider()
        
        # Generador de PDF
        if st.button("📄 Generar Reporte PDF Oficial"):
            class PDF(FPDF):
                def header(self):
                    self.set_font('Arial', 'B', 14); self.cell(0, 10, 'SENTINEL AI - REPORTE DE INTELIGENCIA', 0, 1, 'C'); self.ln(5)
            
            pdf = PDF(); pdf.add_page(); pdf.set_font("Arial", size=10)
            pdf.cell(0, 10, f"Fecha: {datetime.now().date()} | Modo: {modo}", 0, 1)
            pdf.ln(5)
            
            for i, row in edited_df.iterrows():
                try:
                    txt = f"[{row['Etiqueta']}] ({row['Sentimiento']}) {row['Titular']}"
                    txt = txt.encode('latin-1', 'replace').decode('latin-1')
                    pdf.multi_cell(0, 5, txt); pdf.ln(1)
                except: pass
                
            t = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            pdf.output(t.name)
            with open(t.name, "rb") as f:
                st.download_button("⬇️ Descargar PDF", f, "Sentinel_Reporte_Titan.pdf")

else:
    st.info("👋 Sistema en espera. Configure los parámetros en el Mando Central (Barra Lateral).")
