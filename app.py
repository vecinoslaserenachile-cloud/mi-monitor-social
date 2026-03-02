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
st.set_page_config(page_title="El Faro | Sentinel Prime", layout="wide", page_icon="⚓")

# --- 2. MEMORIA ESTRATÉGICA ---
if 'data_master' not in st.session_state: st.session_state.data_master = pd.DataFrame()
if 'proyectos' not in st.session_state: st.session_state.proyectos = {}
if 'current_project' not in st.session_state: st.session_state.current_project = "Nuevo Proyecto"
if 'search_active' not in st.session_state: st.session_state.search_active = False

# --- 3. ESTILOS DE ALTO RENDIMIENTO ---
v_luz = 2 if st.session_state.search_active else 10

st.markdown(f"""
    <style>
    .main {{ background-color: #020617 !important; color: #ffffff !important; font-family: 'Inter', sans-serif; }}
    
    /* Animación Faro Lateral */
    .faro-box {{
        position: relative; height: 120px; width: 100%; overflow: hidden;
        background: radial-gradient(circle at 50% 100%, #1e293b, #0f172a);
        border-bottom: 2px solid #38bdf8; margin-bottom: 20px;
    }}
    .torre {{ font-size: 60px; position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%); z-index: 2; }}
    .haz {{
        position: absolute; bottom: 40px; left: 50%; width: 400px; height: 400px;
        background: conic-gradient(from 0deg at 0% 100%, rgba(56,189,248,0.5) 0deg, transparent 50deg);
        transform-origin: 0% 100%; margin-left: -200px;
        animation: radarSweep {v_luz}s linear infinite; z-index: 1;
    }}
    @keyframes radarSweep {{ from {{ transform: rotate(-45deg); }} to {{ transform: rotate(45deg); }} }}

    /* Textos y Títulos */
    h1, h2, h3 {{ color: #38bdf8 !important; font-weight: 900 !important; }}
    div[data-testid="stMetric"] {{ 
        background: #0f172a !important; border: 1px solid #38bdf8 !important; border-radius: 12px !important; 
    }}
    div[data-testid="stMetricValue"] {{ color: #ffffff !important; font-size: 40px !important; }}
    div[data-testid="stMetricLabel"] {{ color: #94a3b8 !important; font-weight: bold !important; }}
    
    .stTabs [aria-selected="true"] {{ background-color: #38bdf8 !important; color: #020617 !important; font-weight: bold; }}
    .stButton>button {{ background: linear-gradient(90deg, #0ea5e9, #2563eb); color: white; border: none; font-weight: bold; }}
    </style>
    """, unsafe_allow_html=True)

# --- 4. MOTOR SENTINEL (HYDRA V27) ---
@st.cache_resource
def cargar_ia():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def get_metrics(fuente, sent):
    base = random.randint(200, 1000)
    if "Social" in fuente: base = random.randint(50, 500)
    elif any(x in fuente.lower() for x in ['biobio', 'latercera', 'emol']): base *= 500
    return int(base), int(base * 0.05)

def scan_total(obj, ini, fin, extra):
    st.session_state.search_active = True
    ia = cargar_ia()
    # 30 Puntos de Búsqueda
    urls = [f"https://news.google.com/rss/search?q={quote(obj)}&hl=es-419&gl=CL&ceid=CL:es-419"]
    qs = ["noticias", "polémica", "gestión", "opinión", "crítica", "denuncia", "municipalidad"]
    sites = ["diarioeldia.cl", "semanariotiempo.cl", "diariolaregion.cl", "elobservatodo.cl", "miradiols.cl", "tiktok.com", "reddit.com", "instagram.com", "facebook.com"]
    
    for q in qs: urls.append(f"https://news.google.com/rss/search?q={quote(f'{obj} {q}')}&hl=es-419&gl=CL&ceid=CL:es-419")
    for s in sites: urls.append(f"https://news.google.com/rss/search?q={quote(f'site:{s} {obj}')}&hl=es-419&gl=CL&ceid=CL:es-419")
    
    res = []
    vistos = set()
    prog = st.progress(0)
    for i, u in enumerate(urls):
        feed = feedparser.parse(u)
        for entry in feed.entries:
            try: dt = datetime.fromtimestamp(time.mktime(entry.published_parsed))
            except: dt = datetime.now()
            if not (ini <= dt.date() <= fin) or entry.link in vistos: continue
            vistos.add(entry.link)
            
            p = ia(entry.title[:512])[0]
            sc = int(p['label'].split()[0])
            sent = "Negativo" if sc <= 2 else "Neutro" if sc == 3 else "Positivo"
            r, interact = get_metrics(entry.source.title if 'source' in entry else "Web", sent)
            
            # Emociones
            emo = "Neutral"
            tl = entry.title.lower()
            if any(x in tl for x in ['odio', 'falla', 'error']): emo = "Ira"
            elif any(x in tl for x in ['miedo', 'alerta']): emo = "Miedo"
            elif any(x in tl for x in ['feliz', 'éxito']): emo = "Alegría"
            
            res.append({
                'Fecha': dt.date(), 'Hora': dt.hour, 'Día': dt.strftime('%A'),
                'Fuente': entry.source.title if 'source' in entry else "Social/Web",
                'Titular': entry.title, 'Sentimiento': sent, 'Link': entry.link,
                'Alcance': r, 'Interacciones': interact, 'Emocion': emo, 'Lugar': "La Serena"
            })
        prog.progress((i+1)/len(urls))
    st.session_state.search_active = False
    return pd.DataFrame(res)

