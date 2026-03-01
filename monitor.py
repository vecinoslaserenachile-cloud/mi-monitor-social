import streamlit as st
import feedparser
import pandas as pd
from transformers import pipeline
from datetime import datetime, timedelta
import time
import plotly.express as px  # <--- VUELVE PLOTLY (Gráficos interactivos)
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
    page_title="Sentinel AI: Ultimate", 
    layout="wide", 
    page_icon="📡",
    initial_sidebar_state="expanded"
)

# --- 2. ESTILOS VISUALES (PREMIUM DARK) ---
st.markdown("""
    <style>
    .main { background: linear-gradient(160deg, #0e1117, #1a202c); }
    h1 { background: -webkit-linear-gradient(#00f260, #0575e6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    
    /* Métricas con efecto cristal */
    div[data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 15px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2);
    }
    
    /* Botones Neón */
    .stButton>button {
        background: linear-gradient(90deg, #0575e6 0%, #00f260 100%);
        color: white; border: none; padding: 12px 24px;
        border-radius: 50px; font-weight: bold; width: 100%;
        box-shadow: 0 0 20px rgba(5, 117, 230, 0.4);
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. MEMORIA ---
if 'data_final' not in st.session_state:
    st.session_state.data_final = pd.DataFrame(columns=['Fecha', 'Fuente', 'Titular', 'Sentimiento', 'Link', 'Score', 'Etiqueta', 'Lat', 'Lon', 'Lugar', 'Manual'])

# --- 4. BASE GEO (RECUPERADA) ---
GEO_DB = {
    "avenida del mar": [-29.9168, -71.2785], "faro": [-29.9073, -71.2847], "centro": [-29.9027, -71.2519],
    "plaza de armas": [-29.9027, -71.2519], "las compañías": [-29.8783, -71.2389], "tierras blancas": [-29.9392, -71.2294],
    "coquimbo": [-29.9533, -71.3436], "ovalle": [-30.6015, -71.2003], "vicuña": [-30.0319, -70.7081],
    "aeropuerto": [-29.9161, -71.1994], "la florida": [-29.9238, -71.2185]
}

# --- 5. MOTOR DE BÚSQUEDA AMPLIFICADO ---
@st.cache_resource
def cargar_modelo():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def detectar_ubicacion(texto):
    texto = texto.lower()
    for lugar, coords in GEO_DB.items():
        if lugar in texto: return coords[0], coords[1], lugar.title()
    return -29.9027 + random.uniform(-0.04, 0.04), -71.2519 + random.uniform(-0.04, 0.04), "La Serena"

def construir_urls_masivas(objetivo, tipo, extra):
    # ESTRATEGIA: Generar muchas variaciones para que Google suelte más resultados
    queries = [objetivo]
    
    # 1. Desglose del nombre (Ej: Daniela Norambuena -> Daniela Norambuena, Norambuena La Serena)
    parts = objetivo.split()
    if len(parts) > 1:
        queries.append(f"{parts[-1]} La Serena") # Apellido + Ciudad
        queries.append(f"{objetivo} Coquimbo")
        
    # 2. Contexto
    queries.append(f"{objetivo} noticias")
    
    # 3. Extras del usuario
    if extra:
        for k in extra.split(","):
            queries.append(f"{objetivo} {k.strip()}")
            
    urls = []
    base = "https://news.google.com/rss/search?q={}&hl=es-419&gl=CL&ceid=CL:es-419"
    
    for q in queries:
        q_enc = quote(q)
        # Filtros de sitio
        if tipo == "Redes Sociales":
            q_enc += quote(" site:twitter.com OR site:facebook.com OR site:instagram.com OR site:tiktok.com")
        elif tipo == "Solo Prensa":
            q_enc += quote(" when:30d") # Ampliado a 30 días para traer más volumen
            
        urls.append(base.format(q_enc))
        
    return list(set(urls))

def escanear(objetivo, etiqueta, tipo, inicio, fin, extra):
    analizador = cargar_modelo()
    urls = construir_urls_masivas(objetivo, tipo, extra)
    resultados = []
    vistos = set()
    
    progreso = st.progress(0)
    
    for idx, url in enumerate(urls):
        feed = feedparser.parse(url)
        for item in feed.entries:
            try:
                # Filtrado Fechas
                fecha = datetime.fromtimestamp(time.mktime(item.published_parsed)).date()
            except: fecha = datetime.now().date()
            
            if not (inicio <= fecha <= fin): continue
            if item.link in vistos: continue
            vistos.add(item.link)
            
            try:
                # IA
                pred = analizador(item.title[:512])[0]
                score = int(pred['label'].split()[0])
                sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
                fuente = item.source.title if 'source' in item else "Web"
                
                # Geo
                lat, lon, lugar = detectar_ubicacion(item.title)
                
                resultados.append({
                    'Fecha': fecha, 'Fuente': fuente, 'Titular': item.title,
                    'Sentimiento': sent, 'Link': item.link, 'Score': score,
                    'Etiqueta': etiqueta, 'Lat': lat, 'Lon': lon, 'Lugar': lugar, 'Manual': False
                })
            except: pass
        progreso.progress((idx + 1) / len(urls))
            
    progreso.empty()
    return pd.DataFrame(resultados)

# --- 6. INTERFAZ ---
with st.sidebar:
    st.header("🎛️ Centro de Control")
    modo = st.radio("Modo", ["Individual", "Versus (Comparativa)"])
    
    if modo == "Individual":
        obj1 = st.text_input("Objetivo", "Daniela Norambuena")
        obj2 = None
    else:
        c1, c2 = st.columns(2)
        obj1 = c1.text_input("Candidato A", "Daniela Norambuena")
        obj2 = c2.text_input("Candidato B", "Roberto Jacob")
        
    extra = st.text_input("Palabras Clave Extra", placeholder="Ej: seguridad, festival, obras")
    
    st.markdown("---")
    tipo = st.selectbox("Fuentes", ["Todo Internet", "Solo Prensa", "Redes Sociales"])
    rango = st.date_input("Rango Fechas", [datetime.now()-timedelta(days=14), datetime.now()])
    
    # MANUAL ENTRY
    with st.expander("📝 Ingreso Manual"):
        with st.form("manual"):
            m_txt = st.text_input("Dato")
            m_src = st.text_input("Fuente")
            m_sen = st.selectbox("Sentimiento", ["Positivo", "Negativo"])
            if st.form_submit_button("Guardar"):
                new = {'Fecha': datetime.now().date(), 'Fuente': m_src, 'Titular': m_txt, 'Sentimiento': m_sen, 'Link':'#', 'Score':0, 'Etiqueta': 'Manual', 'Lat':-29.90, 'Lon':-71.25, 'Lugar':'Manual', 'Manual':True}
                st.session_state.data_final = pd.concat([st.session_state.data_final, pd.DataFrame([new])], ignore_index=True)
                st.success("Guardado")

    if st.button("🚀 EJECUTAR BÚSQUEDA TOTAL"):
        st.session_state.data_final = pd.DataFrame()
        with st.spinner("Triangulando información en la red..."):
            df1 = escanear(obj1, obj1, tipo, rango[0], rango[1], extra)
            st.session_state.data_final = pd.concat([st.session_state.data_final, df1], ignore_index=True)
            
            if modo == "Versus (Comparativa)" and obj2:
                df2 = escanear(obj2, obj2, tipo, rango[0], rango[1], extra)
                st.session_state.data_final = pd.concat([st.session_state.data_final, df2], ignore_index=True)

# --- 7. DASHBOARD VISUAL (RECUPERADO) ---
df = st.session_state.data_final

if not df.empty:
    st.title("📡 SENTINEL AI: DASHBOARD")
    
    # KPIs SUPERIORES
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Volumen Total", len(df))
    k2.metric("Positivos", len(df[df.Sentimiento=='Positivo']), delta="🟢")
    k3.metric("Negativos", len(df[df.Sentimiento=='Negativo']), delta="-🔴", delta_color="inverse")
    k4.metric("Fuentes", df['Fuente'].nunique())
    
    st.divider()
    
    # === SECCIÓN 1: VISUALIZACIONES AVANZADAS ===
    col_sun, col_gauge = st.columns([2, 1])
    
    with col_sun:
        st.subheader("🕸️ Mapa Conceptual Interactivo (Sunburst)")
        st.caption("Haz clic en el centro para expandir: Sentimiento -> Fuente -> Noticia")
        # EL GRÁFICO QUE TE GUSTABA: SUNBURST
        fig_sun = px.sunburst(
            df, 
            path=['Etiqueta', 'Sentimiento', 'Fuente'], 
            color='Sentimiento',
            color_discrete_map={'Positivo':'#00f260', 'Negativo':'#eb3b5a', 'Neutro':'#f7b731'},
            height=500
        )
        st.plotly_chart(fig_sun, use_container_width=True)
        
    with col_gauge:
        st.subheader("🚦 Salud de Marca")
        # EL VELOCÍMETRO
        pos = len(df[df.Sentimiento=='Positivo'])
        neg = len(df[df.Sentimiento=='Negativo'])
        total = len(df)
        score = ((pos * 100) + (total - neg - pos) * 50) / total if total > 0 else 0
        
        fig_g = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = score,
            gauge = {
                'axis': {'range': [None, 100]},
                'bar': {'color': "rgba(0,0,0,0)"},
                'steps': [
                    {'range': [0, 40], 'color': "#eb3b5a"},
                    {'range': [40, 70], 'color': "#f7b731"},
                    {'range': [70, 100], 'color': "#00f260"}],
                'threshold': {'line': {'color': "white", 'width': 4}, 'thickness': 0.75, 'value': score}
            }
        ))
        fig_g.update_layout(paper_bgcolor="rgba(0,0,0,0)", font={'color': "white"})
        st.plotly_chart(fig_g, use_container_width=True)
        
        # Ranking de Influenciadores
        st.markdown("##### 🏆 Top Medios")
        top_media = df['Fuente'].value_counts().head(5).reset_index()
        top_media.columns = ['Medio', 'Notas']
        fig_bar = px.bar(top_media, x='Notas', y='Medio', orientation='h', color='Notas', color_continuous_scale='Bluyl')
        fig_bar.update_layout(paper_bgcolor="rgba(0,0,0,0)", font={'color': "white"}, height=200)
        st.plotly_chart(fig_bar, use_container_width=True)

    # === SECCIÓN 2: MAPA Y NUBE ===
    st.divider()
    tabs = st.tabs(["🗺️ Mapa Táctico", "☁️ Semántica", "⚔️ Comparativa (Barras)", "📝 Datos"])
    
    with tabs[0]:
        m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
        HeatMap([[r['Lat'], r['Lon']] for i, r in df.iterrows()], radius=15).add_to(m)
        mc = MarkerCluster().add_to(m)
        for i, r in df.iterrows():
            folium.Marker([r['Lat'], r['Lon']], popup=r['Titular'], icon=folium.Icon(color="green" if r['Sentimiento']=='Positivo' else "red")).add_to(mc)
        st_folium(m, width="100%", height=500)
        
    with tabs[1]:
        wc = WordCloud(width=800, height=300, background_color='#0e1117', colormap='rainbow').generate(" ".join(df['Titular']))
        fig, ax = plt.subplots(); ax.imshow(wc); ax.axis("off"); fig.patch.set_facecolor('#0e1117')
        st.pyplot(fig)
        
    with tabs[2]:
        if modo == "Versus (Comparativa)":
            fig_comp = px.bar(df, x="Etiqueta", color="Sentimiento", barmode="group", 
                              color_discrete_map={'Positivo':'#00f260', 'Negativo':'#eb3b5a', 'Neutro':'#f7b731'})
            st.plotly_chart(fig_comp, use_container_width=True)
        else:
            st.info("Activa el modo Comparativa para ver este gráfico.")
            
    with tabs[3]:
        st.dataframe(df, use_container_width=True)
        if st.button("📄 PDF"):
            pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", size=10)
            for i, r in df.iterrows():
                try: pdf.multi_cell(0, 5, f"[{r['Etiqueta']}] {r['Titular']}".encode('latin-1','replace').decode('latin-1')); pdf.ln(1)
                except: pass
            t = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); pdf.output(t.name)
            with open(t.name, "rb") as f: st.download_button("Descargar", f, "reporte.pdf")

else:
    st.info("👋 Inicia el escaneo desde la barra lateral. (La búsqueda ampliada puede tardar unos segundos).")
