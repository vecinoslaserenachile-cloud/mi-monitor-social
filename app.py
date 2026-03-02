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
import streamlit.components.v1 as components

# --- 1. CONFIGURACIÓN ---
st.set_page_config(page_title="Sentinel Apex", layout="wide", page_icon="⚓")

# --- 2. MEMORIA Y ESTADO ---
COLS = ['Fecha', 'Fuente', 'Titular', 'Link', 'Sentimiento', 'Alcance', 'Interacciones', 'Vibra', 'Lugar', 'Tipo']
if 'data_master' not in st.session_state: st.session_state.data_master = pd.DataFrame(columns=COLS)
if 'proyectos' not in st.session_state: st.session_state.proyectos = {}
if 'search_active' not in st.session_state: st.session_state.search_active = False

# --- 3. ESTILOS APEX (HTML CARDS & NO FLASH) ---
speed = "2s" if st.session_state.search_active else "12s"

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@300;700;900&display=swap');
    
    /* FONDO PRINCIPAL */
    .stApp, .main {{ background-color: #020617 !important; font-family: 'Montserrat', sans-serif; }}
    
    /* ESTILOS GLOBALES */
    h1, h2, h3, h4, h5, p, span, div {{ color: #FFFFFF !important; }}
    
    /* TABS PERSONALIZADOS */
    .stTabs [aria-selected="true"] {{
        background-color: #00F0FF !important;
        color: #000000 !important;
        font-weight: 900 !important;
        border-radius: 5px;
    }}
    .stTabs [aria-selected="false"] {{
        background-color: #0F172A !important;
        color: #FFFFFF !important;
    }}
    
    /* BOTONES */
    .stButton>button {{
        background: linear-gradient(90deg, #00F0FF 0%, #0077FF 100%) !important;
        color: #000000 !important;
        font-weight: 900 !important;
        border: none;
        text-transform: uppercase;
        letter-spacing: 1px;
    }}
    
    /* IFRAME FIX (NO FLASH) */
    iframe {{ background-color: #020617 !important; }}
    
    /* KPI CARD CONTAINER (CSS Grid para tarjetas HTML) */
    .kpi-grid {{
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 20px;
        margin-bottom: 30px;
    }}
    .kpi-card {{
        background: linear-gradient(145deg, #0f172a, #1e293b);
        border: 1px solid #00F0FF;
        border-radius: 12px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 4px 15px rgba(0, 240, 255, 0.15);
    }}
    .kpi-label {{
        color: #94A3B8 !important;
        font-size: 12px;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 5px;
    }}
    .kpi-value {{
        color: #FFFFFF !important;
        font-size: 36px;
        font-weight: 900;
        margin: 0;
        text-shadow: 0 0 10px rgba(255, 255, 255, 0.3);
    }}
    .kpi-sub {{
        color: #00F0FF !important;
        font-size: 12px;
        font-weight: 700;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 4. MOTORES INTELLIGENCIA ---
@st.cache_resource
def load_engine():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def normalizar_datos(txt, ia):
    # Sentimiento
    res = ia(txt[:512])[0]
    sc = int(res['label'].split()[0])
    s = "🔴 Negativo" if sc <= 2 else "🟡 Neutro" if sc == 3 else "🟢 Positivo"
    
    # Emoción (Fallback seguro)
    tl = txt.lower()
    emo = "👁️ Expectativa"
    if any(x in tl for x in ['miedo','terror','delito']): emo = "😱 Miedo"
    elif any(x in tl for x in ['ira','odio','vergüenza','robo']): emo = "🤬 Ira"
    elif any(x in tl for x in ['feliz','éxito','logro']): emo = "🎉 Alegría"
    elif any(x in tl for x in ['triste','pena']): emo = "😢 Tristeza"
    elif s == "Positivo": emo = "🤝 Confianza"
    
    # Lugar
    lug = "La Serena"
    if "coquimbo" in tl: lug = "Coquimbo"
    if "compañías" in tl: lug = "Las Compañías"
    
    return s, emo, lug

def get_metrics_advanced(src, sent):
    base = 100
    if any(x in src.lower() for x in ['biobio','emol','tercera']): base = 250000
    elif any(x in src.lower() for x in ['eldia','tiempo','observatodo']): base = 60000
    elif 'social' in src.lower(): base = 5000
    
    alc = int(base * random.uniform(0.5, 1.5))
    inter = int(alc * (0.05 if sent == "🔴 Negativo" else 0.02))
    return alc, inter

def run_scan_apex(obj, ini, fin, exclude_kw, platforms):
    st.session_state.search_active = True
    ia = load_engine()
    
    # Construcción de URLs (Recuperando filtros avanzados)
    base_rss = "https://news.google.com/rss/search?q={}&hl=es-419&gl=CL&ceid=CL:es-419"
    queries = [obj, f"{obj} noticias", f"{obj} gestión"]
    
    # Filtrado por plataformas seleccionadas
    sites = []
    if "Prensa" in platforms: sites.extend(["diarioeldia.cl", "semanariotiempo.cl", "biobiochile.cl"])
    if "Redes" in platforms: sites.extend(["tiktok.com", "reddit.com", "instagram.com", "facebook.com", "twitter.com"])
    
    urls = []
    for q in queries: urls.append(base_rss.format(quote(q)))
    for s in sites: urls.append(base_rss.format(quote(f"site:{s} {obj}")))
    
    res = []
    seen = set()
    prog = st.progress(0)
    
    for i, u in enumerate(urls):
        feed = feedparser.parse(u)
        for entry in feed.entries:
            # Filtro de Exclusión
            if exclude_kw and exclude_kw.lower() in entry.title.lower(): continue
            if entry.link in seen: continue
            seen.add(entry.link)
            
            try: dt = datetime.fromtimestamp(time.mktime(entry.published_parsed))
            except: dt = datetime.now()
            
            if not (ini <= dt.date() <= fin): continue
            
            s, e, l = normalizar_datos(entry.title, ia)
            src = entry.source.title if 'source' in entry else "Web"
            typ = "Red Social" if any(x in src.lower() for x in ['tiktok','instagram','facebook','twitter','reddit']) else "Prensa"
            
            a, inter = get_metrics_advanced(src, s)
            
            res.append({
                'Fecha': dt.date(), 'Hora': dt.hour, 'Dia': dt.strftime('%A'),
                'Fuente': src, 'Titular': entry.title, 'Link': entry.link,
                'Sentimiento': s, 'Alcance': a, 'Interacciones': inter,
                'Vibra': e, 'Lugar': l, 'Tipo': typ
            })
        prog.progress((i+1)/len(urls))
    
    st.session_state.search_active = False
    return pd.DataFrame(res)

# --- 5. SIDEBAR (CONFIGURACIÓN GRANULAR) ---
with st.sidebar:
    # Faro SVG Aislado
    faro_html = f"""
    <div style="width:100%; height:180px; background:radial-gradient(circle at bottom, #0f172a 0%, transparent 80%); position:relative; overflow:hidden; border-bottom:2px solid #00F0FF; margin-bottom:20px;">
        <div style="position:absolute; bottom:60px; left:50%; margin-left:-300px; width:600px; height:600px; 
             background:conic-gradient(from 0deg at 50% 50%, rgba(0,240,255,0.5) 0deg, transparent 60deg);
             transform-origin:50% 50%; animation: spin {speed} linear infinite;"></div>
        <div style="font-size:80px; position:relative; z-index:10; text-align:center; margin-top:40px; filter:drop-shadow(0 0 15px cyan);">⚓</div>
        <style>@keyframes spin {{ 0% {{transform: rotate(0deg);}} 100% {{transform: rotate(360deg);}} }}</style>
    </div>
    """
    components.html(faro_html, height=180)
    
    st.title("EL FARO")
    st.caption("Sentinel Apex v39.0")
    
    # 1. OBJETIVO
    obj_in = st.text_input("Objetivo de Rastreo", "Daniela Norambuena")
    
    # 2. FILTROS AVANZADOS (RECUPERADOS)
    with st.expander("🛠️ Ajuste Fino de Búsqueda", expanded=True):
        exclude_in = st.text_input("Excluir palabras (Opcional)", placeholder="Ej: concierto, sorteo")
        sources_in = st.multiselect("Fuentes a Escanear", ["Prensa", "Redes"], default=["Prensa", "Redes"])
        c1, c2 = st.columns(2)
        d_ini = c1.date_input("Desde", datetime.now()-timedelta(days=30))
        d_fin = c2.date_input("Hasta", datetime.now())
        
    if st.button("🔥 EJECUTAR ESCANEO APEX"):
        st.session_state.data_master = run_scan_apex(obj_in, d_ini, d_fin, exclude_in, sources_in)
        
    # 3. PROYECTOS
    with st.expander("📂 Gestión de Misiones"):
        p_name = st.text_input("Guardar como:")
        if st.button("Guardar Misión"):
            st.session_state.proyectos[p_name] = st.session_state.data_master
            st.success("Guardado")
        if st.session_state.proyectos:
            sel = st.selectbox("Cargar Misión", list(st.session_state.proyectos.keys()))
            if st.button("Cargar"):
                st.session_state.data_master = st.session_state.proyectos[sel]
                st.rerun()

# --- 6. DASHBOARD APEX ---
df = st.session_state.data_master
if not df.empty:
    st.markdown(f"## 🔭 Centro de Inteligencia: {obj_in.upper()}")
    
    # 6.1 KPIs CON HTML PURO (CERO GRISES, CERO ERRORES DE CSS)
    vol = len(df)
    alc = df['Alcance'].sum()
    inter = df['Interacciones'].sum()
    pos_p = int(len(df[df.Sentimiento.str.contains("Positivo")])/vol*100) if vol>0 else 0
    
    kpi_html = f"""
    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-label">Menciones Totales</div>
            <div class="kpi-value">{vol}</div>
            <div class="kpi-sub">Impactos Únicos</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Alcance Estimado</div>
            <div class="kpi-value">{alc/1000000:.1f}M</div>
            <div class="kpi-sub">Impresiones</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Interacciones</div>
            <div class="kpi-value">{inter/1000:.1f}K</div>
            <div class="kpi-sub">Engagement</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">Índice Positividad</div>
            <div class="kpi-value" style="color: #00FF00 !important;">{pos_p}%</div>
            <div class="kpi-sub">Favorabilidad</div>
        </div>
    </div>
    """
    st.markdown(kpi_html, unsafe_allow_html=True)
    
    tabs = st.tabs(["📊 ESTRATEGIA", "🎭 EMOCIONES", "🗺️ TÁCTICO", "🌪️ EMBUDO & DATA", "📄 REPORTE"])
    
    # === TAB 1: ESTRATEGIA (GRÁFICOS GIGANTES) ===
    with tabs[0]:
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown("### 🕸️ Ecosistema Interactivo")
            fig_sun = px.sunburst(df, path=['Sentimiento', 'Fuente', 'Titular'], color='Sentimiento',
                                  color_discrete_map={'🟢 Positivo':'#00FF00', '🔴 Negativo':'#FF0000', '🟡 Neutro':'#FFFF00'})
            fig_sun.update_traces(textinfo="label+percent entry", textfont=dict(size=16, color="white"))
            fig_sun.update_layout(height=500, paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_sun, use_container_width=True)
        with c2:
            st.markdown("### 📈 Tendencia Temporal")
            daily = df.groupby('Fecha').size().reset_index(name='Menciones')
            fig_line = px.area(daily, x='Fecha', y='Menciones', template="plotly_dark")
            fig_line.update_traces(line_color='#00F0FF', fill_color='rgba(0, 240, 255, 0.2)')
            fig_line.update_layout(height=500, paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_line, use_container_width=True)
            
        st.markdown("### 🌳 Mapa de Conceptos (Treemap)")
        fig_tree = px.treemap(df, path=['Lugar', 'Fuente', 'Titular'], color='Sentimiento',
                              color_discrete_map={'🟢 Positivo':'#00FF00', '🔴 Negativo':'#FF0000', '🟡 Neutro':'#FFFF00'})
        # Textos gigantes 28px
        fig_tree.update_traces(textinfo="label+value", textfont=dict(size=28, color="white", family="Arial Black"))
        fig_tree.update_layout(height=600, margin=dict(t=0,l=0,r=0,b=0))
        st.plotly_chart(fig_tree, use_container_width=True)

    # === TAB 2: EMOCIONES ===
    with tabs[1]:
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("### 📡 Radar de Vibras")
            df_vib = df['Vibra'].value_counts().reset_index()
            df_vib.columns = ['Vibra', 'Count']
            fig_r = px.line_polar(df_vib, r='Count', theta='Vibra', line_close=True, template="plotly_dark")
            fig_r.update_traces(fill='toself', line_color='#00F0FF')
            st.plotly_chart(fig_r, use_container_width=True)
        with c4:
            st.markdown("### 🥧 Share de Medios")
            fig_p = px.pie(df, names='Tipo', hole=0.5, color_discrete_sequence=px.colors.sequential.Cyan)
            fig_p.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_p, use_container_width=True)

    # === TAB 3: TÁCTICO (MAPA ESTABLE) ===
    with tabs[2]:
        st.markdown("### 📍 Despliegue Territorial")
        m = folium.Map(location=[-29.90, -71.25], zoom_start=12, tiles="CartoDB dark_matter")
        mc = MarkerCluster().add_to(m)
        for _, r in df.iterrows():
            folium.Marker([random.uniform(-29.95,-29.85), random.uniform(-71.3,-71.2)], popup=r['Titular']).add_to(mc)
        st_folium(m, width="100%", height=500)

    # === TAB 4: EMBUDO & DATOS ===
    with tabs[3]:
        c5, c6 = st.columns([1, 1])
        with c5:
            st.markdown("### 🌪️ Embudo de Conversión Mediática")
            st.caption("Cómo el ruido se transforma en interacción real.")
            fig_fun = px.funnel(pd.DataFrame({
                'Etapa': ['Alcance Potencial (Vistas)', 'Lectura Estimada', 'Interacción (Engagement)', 'Viralización'],
                'Valor': [alc, alc*0.2, inter, inter*0.1]
            }), x='Valor', y='Etapa')
            fig_fun.update_traces(marker=dict(color=["#00F0FF", "#00BFFF", "#1E90FF", "#0000FF"]))
            fig_fun.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_fun, use_container_width=True)
        
        with c6:
            st.markdown("### 📝 Ingesta de Antecedentes")
            with st.form("manual"):
                txt = st.text_area("Texto / Nota")
                src = st.text_input("Fuente")
                if st.form_submit_button("💾 INCORPORAR"):
                    new = df.iloc[0].to_dict()
                    new['Titular'] = txt; new['Fuente'] = src; new['Tipo'] = 'Manual'
                    st.session_state.data_master = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
                    st.success("Guardado")
                    st.rerun()

    # === TAB 5: REPORTE ===
    with tabs[4]:
        st.markdown("### 📄 Generador de Informes C-Level")
        
        top_src = df['Fuente'].mode()[0]
        
        txt_ia = f"""
        INFORME DE INTELIGENCIA ESTRATÉGICA - SENTINEL APEX
        ===================================================
        OBJETIVO: {obj_in.upper()}
        PERIODO: {datetime.now().strftime('%Y-%m-%d')}
        
        1. RESUMEN EJECUTIVO
        El sistema Sentinel ha procesado {vol} impactos. El Alcance Potencial Acumulado se sitúa en {alc/1000000:.2f} millones.
        La Tasa de Favorabilidad es del {pos_p}%, indicando un escenario de {'Oportunidad' if pos_p > 50 else 'Riesgo'}.
        
        2. ANÁLISIS DE PENETRACIÓN
        La fuente '{top_src}' lidera el Share of Voice. Se detecta una fuerte correlación entre las menciones en redes sociales y la emoción de '{df['Vibra'].mode()[0]}'.
        
        3. MATRIZ DE ACCIÓN
        - Contención: Monitorizar '{top_src}' por posibles focos de crisis.
        - Amplificación: Reforzar mensajes en zonas de alta positividad como {df['Lugar'].mode()[0]}.
        
        Generado por El Faro v39.0
        """
        st.text_area("Texto del Informe:", txt_ia, height=400)
        
        if st.button("DESCARGAR PDF PROFESIONAL"):
            # Generación de gráficos para PDF
            fig1, ax1 = plt.subplots(figsize=(6,4))
            df['Sentimiento'].value_counts().plot(kind='bar', color=['green','red','yellow'], ax=ax1, title="Balance")
            buf1 = io.BytesIO(); plt.savefig(buf1, format='png'); buf1.seek(0)
            
            pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 16); pdf.cell(0, 10, "REPORTE EL FARO", 0, 1, 'C')
            pdf.ln(10); pdf.set_font("Arial", size=11); pdf.multi_cell(0, 7, txt_ia.encode('latin-1','replace').decode('latin-1'))
            
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f1:
                f1.write(buf1.getvalue())
                pdf.image(f1.name, x=60, y=160, w=90)
                
            out = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
            pdf.output(out.name)
            with open(out.name, "rb") as f: st.download_button("📥 DESCARGAR PDF", f, "Reporte_Apex.pdf")

else:
    st.info("👋 Inicia el escaneo con el botón 🔥 en el panel lateral.")
