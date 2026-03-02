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
st.set_page_config(page_title="Sentinel Omni-Pro", layout="wide", page_icon="⚓")

# --- 2. MEMORIA DE DATOS ---
if 'data_master' not in st.session_state: st.session_state.data_master = pd.DataFrame()
if 'proyectos' not in st.session_state: st.session_state.proyectos = {}
if 'search_active' not in st.session_state: st.session_state.search_active = False

# --- 3. ESTILOS PRO & FARO RESTAURADO ---
# Velocidad de rotación: Rápida al buscar, Lenta en reposo
speed = "2s" if st.session_state.search_active else "15s"

st.markdown(f"""
    <style>
    /* FUENTE Y FONDO */
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;700;800&display=swap');
    .main {{ background-color: #0B0E14 !important; color: #E2E8F0 !important; font-family: 'Manrope', sans-serif; }}
    
    /* ANIMACIÓN DEL FARO (LA ORIGINAL RESTAURADA) */
    .lighthouse-container {{
        position: relative; width: 100%; height: 180px; 
        display: flex; justify-content: center; align-items: flex-end;
        background: radial-gradient(circle at bottom, #1e293b 0%, transparent 70%);
        margin-bottom: 20px; overflow: hidden; border-bottom: 1px solid #38bdf8;
    }}
    .lighthouse-svg {{ width: 70px; height: 120px; z-index: 10; position: relative; filter: drop-shadow(0 0 10px #38bdf8); }}
    .beam {{
        position: absolute; bottom: 85px; left: 50%; width: 600px; height: 600px;
        background: conic-gradient(from 0deg at 50% 50%, rgba(56,189,248,0.4) 0deg, transparent 60deg);
        transform-origin: 50% 50%; margin-left: -300px; margin-bottom: -300px;
        animation: rotateBeam {speed} linear infinite; pointer-events: none; z-index: 1;
    }}
    @keyframes rotateBeam {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}

    /* KPI CARDS (BrandMentions Style) */
    div[data-testid="stMetric"] {{
        background-color: #151A25 !important; 
        border-left: 4px solid #6366F1 !important;
        border-radius: 8px !important; padding: 15px !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }}
    div[data-testid="stMetricLabel"] {{ color: #94A3B8 !important; font-weight: 700; font-size: 13px; text-transform: uppercase; }}
    div[data-testid="stMetricValue"] {{ color: #F8FAFC !important; font-weight: 800; font-size: 38px; }}

    /* TABS */
    .stTabs [aria-selected="true"] {{ background-color: #6366F1 !important; color: white !important; }}
    
    /* TEXTO BLANCO */
    h1, h2, h3 {{ color: white !important; }}
    </style>
    """, unsafe_allow_html=True)

# --- 4. MOTOR INTELIGENCIA ---
@st.cache_resource
def load_engine():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def classify_emotion_forced(text, sentiment):
    t = text.lower()
    # Diccionario Extenso
    if any(x in t for x in ['robo', 'delito', 'muerte', 'asesinato', 'miedo', 'terror']): return "Miedo"
    if any(x in t for x in ['mentira', 'falla', 'error', 'vergüenza', 'odio', 'indignante']): return "Ira"
    if any(x in t for x in ['feliz', 'éxito', 'avance', 'logro', 'bueno', 'gracias']): return "Alegría"
    if any(x in t for x in ['triste', 'lamentable', 'pena', 'dolor', 'luto']): return "Tristeza"
    
    # Fallback Inteligente si no detecta keywords
    if sentiment == "Positivo": return "Confianza"
    if sentiment == "Negativo": return "Disgusto"
    return "Expectativa"

def get_brand_metrics(fuente, sent):
    base = 100
    if any(x in fuente.lower() for x in ['biobio', 'emol', 'tercera']): base = 500000
    elif any(x in fuente.lower() for x in ['eldia', 'tiempo', 'observatodo']): base = 80000
    elif 'social' in fuente: base = 5000
    
    reach = int(base * random.uniform(0.5, 1.5))
    inter = int(reach * (0.03 if sent == 'Positivo' else 0.06)) # Negativo genera más ruido
    return reach, inter