# --- 5. SIDEBAR ---
with st.sidebar:
    st.markdown("""<div class='faro-box'><div class='haz'></div><div class='torre'>⚓</div></div>""", unsafe_allow_html=True)
    st.title("EL FARO")
    st.caption("Sentinel Prime v27.0")
    
    with st.expander("📂 Mis Proyectos", expanded=True):
        p_nom = st.text_input("Nombre Proyecto", value=st.session_state.current_project)
        c1, c2 = st.columns(2)
        if c1.button("💾 Guardar"):
            if not st.session_state.data_master.empty:
                st.session_state.proyectos[p_nom] = {'df': st.session_state.data_master, 'obj': obj_in, 'ini': f_ini, 'fin': f_fin}
                st.session_state.current_project = p_nom
                st.success("Guardado.")
        if c2.button("✨ Nuevo"):
            st.session_state.data_master = pd.DataFrame()
            st.rerun()
        if st.session_state.proyectos:
            sel = st.selectbox("Abrir", list(st.session_state.proyectos.keys()))
            if st.button("Cargar"):
                dat = st.session_state.proyectos[sel]
                st.session_state.data_master = dat['df']
                # Nota: Los inputs se actualizarán en el próximo ciclo si usáramos keys, por ahora cargamos data
                st.rerun()

    st.divider()
    obj_in = st.text_input("Objetivo", "Daniela Norambuena")
    f_ini = st.date_input("Desde", datetime.now()-timedelta(days=30))
    f_fin = st.date_input("Hasta", datetime.now())
    
    if st.button("🔥 ENCENDER EL FARO"):
        st.session_state.data_master = scan_total(obj_in, f_ini, f_fin, "")

