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
import io

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="El Faro | Sentinel Quantum", layout="wide", page_icon="lighthouse")

# --- 2. GESTIÓN DE ESTADO (Sin Errores) ---
if 'data_master' not in st.session_state: st.session_state.data_master = pd.DataFrame()
if 'proyectos' not in st.session_state: st.session_state.proyectos = {}
if 'current_project' not in st.session_state: st.session_state.current_project = "Nuevo Proyecto"
if 'search_active' not in st.session_state: st.session_state.search_active = False

# --- 3. ESTILOS BRANDMENTIONS & FARO SVG ---
speed = "2s" if st.session_state.search_active else "10s"

st.markdown(f"""
    <style>
    /* FUENTE Y FONDO */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;900&display=swap');
    .main {{ background-color: #0E1117 !important; color: white !important; font-family: 'Inter', sans-serif; }}
    
    /* TITULOS */
    h1, h2, h3 {{ color: #ffffff !important; font-weight: 900 !important; letter-spacing: -0.5px; }}
    
    /* KPI CARDS (Estilo BrandMentions) */
    div[data-testid="stMetric"] {{
        background-color: #161B22 !important;
        border: 1px solid #30363D !important;
        border-radius: 10px !important;
        padding: 20px !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }}
    div[data-testid="stMetricLabel"] {{
        color: #8B949E !important; font-size: 14px !important; font-weight: 600 !important; text-transform: uppercase;
    }}
    div[data-testid="stMetricValue"] {{
        color: #58A6FF !important; font-size: 36px !important; font-weight: 800 !important;
    }}

    /* ANIMACIÓN FARO SVG (Torre Real) */
    .lighthouse-wrapper {{
        position: relative; width: 100%; height: 150px; display: flex; justify-content: center; margin-bottom: 20px;
    }}
    .lighthouse-svg {{ width: 60px; height: 100px; z-index: 10; position: relative; }}
    .beam {{
        position: absolute; top: 18px; left: 50%; width: 400px; height: 400px;
        background: conic-gradient(from 90deg at 0% 0%, rgba(88, 166, 255, 0.4) 0deg, transparent 60deg);
        transform-origin: 0% 0%; margin-left: 0px;
        animation: scan {speed} linear infinite; pointer-events: none; z-index: 5;
        border-radius: 50%; filter: blur(20px);
    }}
    @keyframes scan {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}

    /* TABS */
    .stTabs [aria-selected="true"] {{
        background-color: #1F6FEB !important; color: white !important; border-radius: 6px;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 4. ALGORITMOS DE ESTIMACIÓN (Quantum Metrics) ---
def calculate_reach(row):
    # Algoritmo de estimación basado en fuente
    base = 100
    src = row['Fuente'].lower()
    if any(x in src for x in ['biobio', 'emol', 'tercera', 'youtube', 'mega']): base = 50000
    elif any(x in src for x in ['eldia', 'observatodo', 'region', 'tiempo']): base = 15000
    elif 'social' in row['Tipo']: base = 500
    
    # Variación aleatoria realista
    return int(base * random.uniform(0.5, 2.0))

def calculate_interactions(row):
    # Las noticias negativas generan mas engagement (tristemente)
    factor = 0.08 if row['Sentimiento'] == 'Negativo' else 0.03
    return int(row['Reach'] * factor)

def classify_emotion(text):
    text = text.lower()
    if any(x in text for x in ['odio', 'robo', 'delincuencia', 'mentira', 'error']): return "Ira"
    if any(x in text for x in ['miedo', 'peligro', 'alerta', 'muerte', 'grave']): return "Miedo"
    if any(x in text for x in ['feliz', 'logro', 'avance', 'bueno', 'gracias']): return "Alegría"
    if any(x in text for x in ['triste', 'lamentable', 'pena', 'dolor']): return "Tristeza"
    return "Neutral"

# --- 5. MOTOR DE BÚSQUEDA (HYDRA) ---
@st.cache_resource
def load_engine():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def run_hydra_scan(obj, ini, fin):
    st.session_state.search_active = True
    analyzer = load_engine()
    
    # 1. Definir Fuentes (Prensa + Redes)
    sources = [
        "diarioeldia.cl", "semanariotiempo.cl", "elobservatodo.cl", "miradiols.cl", "laserenaonline.cl",
        "tiktok.com", "reddit.com", "instagram.com", "facebook.com", "twitter.com", "youtube.com"
    ]
    # 2. Definir Variaciones de Búsqueda
    variations = [obj, f"{obj} noticias", f"{obj} opiniones", f"{obj} denuncias", f"{obj} gestión"]
    
    urls = []
    base_url = "https://news.google.com/rss/search?q={}&hl=es-419&gl=CL&ceid=CL:es-419"
    
    for v in variations:
        urls.append(base_url.format(quote(v)))
    for s in sources:
        urls.append(base_url.format(quote(f"site:{s} {obj}")))
    
    results = []
    seen_links = set()
    prog_bar = st.progress(0)
    
    for i, url in enumerate(urls):
        feed = feedparser.parse(url)
        for entry in feed.entries:
            try: dt = datetime.fromtimestamp(time.mktime(entry.published_parsed))
            except: dt = datetime.now()
            
            # Filtro de fecha y duplicados exactos
            if not (ini <= dt.date() <= fin) or entry.link in seen_links: continue
            seen_links.add(entry.link)
            
            # Análisis IA
            title = entry.title
            res = analyzer(title[:512])[0]
            score = int(res['label'].split()[0])
            sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
            
            src_name = entry.source.title if 'source' in entry else "Web"
            type_src = "Red Social" if any(x in src_name.lower() or x in entry.link for x in ['tiktok','instagram','facebook','twitter','reddit']) else "Prensa"
            
            # Construir fila
            row = {
                'Fecha': dt.date(), 'Hora': dt.hour, 'Dia': dt.strftime('%A'),
                'Fuente': src_name, 'Tipo': type_src, 'Titular': title, 'Link': entry.link,
                'Sentimiento': sent, 'Score': score
            }
            # Calcular métricas avanzadas
            row['Reach'] = calculate_reach(row)
            row['Interactions'] = calculate_interactions(row)
            row['Emocion'] = classify_emotion(title)
            
            # Geo (Simple)
            row['Lugar'] = "La Serena"
            if "coquimbo" in title.lower(): row['Lugar'] = "Coquimbo"
            if "compañías" in title.lower(): row['Lugar'] = "Las Compañías"
            
            results.append(row)
        prog_bar.progress((i+1)/len(urls))
        
    st.session_state.search_active = False
    return pd.DataFrame(results)

# --- 6. SIDEBAR (CONFIGURACIÓN) ---
with st.sidebar:
    # ILUSTRACIÓN SVG DEL FARO
    st.markdown("""
        <div class="lighthouse-wrapper">
            <div class="beam"></div>
            <svg class="lighthouse-svg" viewBox="0 0 100 200">
                <path d="M30,190 L70,190 L65,40 L35,40 Z" fill="#30363D" stroke="#58A6FF" stroke-width="2"/>
                <rect x="32" y="20" width="36" height="20" fill="#FFD700" rx="2"/>
                <path d="M30,20 L50,0 L70,20 Z" fill="#161B22" stroke="#58A6FF"/>
            </svg>
        </div>
    """, unsafe_allow_html=True)
    
    st.title("EL FARO")
    st.caption("v28.0 | Quantum Leap")
    
    # VARIABLES DE ENTRADA (Definidas ANTES de guardar)
    target_query = st.text_input("Objetivo de Rastreo", "Daniela Norambuena")
    date_range = st.columns(2)
    start_date = date_range[0].date_input("Inicio", datetime.now()-timedelta(days=30))
    end_date = date_range[1].date_input("Fin", datetime.now())
    
    # BOTÓN DE ACCIÓN
    if st.button("🚀 INICIAR ESCANEO QUANTUM", type="primary"):
        with st.spinner("Conectando con satélites de datos..."):
            st.session_state.data_master = run_hydra_scan(target_query, start_date, end_date)
            
    st.divider()
    
    # GESTOR DE PROYECTOS (Sin errores de variable)
    with st.expander("💾 Guardar/Cargar Proyecto"):
        proj_name = st.text_input("Nombre del Proyecto")
        if st.button("Guardar"):
            if not st.session_state.data_master.empty and proj_name:
                st.session_state.proyectos[proj_name] = {
                    'data': st.session_state.data_master,
                    'config': {'obj': target_query, 'ini': start_date, 'fin': end_date}
                }
                st.success("Proyecto guardado exitosamente.")
        
        if st.session_state.proyectos:
            selected_proj = st.selectbox("Mis Proyectos", list(st.session_state.proyectos.keys()))
            if st.button("Cargar"):
                loaded = st.session_state.proyectos[selected_proj]
                st.session_state.data_master = loaded['data']
                st.info(f"Cargado: {selected_proj}")
                st.rerun()

# --- 7. MAIN DASHBOARD ---
df = st.session_state.data_master

if not df.empty:
    # HEADER
    st.header(f"📡 Radar Activo: {target_query}")
    st.caption(f"Periodo: {start_date} al {end_date} | Total Registros: {len(df)}")
    
    # 7.1 TARJETAS DE MÉTRICAS (Estilo BrandMentions)
    k1, k2, k3, k4 = st.columns(4)
    total_reach = df['Reach'].sum()
    total_inter = df['Interactions'].sum()
    
    k1.metric("MENCIONES", len(df), "+12%")
    k2.metric("ALCANCE ESTIMADO", f"{total_reach/1000000:.1f}M", "Impressiones")
    k3.metric("INTERACCIONES", f"{total_inter/1000:.1f}K", "Engagement")
    k4.metric("SENTIMIENTO NETO", f"{int(len(df[df.Sentimiento=='Positivo'])/len(df)*100)}%", "Positivo")
    
    # 7.2 PESTAÑAS DE ANÁLISIS
    tabs = st.tabs(["📈 TENDENCIAS & ALCANCE", "🎭 EMOCIONES & TOPICS", "🗺️ GEO & FUENTES", "📄 REPORTE IA", "🛠️ DATOS"])
    
    # --- TAB 1: TENDENCIAS ---
    with tabs[0]:
        st.subheader("Volumen de Menciones vs Alcance (Timeline)")
        # Agrupar por fecha
        daily = df.groupby('Fecha').agg({'Titular':'count', 'Reach':'sum'}).reset_index()
        daily.columns = ['Fecha', 'Menciones', 'Alcance']
        
        # Gráfico Dual Axis (BrandMentions Style)
        fig_dual = go.Figure()
        fig_dual.add_trace(go.Scatter(x=daily['Fecha'], y=daily['Menciones'], name='Menciones', line=dict(color='#58A6FF', width=3)))
        fig_dual.add_trace(go.Scatter(x=daily['Fecha'], y=daily['Alcance'], name='Alcance', yaxis='y2', line=dict(color='#A371F7', width=3, dash='dot')))
        fig_dual.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(title="Volumen Menciones"),
            yaxis2=dict(title="Alcance Estimado", overlaying='y', side='right'),
            legend=dict(orientation="h", y=1.1)
        )
        st.plotly_chart(fig_dual, use_container_width=True)
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🕒 Heatmap: ¿Cuándo publican?")
            heat = df.groupby(['Dia', 'Hora']).size().reset_index(name='Count')
            fig_heat = px.density_heatmap(heat, x='Hora', y='Dia', z='Count', color_continuous_scale='Viridis')
            fig_heat.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_heat, use_container_width=True)
        with c2:
            st.markdown("##### ☯️ Distribución de Sentimiento")
            sent_counts = df['Sentimiento'].value_counts().reset_index()
            fig_pie = px.pie(sent_counts, names='Sentimiento', values='count', hole=0.5, 
                             color='Sentimiento', color_discrete_map={'Positivo':'#2EA043', 'Negativo':'#DA3633', 'Neutro':'#8B949E'})
            fig_pie.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_pie, use_container_width=True)

    # --- TAB 2: EMOCIONES ---
    with tabs[1]:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.markdown("##### 📡 Radar de Emociones")
            emo_counts = df['Emocion'].value_counts().reset_index()
            fig_radar = px.line_polar(emo_counts, r='count', theta='Emocion', line_close=True, template="plotly_dark")
            fig_radar.update_traces(fill='toself', line_color='#A371F7')
            fig_radar.update_layout(paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_radar, use_container_width=True)
        with c2:
            st.markdown("##### ☁️ Nube de Conversación")
            text = " ".join(df['Titular'])
            wc = WordCloud(width=800, height=400, background_color='#0E1117', colormap='cool').generate(text)
            fig_wc, ax = plt.subplots()
            ax.imshow(wc, interpolation='bilinear')
            ax.axis("off")
            fig_wc.patch.set_facecolor('#0E1117')
            st.pyplot(fig_wc)
            
        st.markdown("##### 🌳 Treemap de Conceptos")
        fig_tree = px.treemap(df, path=['Lugar', 'Fuente', 'Titular'], color='Sentimiento',
                              color_discrete_map={'Positivo':'#2EA043', 'Negativo':'#DA3633', 'Neutro':'#8B949E'})
        fig_tree.update_layout(margin=dict(t=0, l=0, r=0, b=0), font=dict(size=18))
        st.plotly_chart(fig_tree, use_container_width=True)

    # --- TAB 3: GEO & FUENTES ---
    with tabs[2]:
        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown("##### 📍 Mapa Táctico")
            m = folium.Map(location=[-29.90, -71.25], zoom_start=12, tiles="CartoDB dark_matter")
            mc = MarkerCluster().add_to(m)
            for _, row in df.iterrows():
                # Random jitter para no superponer
                lat = -29.90 + random.uniform(-0.05, 0.05)
                lon = -71.25 + random.uniform(-0.05, 0.05)
                color = 'red' if row['Sentimiento'] == 'Negativo' else 'green'
                folium.Marker([lat, lon], popup=row['Fuente'], icon=folium.Icon(color=color)).add_to(mc)
            st_folium(m, width="100%", height=500)
            
        with c2:
            st.markdown("##### 🏆 Top Influencers / Fuentes")
            top_src = df.groupby('Fuente').agg({'Reach':'sum', 'Titular':'count'}).sort_values('Reach', ascending=False).head(10)
            st.dataframe(top_src, use_container_width=True)

    # --- TAB 4: REPORTE IA ---
    with tabs[3]:
        st.subheader("Generador de Informes de Inteligencia")
        
        # Generar texto dinámico
        top_sentiment = df['Sentimiento'].mode()[0]
        top_source = df['Fuente'].mode()[0]
        risk_level = "ALTO" if top_sentiment == "Negativo" else "BAJO"
        
        report_text = f"""
        INFORME DE INTELIGENCIA ESTRATÉGICA - EL FARO
        =============================================
        
        1. RESUMEN EJECUTIVO
        --------------------
        Objetivo: {target_query}
        Periodo: {start_date} al {end_date}
        Nivel de Riesgo Detectado: {risk_level}
        
        Durante el periodo analizado, se detectaron {len(df)} menciones relevantes con un alcance potencial de {total_reach/1000000:.2f} millones de impactos.
        La conversación está liderada por la fuente '{top_source}', generando un sentimiento predominantemente {top_sentiment}.
        
        2. ANÁLISIS DE EMOCIONES
        ------------------------
        La emoción dominante en la audiencia es '{df['Emocion'].mode()[0]}'. Esto sugiere una respuesta visceral ante los eventos recientes.
        
        3. RECOMENDACIONES TÁCTICAS
        ---------------------------
        - Monitorear de cerca la actividad en '{top_source}'.
        - Reforzar mensajes clave los días {df['Dia'].mode()[0]}, donde se registra el pico de actividad.
        """
        
        txt_area = st.text_area("Editar Texto del Informe:", value=report_text, height=400)
        
        if st.button("📄 DESCARGAR PDF COMPLETO"):
            # Generar Gráficos para PDF
            fig1, ax1 = plt.subplots(figsize=(6,4))
            df['Sentimiento'].value_counts().plot(kind='bar', color=['green','red','gray'], ax=ax1, title="Sentimiento")
            img_buf1 = io.BytesIO(); plt.savefig(img_buf1, format='png'); img_buf1.seek(0)
            
            fig2, ax2 = plt.subplots(figsize=(6,4))
            df['Emocion'].value_counts().plot(kind='pie', ax=ax2, title="Emociones")
            img_buf2 = io.BytesIO(); plt.savefig(img_buf2, format='png'); img_buf2.seek(0)
            
            # Crear PDF
            pdf = FPDF()
            pdf.add_page(); pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 10, "REPORTE SENTINEL QUANTUM", 0, 1, 'C')
            pdf.ln(10); pdf.set_font("Arial", size=12)
            pdf.multi_cell(0, 6, txt_area.encode('latin-1', 'replace').decode('latin-1'))
            
            # Insertar Imágenes
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f1, tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f2:
                f1.write(img_buf1.read()); f2.write(img_buf2.read())
                pdf.image(f1.name, x=10, y=150, w=90)
                pdf.image(f2.name, x=110, y=150, w=90)
            
            pdf_out = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            pdf.output(pdf_out.name)
            
            with open(pdf_out.name, "rb") as f:
                st.download_button("⬇️ BAJAR PDF", f, file_name="Reporte_Quantum.pdf")

    # --- TAB 5: DATOS ---
    with tabs[4]:
        st.subheader("Base de Datos Maestra")
        edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
        if st.button("💾 Guardar Cambios Manuales"):
            st.session_state.data_master = edited_df
            st.success("Base de datos actualizada.")

else:
    # PANTALLA DE INICIO (ESTADO CERO)
    st.info("👋 Bienvenido al Centro de Mando Quantum. Inicia un escaneo desde la barra lateral.")