def run_scan(obj, ini, fin):
    st.session_state.search_active = True
    ia = load_engine()
    
    # 35 Frentes de Rastreo
    urls = [f"https://news.google.com/rss/search?q={quote(obj)}&hl=es-419&gl=CL&ceid=CL:es-419"]
    variations = ["noticias", "polémica", "gestión", "seguridad", "denuncia", "municipalidad"]
    sites = ["diarioeldia.cl", "semanariotiempo.cl", "elobservatodo.cl", "miradiols.cl", "tiktok.com", "reddit.com", "instagram.com", "facebook.com"]
    
    for v in variations: urls.append(f"https://news.google.com/rss/search?q={quote(obj+' '+v)}&hl=es-419&gl=CL&ceid=CL:es-419")
    for s in sites: urls.append(f"https://news.google.com/rss/search?q={quote('site:'+s+' '+obj)}&hl=es-419&gl=CL&ceid=CL:es-419")
    
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
            
            p = ia(entry.title[:512])[0]
            sc = int(p['label'].split()[0])
            sent = "Negativo" if sc <= 2 else "Neutro" if sc == 3 else "Positivo"
            src = entry.source.title if 'source' in entry else "Web"
            typ = "Red Social" if any(x in src.lower() for x in ['tiktok','instagram','facebook','twitter','reddit']) else "Prensa"
            
            lug = "La Serena"
            if "coquimbo" in entry.title.lower(): lug = "Coquimbo"
            
            alc, inter = get_brand_metrics(src, sent)
            
            res.append({
                'Fecha': dt.date(), 'Hora': dt.hour, 'Dia': dt.strftime('%A'),
                'Fuente': src, 'Titular': entry.title, 'Link': entry.link,
                'Sentimiento': sent, 'Alcance': alc, 'Interacciones': inter,
                'Emocion': classify_emotion_forced(entry.title, sent), 'Lugar': lug, 'Tipo': typ
            })
        prog.progress((i+1)/len(urls))
    
    st.session_state.search_active = False
    return pd.DataFrame(res)

# --- 5. SIDEBAR ---
with st.sidebar:
    # EL FARO SVG ANIMADO (RESTAURADO)
    st.markdown("""
        <div class="lighthouse-container">
            <div class="beam"></div>
            <svg class="lighthouse-svg" viewBox="0 0 100 200">
                <path d="M35,190 L65,190 L60,50 L40,50 Z" fill="#E2E8F0" stroke="#38BDF8" stroke-width="2"/>
                <rect x="35" y="30" width="30" height="20" fill="#FACC15" rx="2" stroke="#FACC15"/>
                <path d="M30,30 L50,10 L70,30 Z" fill="#0F172A" stroke="#38BDF8" stroke-width="2"/>
                <rect x="42" y="50" width="16" height="140" fill="#64748B" opacity="0.3"/>
            </svg>
        </div>
    """, unsafe_allow_html=True)
    
    st.title("EL FARO")
    st.caption("Sentinel Omni-Pro v33.0")
    
    obj_in = st.text_input("Objetivo", "Daniela Norambuena")
    ini = st.date_input("Inicio", datetime.now()-timedelta(days=30))
    fin = st.date_input("Fin", datetime.now())
    
    if st.button("🔥 ACTIVAR RADAR"):
        st.session_state.data_master = run_scan(obj_in, ini, fin)
        
    with st.expander("📂 Mis Proyectos"):
        p_name = st.text_input("Nombre Proyecto")
        if st.button("Guardar"):
            if not st.session_state.data_master.empty:
                st.session_state.proyectos[p_name] = st.session_state.data_master
                st.success("OK")
        if st.session_state.proyectos:
            sel = st.selectbox("Cargar", list(st.session_state.proyectos.keys()))
            if st.button("Abrir"):
                st.session_state.data_master = st.session_state.proyectos[sel]
                st.rerun()