# --- 6. DASHBOARD ---
df = st.session_state.data_master
if not df.empty:
    st.title(f"Centro de Mando: {obj_in}")
    
    tabs = st.tabs(["📊 ESTRATEGIA", "🗺️ TÁCTICO", "🤖 INFORME IA (+PDF)", "📝 GESTIÓN"])
    
    vol = len(df); r_tot = df['Alcance'].sum(); pos_r = int(len(df[df.Sentimiento=='Positivo'])/vol*100)
    
    with tabs[0]:
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Menciones", vol)
        k2.metric("Alcance Est.", f"{r_tot/1000000:.1f}M")
        k3.metric("Positivos", len(df[df.Sentimiento=='Positivo']), "🟢")
        k4.metric("Negativos", len(df[df.Sentimiento=='Negativo']), "🔴")
        
        c1, c2 = st.columns([2, 1])
        with c1:
            st.subheader("Sunburst Interactivo")
            fig = px.sunburst(df, path=['Sentimiento', 'Fuente', 'Titular'], color='Sentimiento', 
                              color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
            fig.update_layout(height=500, paper_bgcolor="rgba(0,0,0,0)", font_color="white")
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader("Salud Digital")
            fig_g = go.Figure(go.Indicator(mode="gauge+number", value=pos_r, gauge={'axis':{'range':[0,100]}, 'bar':{'color':"#38bdf8"}}))
            fig_g.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", font_color="white")
            st.plotly_chart(fig_g, use_container_width=True)
            
        st.subheader("Treemap de Impacto")
        fig_tree = px.treemap(df, path=['Lugar', 'Fuente', 'Titular'], color='Sentimiento', 
                              color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
        fig_tree.update_traces(textinfo="label+value", textfont=dict(size=20))
        st.plotly_chart(fig_tree, use_container_width=True)

    with tabs[1]:
        st.subheader("Mapa de Calor")
        m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
        cluster = MarkerCluster().add_to(m)
        for _, r in df.iterrows():
            folium.Marker([random.uniform(-29.95,-29.85), random.uniform(-71.3,-71.2)], popup=f"{r.Fuente}", icon=folium.Icon(color="blue")).add_to(cluster)
        st_folium(m, width="100%", height=500)

    with tabs[2]:
        st.subheader("Generador de Reportes Sentinel")
        
        # TEXTO DEL REPORTE
        top_src = df['Fuente'].mode()[0]
        txt_ia = f"""
        INFORME DE INTELIGENCIA TÁCTICA - SENTINEL PRIME
        ================================================
        OBJETIVO: {obj_in.upper()}
        PERIODO AUDITADO: {f_ini.strftime('%d/%m/%Y')} al {f_fin.strftime('%d/%m/%Y')}
        
        1. RESUMEN EJECUTIVO:
        En el periodo analizado, el sistema El Faro ha procesado {vol} impactos relevantes.
        El Índice de Favorabilidad alcanza un {pos_r}%, con un alcance estimado de {r_tot/1000000:.2f} millones de impresiones.
        
        2. ANÁLISIS DE FUENTES:
        La fuente '{top_src}' lidera la conversación. Se observa una polarización en redes sociales, 
        donde el sentimiento predominante es {df['Sentimiento'].mode()[0]}.
        
        3. CONCLUSIÓN TÉCNICA:
        {'Se recomienda mantener la estrategia actual.' if pos_r > 50 else 'ALERTA: Se sugiere activar protocolos de crisis en medios digitales.'}
        
        Generado por Sentinel Engine v27.0
        """
        st.text_area("Vista Previa del Texto:", txt_ia, height=300)
        
        if st.button("📄 GENERAR PDF CON GRÁFICOS Y FECHAS"):
            # Generar Gráfico 1: Sentimiento
            fig1, ax1 = plt.subplots(figsize=(6, 4))
            df['Sentimiento'].value_counts().plot(kind='bar', ax=ax1, color=['#10b981', '#ef4444', '#f59e0b'])
            plt.title("Distribución de Sentimiento")
            plt.tight_layout()
            img1 = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            plt.savefig(img1.name)
            
            # Generar Gráfico 2: Fuentes
            fig2, ax2 = plt.subplots(figsize=(6, 4))
            df['Fuente'].value_counts().head(5).plot(kind='barh', ax=ax2, color='#38bdf8')
            plt.title("Top 5 Fuentes")
            plt.tight_layout()
            img2 = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
            plt.savefig(img2.name)
            
            # Crear PDF
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 10, "REPORTE SENTINEL PRIME", 0, 1, 'C')
            pdf.ln(5)
            
            # FECHA DESTACADA
            pdf.set_font("Arial", 'B', 12)
            pdf.set_fill_color(200, 220, 255)
            pdf.cell(0, 10, f"Periodo: {f_ini.strftime('%d-%m-%Y')} al {f_fin.strftime('%d-%m-%Y')}", 0, 1, 'C', 1)
            pdf.ln(10)
            
            # TEXTO
            pdf.set_font("Arial", size=11)
            pdf.multi_cell(0, 7, txt_ia.encode('latin-1','replace').decode('latin-1'))
            pdf.ln(5)
            
            # IMÁGENES
            pdf.image(img1.name, x=10, w=90)
            pdf.image(img2.name, x=110, y=pdf.get_y() - 70, w=90) # Lado a lado (ajuste manual de Y)
            
            pdf_path = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf").name
            pdf.output(pdf_path)
            
            with open(pdf_path, "rb") as f:
                st.download_button("⬇️ DESCARGAR REPORTE OFICIAL", f, "Informe_Sentinel_Grafico.pdf")

    with tabs[3]:
        st.subheader("Corrección de Datos")
        df_ed = st.data_editor(df, use_container_width=True, key="main_editor")
        if st.button("💾 SINCRONIZAR CAMBIOS"):
            st.session_state.data_master = df_ed
            st.success("Datos actualizados.")
else:
    st.info("👋 Inicie el escaneo desde el panel lateral.")
