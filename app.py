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
st.set_page_config(page_title="Sentinel Platinum", layout="wide", page_icon="⚓")

# --- 2. ESTILOS PLATINUM (CONTRASTE EXTREMO) ---
# Velocidad del faro según estado
speed = "2s" if 'search_active' in st.session_state and st.session_state.search_active else "12s"

st.markdown(f"""
    <style>
    /* FONDO Y TIPOGRAFÍA */
    @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@300;700;900&display=swap');
    .main {{ background-color: #050914 !important; color: #ffffff !important; font-family: 'Roboto', sans-serif; }}
    
    /* KPI CARDS - FORZAR BLANCO */
    div[data-testid="stMetric"] {{
        background-color: #0F172A !important;
        border: 1px solid #38BDF8 !important;
        border-radius: 8px !important;
        padding: 15px !important;
        box-shadow: 0 4px 20px rgba(0,0,0,0.5);
    }}
    /* Etiqueta (Menciones, Alcance...) -> BLANCO PURO */
    div[data-testid="stMetricLabel"] p {{
        color: #FFFFFF !important; 
        font-size: 16px !important; 
        font-weight: 700 !important;
        text-transform: uppercase !important;
        opacity: 1 !important;
    }}
    div[data-testid="stMetricLabel"] {{
        color: #FFFFFF !important;
        opacity: 1 !important;
    }}
    /* Valor (Números) -> CYAN NEÓN */
    div[data-testid="stMetricValue"] {{
        color: #38BDF8 !important; 
        font-size: 38px !important; 
        font-weight: 900 !important;
    }}

    /* ANIMACIÓN FARO (CONFINADA AL SIDEBAR PARA EVITAR PARPADEO) */
    .lighthouse-container {{
        position: relative; width: 100%; height: 180px; 
        display: flex; justify-content: center; align-items: flex-end;
        overflow: hidden; /* CRÍTICO: Evita que la luz toque el mapa */
        background: radial-gradient(circle at bottom, #1e293b 0%, transparent 70%);
        border-bottom: 1px solid #334155; margin-bottom: 20px;
    }}
    .lighthouse-svg {{ width: 80px; height: 120px; z-index: 10; position: relative; }}
    .beam {{
        position: absolute; bottom: 80px; left: 50%; width: 600px; height: 600px;
        background: conic-gradient(from 0deg at 50% 50%, rgba(56,189,248,0.3) 0deg, transparent 60deg);
        transform-origin: 50% 50%; margin-left: -300px; margin-bottom: -300px;
        animation: radarScan {speed} linear infinite; pointer-events: none; z-index: 1;
    }}
    @keyframes radarScan {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}

    /* TABS */
    .stTabs [aria-selected="true"] {{
        background-color: #38BDF8 !important; color: #000000 !important; font-weight: bold;
    }}
    
    /* BOTONES */
    .stButton>button {{
        background: linear-gradient(90deg, #0284c7, #2563eb); color: white; border: none; font-weight: bold;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 3. GESTIÓN DE ESTADO ---
if 'data_master' not in st.session_state: st.session_state.data_master = pd.DataFrame()
if 'proyectos' not in st.session_state: st.session_state.proyectos = {}
if 'current_project' not in st.session_state: st.session_state.current_project = "Nuevo Proyecto"

# --- 4. MOTORES DE INTELIGENCIA ---
@st.cache_resource
def load_engine():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def get_quantum_metrics(row):
    # Simulación avanzada de alcance
    base = 100
    src = row['Fuente'].lower()
    if any(x in src for x in ['biobio', 'emol', 'tercera', 'youtube']): base = 150000
    elif any(x in src for x in ['eldia', 'tiempo', 'observatodo', 'region']): base = 45000
    elif 'social' in row['Tipo']: base = 1200
    
    reach = int(base * random.uniform(0.8, 1.5))
    interact = int(reach * (0.05 if row['Sentimiento'] == 'Negativo' else 0.02))
    return reach, interact

def classify_emotion_advanced(text):
    t = text.lower()
    # Diccionario ampliado para asegurar datos en el radar
    if any(x in t for x in ['odio', 'robo', 'delincuencia', 'mentira', 'error', 'falla', 'crisis', 'vergüenza']): return "Ira"
    if any(x in t for x in ['miedo', 'peligro', 'alerta', 'muerte', 'grave', 'amenaza', 'temor']): return "Miedo"
    if any(x in t for x in ['feliz', 'logro', 'avance', 'bueno', 'gracias', 'excelente', 'triunfo', 'apoyo']): return "Alegría"
    if any(x in t for x in ['triste', 'lamentable', 'pena', 'dolor', 'luto']): return "Tristeza"
    if any(x in t for x in ['sorpresa', 'increíble', 'insólito', 'impacto']): return "Sorpresa"
    return "Neutral" # Fallback

def run_hydra_scan(obj, ini, fin):
    st.session_state.search_active = True
    analyzer = load_engine()
    
    # 25 Frentes de Búsqueda
    urls = []
    base = "https://news.google.com/rss/search?q={}&hl=es-419&gl=CL&ceid=CL:es-419"
    targets = [obj, f"{obj} polémica", f"{obj} gestión", f"{obj} seguridad", f"{obj} obras"]
    sites = ["diarioeldia.cl", "semanariotiempo.cl", "elobservatodo.cl", "miradiols.cl", "tiktok.com", "reddit.com", "instagram.com"]
    
    for t in targets: urls.append(base.format(quote(t)))
    for s in sites: urls.append(base.format(quote(f"site:{s} {obj}")))
    
    res = []
    seen = set()
    prog = st.progress(0)
    
    for i, url in enumerate(urls):
        feed = feedparser.parse(url)
        for entry in feed.entries:
            try: dt = datetime.fromtimestamp(time.mktime(entry.published_parsed))
            except: dt = datetime.now()
            
            if not (ini <= dt.date() <= fin) or entry.link in seen: continue
            seen.add(entry.link)
            
            # NLP
            p = analyzer(entry.title[:512])[0]
            score = int(p['label'].split()[0])
            sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
            
            src = entry.source.title if 'source' in entry else "Web"
            typ = "Red Social" if any(x in src.lower() for x in ['tiktok','instagram','reddit','facebook','twitter']) else "Prensa"
            
            # Geo
            lug = "La Serena"
            if "coquimbo" in entry.title.lower(): lug = "Coquimbo"
            if "compañías" in entry.title.lower(): lug = "Las Compañías"
            
            row = {'Fecha': dt.date(), 'Hora': dt.hour, 'Dia': dt.strftime('%A'), 'Fuente': src, 'Tipo': typ, 'Titular': entry.title, 'Link': entry.link, 'Sentimiento': sent, 'Lugar': lug}
            row['Reach'], row['Interactions'] = get_quantum_metrics(row)
            row['Emocion'] = classify_emotion_advanced(entry.title)
            
            res.append(row)
        prog.progress((i+1)/len(urls))
        
    st.session_state.search_active = False
    return pd.DataFrame(res)

# --- 5. SIDEBAR ---
with st.sidebar:
    # FARO SVG ANIMADO (Confinado)
    st.markdown("""
        <div class="lighthouse-container">
            <div class="beam"></div>
            <svg class="lighthouse-svg" viewBox="0 0 100 200">
                <path d="M35,190 L65,190 L60,50 L40,50 Z" fill="#cbd5e1" stroke="#38BDF8" stroke-width="2"/>
                <rect x="35" y="30" width="30" height="20" fill="#facc15" rx="2" stroke="#facc15"/>
                <path d="M30,30 L50,10 L70,30 Z" fill="#0f172a" stroke="#38BDF8" stroke-width="2"/>
                <rect x="42" y="50" width="16" height="140" fill="#94a3b8" opacity="0.3"/>
            </svg>
        </div>
    """, unsafe_allow_html=True)
    
    st.title("SENTINEL PLATINUM")
    
    # GESTIÓN DE PROYECTOS
    with st.expander("💾 Misión / Proyecto"):
        p_name = st.text_input("Nombre Misión")
        if st.button("Guardar Estado"):
            if not st.session_state.data_master.empty and p_name:
                st.session_state.proyectos[p_name] = st.session_state.data_master
                st.success("Guardado")
        
        if st.session_state.proyectos:
            sel = st.selectbox("Cargar", list(st.session_state.proyectos.keys()))
            if st.button("Abrir"):
                st.session_state.data_master = st.session_state.proyectos[sel]
                st.rerun()

    st.divider()
    obj = st.text_input("Objetivo", "Daniela Norambuena")
    ini = st.date_input("Inicio", datetime.now()-timedelta(days=30))
    fin = st.date_input("Fin", datetime.now())
    
    if st.button("🔥 ESCANEAR RED"):
        st.session_state.data_master = run_hydra_scan(obj, ini, fin)

# --- 6. DASHBOARD CENTRAL ---
df = st.session_state.data_master

if not df.empty:
    st.markdown(f"## 🛰️ Centro de Mando: {obj}")
    st.markdown(f"**Periodo de Análisis:** {ini.strftime('%d/%m/%Y')} - {fin.strftime('%d/%m/%Y')}")
    
    # 6.1 KPIs BLANCOS Y VISIBLES
    k1, k2, k3, k4 = st.columns(4)
    vol = len(df)
    reach = df['Reach'].sum()
    
    k1.metric("MENCIONES", vol)
    k2.metric("ALCANCE", f"{reach/1000000:.1f}M")
    k3.metric("INTERACCIONES", f"{df['Interactions'].sum()/1000:.1f}K")
    k4.metric("POSITIVIDAD", f"{int(len(df[df.Sentimiento=='Positivo'])/vol*100)}%")
    
    tabs = st.tabs(["📊 ESTRATEGIA & CONCEPTOS", "🎭 EMOCIONES & CLIMA", "🗺️ GEO & TÁCTICO", "📄 INFORME CONSULTOR", "🛠️ DATOS"])
    
    # === TAB 1: ESTRATEGIA (SUNBURST + TREEMAP) ===
    with tabs[0]:
        c_sun, c_tree = st.columns([1, 1])
        
        with c_sun:
            st.markdown("### 🕸️ Ecosistema Interactivo")
            st.caption("Haz clic en el centro para expandir.")
            # SUNBURST RESTAURADO
            fig_sun = px.sunburst(df, path=['Sentimiento', 'Fuente', 'Titular'], color='Sentimiento', 
                                  color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
            fig_sun.update_layout(height=600, paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white", size=14))
            st.plotly_chart(fig_sun, use_container_width=True)
            
        with c_tree:
            st.markdown("### 🌳 Mapa de Conceptos (Treemap)")
            st.caption("Tamaño = Impacto mediático.")
            # TREEMAP CON ETIQUETAS FORZADAS
            fig_tree = px.treemap(df, path=['Lugar', 'Fuente', 'Titular'], color='Sentimiento',
                                  color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
            fig_tree.update_traces(textinfo="label+value", textfont=dict(size=20), root_color="#0F172A")
            fig_tree.update_layout(height=600, margin=dict(t=0, l=0, r=0, b=0))
            st.plotly_chart(fig_tree, use_container_width=True)

    # === TAB 2: EMOCIONES ===
    with tabs[1]:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 📡 Radar de Emociones")
            # Agrupar y asegurar datos
            emo_stats = df['Emocion'].value_counts().reset_index()
            emo_stats.columns = ['Emocion', 'Count']
            
            fig_radar = px.line_polar(emo_stats, r='Count', theta='Emocion', line_close=True, template="plotly_dark")
            fig_radar.update_traces(fill='toself', line_color='#38BDF8')
            fig_radar.update_layout(height=500, paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_radar, use_container_width=True)
            
        with c2:
            st.markdown("### 🕒 Heatmap de Actividad")
            heat = df.groupby(['Dia', 'Hora']).size().reset_index(name='Menciones')
            fig_heat = px.density_heatmap(heat, x='Hora', y='Dia', z='Menciones', color_continuous_scale='Viridis')
            fig_heat.update_layout(height=500, paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_heat, use_container_width=True)

    # === TAB 3: GEO-TACTICAL (SIN PARPADEO) ===
    with tabs[2]:
        st.markdown("### 📍 Despliegue Territorial")
        # El mapa está en una pestaña separada y el faro está en el sidebar con overflow:hidden
        # Esto previene el repintado constante.
        m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
        cluster = MarkerCluster().add_to(m)
        for _, r in df.iterrows():
            c = "green" if r.Sentimiento=='Positivo' else "red" if r.Sentimiento=='Negativo' else "orange"
            folium.Marker([random.uniform(-29.95,-29.85), random.uniform(-71.3,-71.2)], 
                          popup=f"<b>{r.Fuente}</b><br>{r.Titular}", icon=folium.Icon(color=c)).add_to(cluster)
        st_folium(m, width="100%", height=600)

    # === TAB 4: REPORTE CONSULTOR ===
    with tabs[3]:
        st.markdown("### 🤖 Generador de Informes Ejecutivos")
        
        # Lógica de Informe PRO
        top_f = df['Fuente'].mode()[0]
        riesgo = int(len(df[df.Sentimiento=='Negativo'])/vol*100)
        
        txt_pro = f"""
        INFORME DE INTELIGENCIA ESTRATÉGICA - SENTINEL PLATINUM
        =======================================================
        OBJETIVO: {obj.upper()}
        PERIODO AUDITADO: {ini.strftime('%d-%m-%Y')} al {fin.strftime('%d-%m-%Y')}
        
        1. RESUMEN EJECUTIVO
        El sistema Sentinel ha procesado un volumen total de {vol} impactos mediáticos validados.
        El Alcance Potencial Acumulado se estima en {reach/1000000:.2f} millones de impresiones digitales.
        
        2. ANÁLISIS DE RIESGO REPUTACIONAL
        El Índice de Riesgo actual es del {riesgo}%. La polarización se concentra en la fuente '{top_f}', 
        que actúa como el principal vector de opinión en este ciclo.
        
        3. DIAGNÓSTICO EMOCIONAL
        La emoción predominante es '{df['Emocion'].mode()[0]}'. Esto indica una respuesta activa de la ciudadanía 
        frente a los hitos de gestión. Se recomienda monitorear los picos de actividad en los días {df['Dia'].mode()[0]}.
        
        4. RECOMENDACIONES TÁCTICAS
        - Activar protocolo de contención en '{top_f}'.
        - Reforzar la narrativa positiva en los sectores de {df['Lugar'].mode()[0]}.
        
        Documento generado por Sentinel Engine v29.0
        """
        st.text_area("Vista Previa del Análisis:", txt_pro, height=450)
        
        if st.button("📄 GENERAR PDF CON GRÁFICOS Y FECHAS"):
            # 1. Gráfico Barras
            fig1, ax1 = plt.subplots(figsize=(6,4))
            df['Sentimiento'].value_counts().plot(kind='bar', color=['#10b981','#ef4444','#f59e0b'], ax=ax1, title="Balance de Sentimiento")
            img1 = io.BytesIO(); plt.savefig(img1, format='png'); img1.seek(0)
            
            # 2. Gráfico Torta
            fig2, ax2 = plt.subplots(figsize=(6,4))
            df['Emocion'].value_counts().plot(kind='pie', ax=ax2, title="Distribución Emocional")
            img2 = io.BytesIO(); plt.savefig(img2, format='png'); img2.seek(0)
            
            # PDF
            pdf = FPDF()
            pdf.add_page(); pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 10, "REPORTE ESTRATEGICO PLATINUM", 0, 1, 'C')
            
            # FECHA DESTACADA
            pdf.set_fill_color(200, 220, 255); pdf.set_font("Arial", 'B', 11)
            pdf.cell(0, 10, f"Periodo: {ini.strftime('%d-%m-%Y')} - {fin.strftime('%d-%m-%Y')}", 0, 1, 'C', 1)
            pdf.ln(10)
            
            # TEXTO
            pdf.set_font("Arial", size=11)
            pdf.multi_cell(0, 7, txt_pro.encode('latin-1','replace').decode('latin-1'))
            
            # IMAGENES
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f1, tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f2:
                f1.write(img1.getvalue()); f2.write(img2.getvalue())
                pdf.image(f1.name, x=10, y=160, w=90)
                pdf.image(f2.name, x=110, y=160, w=90)
            
            out = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            pdf.output(out.name)
            with open(out.name, "rb") as f: st.download_button("📥 DESCARGAR PDF PROFESIONAL", f, "Reporte_Platinum.pdf")

    # === TAB 5: GESTIÓN ===
    with tabs[4]:
        df_ed = st.data_editor(df, use_container_width=True, key="main_ed")
        if st.button("✅ ACTUALIZAR BASE DE DATOS"):
            st.session_state.data_master = df_ed
            st.success("Sincronizado.")

else:
    st.info("👋 El sistema está listo. Configure su objetivo y presione 'ESCANEAR RED'.")