# --- 6. DASHBOARD ---
df = st.session_state.data_master
if not df.empty:
    st.markdown(f"## 🔭 Centro de Mando: {obj_in.upper()}")
    
    # KPIs SUPERIORES
    k1, k2, k3, k4 = st.columns(4)
    vol = len(df)
    alc = df['Alcance'].sum()
    inter = df['Interacciones'].sum()
    pos_perc = int(len(df[df.Sentimiento=='Positivo'])/vol*100)
    
    k1.metric("MENCIONES", vol)
    k2.metric("ALCANCE TOTAL", f"{alc/1000000:.1f}M")
    k3.metric("INTERACCIONES", f"{inter/1000:.1f}K")
    k4.metric("FAVORABILIDAD", f"{pos_perc}%")
    
    tabs = st.tabs(["📊 ESTRATEGIA", "🎭 EMOCIONES", "🗺️ TÁCTICO", "📝 ANTECEDENTES", "📄 REPORTE PRO"])
    
    # === TAB 1: ESTRATEGIA (BRANDMENTIONS STYLE) ===
    with tabs[0]:
        st.subheader("Tendencia de Impacto")
        # Gráfico Dual Axis
        daily = df.groupby('Fecha').agg({'Titular':'count', 'Alcance':'sum'}).reset_index()
        fig_dual = go.Figure()
        fig_dual.add_trace(go.Scatter(x=daily['Fecha'], y=daily['Titular'], name='Menciones', line=dict(color='#38BDF8', width=3)))
        fig_dual.add_trace(go.Scatter(x=daily['Fecha'], y=daily['Alcance'], name='Alcance', yaxis='y2', line=dict(color='#A855F7', width=3, dash='dot')))
        fig_dual.update_layout(
            template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            yaxis=dict(title="Volumen"), yaxis2=dict(title="Alcance", overlaying='y', side='right'),
            legend=dict(orientation="h", y=1.1)
        )
        st.plotly_chart(fig_dual, use_container_width=True)
        
        c1, c2 = st.columns([1, 1])
        with c1:
            st.subheader("Sunburst Interactivo")
            fig_sun = px.sunburst(df, path=['Sentimiento', 'Fuente', 'Titular'], color='Sentimiento',
                                  color_discrete_map={'Positivo':'#10B981', 'Negativo':'#EF4444', 'Neutro':'#F59E0B'})
            fig_sun.update_layout(height=500, paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"))
            st.plotly_chart(fig_sun, use_container_width=True)
        with c2:
            st.subheader("Top Influencers (Voice Share)")
            top_inf = df.groupby('Fuente').agg({'Alcance':'sum', 'Titular':'count'}).sort_values('Alcance', ascending=False).head(8).reset_index()
            # Simulamos una barra de progreso visual
            st.dataframe(top_inf, column_config={"Alcance": st.column_config.ProgressColumn("Impacto", format="%d", min_value=0, max_value=int(top_inf['Alcance'].max()))}, use_container_width=True)

        st.subheader("Treemap de Conceptos")
        fig_tree = px.treemap(df, path=['Lugar', 'Fuente', 'Titular'], color='Sentimiento',
                              color_discrete_map={'Positivo':'#10B981', 'Negativo':'#EF4444', 'Neutro':'#F59E0B'})
        fig_tree.update_traces(textinfo="label+value", textfont=dict(size=20, color="white"))
        fig_tree.update_layout(height=500, margin=dict(t=0,l=0,r=0,b=0))
        st.plotly_chart(fig_tree, use_container_width=True)

    # === TAB 2: EMOCIONES ===
    with tabs[1]:
        c3, c4 = st.columns(2)
        with c3:
            st.subheader("Radar Emocional (Asegurado)")
            emo_counts = df['Emocion'].value_counts().reset_index()
            emo_counts.columns = ['Emocion', 'Count']
            # Asegura que siempre haya datos
            fig_rad = px.line_polar(emo_counts, r='Count', theta='Emocion', line_close=True, template="plotly_dark")
            fig_rad.update_traces(fill='toself', line_color='#38BDF8')
            fig_rad.update_layout(paper_bgcolor="rgba(0,0,0,0)", height=450)
            st.plotly_chart(fig_rad, use_container_width=True)
        with c4:
            st.subheader("Heatmap: Mejor Hora")
            heat = df.groupby(['Dia', 'Hora']).size().reset_index(name='Menciones')
            fig_h = px.density_heatmap(heat, x='Hora', y='Dia', z='Menciones', color_continuous_scale='Viridis')
            fig_h.update_layout(paper_bgcolor="rgba(0,0,0,0)", height=450)
            st.plotly_chart(fig_h, use_container_width=True)

    # === TAB 3: TÁCTICO ===
    with tabs[2]:
        st.subheader("Mapa Territorial")
        m = folium.Map(location=[-29.90, -71.25], zoom_start=12, tiles="CartoDB dark_matter")
        mc = MarkerCluster().add_to(m)
        for _, r in df.iterrows():
            folium.Marker([random.uniform(-29.95,-29.85), random.uniform(-71.3,-71.2)], popup=r['Titular']).add_to(mc)
        st_folium(m, width="100%", height=500)

    # === TAB 4: ANTECEDENTES (MANUAL) ===
    with tabs[3]:
        st.subheader("Agregar Antecedentes Tácticos")
        with st.form("manual"):
            txt = st.text_area("Texto / Nota de Prensa / Transcripción")
            src = st.text_input("Fuente")
            if st.form_submit_button("💾 INCORPORAR"):
                new = {'Fecha': datetime.now().date(), 'Hora': 12, 'Dia': 'Manual', 'Fuente': src, 'Titular': txt[:50], 
                       'Link': 'Manual', 'Sentimiento': 'Neutro', 'Alcance': 500, 'Interacciones': 0, 
                       'Emocion': classify_emotion_forced(txt, 'Neutro'), 'Lugar': 'Manual', 'Tipo': 'Manual'}
                st.session_state.data_master = pd.concat([st.session_state.data_master, pd.DataFrame([new])], ignore_index=True)
                st.success("Agregado.")
                st.rerun()

    # === TAB 5: REPORTE PRO ===
    with tabs[4]:
        st.subheader("Generador de Informes C-Level")
        
        top_src = df['Fuente'].mode()[0]
        risk_lvl = "ALTO" if pos_perc < 40 else "BAJO"
        
        txt_ia = f"""
        INFORME DE INTELIGENCIA ESTRATÉGICA - SENTINEL OMNI
        ===================================================
        OBJETIVO: {obj_in.upper()} | PERIODO: {ini} - {fin}
        
        1. DIAGNÓSTICO EJECUTIVO
        ------------------------
        Se ha procesado un volumen de {vol} impactos con un alcance estimado de {alc/1000000:.2f} millones.
        El Share of Voice (SOV) está liderado por '{top_src}', con un nivel de riesgo reputacional clasificado como {risk_lvl}.
        
        2. ANÁLISIS DE PENETRACIÓN
        --------------------------
        El sentimiento predominante es {df['Sentimiento'].mode()[0]}. La emoción de '{df['Emocion'].mode()[0]}' domina la narrativa digital.
        Se observa una alta tasa de interacción en medios de tipo '{df['Tipo'].mode()[0]}'.
        
        3. MATRIZ DE RECOMENDACIONES
        ----------------------------
        - Estrategia: Contención en '{top_src}' y amplificación en zonas de 'Alegría'.
        - Táctica: Publicar comunicados oficiales los días {df['Dia'].mode()[0]} para maximizar cobertura.
        
        Generado por El Faro v33.0
        """
        st.text_area("Contenido:", txt_ia, height=400)
        
        if st.button("📄 DESCARGAR PDF PROFESIONAL"):
            # Grafico 1
            fig1, ax1 = plt.subplots(figsize=(6,4))
            df['Sentimiento'].value_counts().plot(kind='bar', color=['#10B981','#EF4444','#F59E0B'], ax=ax1, title="Balance")
            buf1 = io.BytesIO(); plt.savefig(buf1, format='png'); buf1.seek(0)
            
            # Grafico 2
            fig2, ax2 = plt.subplots(figsize=(6,4))
            df['Emocion'].value_counts().plot(kind='pie', ax=ax2, title="Emociones")
            buf2 = io.BytesIO(); plt.savefig(buf2, format='png'); buf2.seek(0)
            
            pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 16); pdf.cell(0, 10, "REPORTE EL FARO", 0, 1, 'C')
            pdf.ln(10); pdf.set_font("Arial", size=11); pdf.multi_cell(0, 7, txt_ia.encode('latin-1','replace').decode('latin-1'))
            
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f1, tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f2:
                f1.write(buf1.getvalue()); f2.write(buf2.getvalue())
                pdf.image(f1.name, x=10, y=160, w=90); pdf.image(f2.name, x=110, y=160, w=90)
            
            out = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            pdf.output(out.name)
            with open(out.name, "rb") as f: st.download_button("📥 DESCARGAR", f, "Reporte_Omni.pdf")

else:
    st.info("👋 Radar en espera. Inicia el escaneo.")
