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
st.set_page_config(page_title="El Faro | Total Vision", layout="wide", page_icon="⚓")

# --- 2. ESTILOS PRO ---
st.markdown("""
    <style>
    .main { background: #020617; color: #f8fafc; }
    h1 { background: linear-gradient(to right, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 900; }
    div[data-testid="stMetric"] { background: rgba(30, 41, 59, 0.8); border: 1px solid #38bdf8; border-radius: 15px; padding: 20px; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. MEMORIA ---
if 'data_faro' not in st.session_state:
    st.session_state.data_faro = pd.DataFrame()

# --- 4. GEODATA LA SERENA/COQUIMBO ---
GEO_DB = {
    "avenida del mar": [-29.9168, -71.2785], "faro": [-29.9073, -71.2847], "centro": [-29.9027, -71.2519],
    "plaza de armas": [-29.9027, -71.2519], "las compañías": [-29.8783, -71.2389], "tierras blancas": [-29.9392, -71.2294],
    "coquimbo": [-29.9533, -71.3436], "ovalle": [-30.6015, -71.2003], "vicuña": [-30.0319, -70.7081],
    "municipalidad": [-29.9045, -71.2489], "el milagro": [-29.9333, -71.2333]
}

# --- 5. MOTOR SENTINEL V15 ---
@st.cache_resource
def cargar_ia():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def clasificar_fuente_ninja(link, nombre):
    l, n = link.lower(), nombre.lower()
    social = ['twitter', 'facebook', 'instagram', 'tiktok', 'x.com', 'youtube', 'reddit', 'threads', 'twitch']
    if any(x in l or x in n for x in social): return "Red Social"
    return "Prensa/Medios"

def escanear_total(obj, ini, fin):
    ia = cargar_ia()
    # ESTRATEGIA HYDRA: Búsqueda en todos los frentes posibles
    sites = [
        "diarioeldia.cl", "semanariotiempo.cl", "elobservatodo.cl", "miradiols.cl", "diariolaregion.cl",
        "reddit.com", "threads.net", "youtube.com", "twitter.com", "tiktok.com"
    ]
    
    urls = [f"https://news.google.com/rss/search?q={quote(obj)}&hl=es-419&gl=CL&ceid=CL:es-419"]
    for s in sites:
        urls.append(f"https://news.google.com/rss/search?q={quote(f'site:{s} {obj}')}&hl=es-419&gl=CL&ceid=CL:es-419")
    
    res = []
    vistos = set()
    prog = st.progress(0)
    for i, u in enumerate(urls):
        feed = feedparser.parse(u)
        for entry in feed.entries:
            try: dt = datetime.fromtimestamp(time.mktime(entry.published_parsed)).date()
            except: dt = datetime.now().date()
            if not (ini <= dt <= fin) or entry.link in vistos: continue
            vistos.add(entry.link)
            
            pred = ia(entry.title[:512])[0]
            score = int(pred['label'].split()[0])
            sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
            
            # Ubicación
            t_low = entry.title.lower()
            lat, lon, lug = -29.9027, -71.2519, "General"
            for k, v in GEO_DB.items():
                if k in t_low: lat, lon, lug = v[0], v[1], k.title(); break
            
            res.append({
                'Fecha': dt, 'Fuente': entry.source.title if 'source' in entry else "Web",
                'Titular': entry.title, 'Sentimiento': sent, 'Link': entry.link,
                'Tipo': clasificar_fuente_ninja(entry.link, entry.source.title if 'source' in entry else ""),
                'Lat': lat, 'Lon': lon, 'Lugar': lug
            })
        prog.progress((i+1)/len(urls))
    prog.empty()
    return pd.DataFrame(res)

# --- 6. SIDEBAR ---
with st.sidebar:
    st.markdown("# ⚓ EL FARO")
    st.caption("v15.0 | Total Vision")
    obj_input = st.text_input("Objetivo de Radar", "Daniela Norambuena")
    c1, c2 = st.columns(2)
    f_ini = c1.date_input("Desde", datetime.now()-timedelta(days=30))
    f_fin = c2.date_input("Hasta", datetime.now())
    if st.button("🔥 ENCENDER EL FARO"):
        with st.spinner("Rastreando redes y prensa..."):
            st.session_state.data_faro = escanear_total(obj_input, f_ini, f_fin)

# --- 7. DASHBOARD ---
df = st.session_state.data_faro
if not df.empty:
    tabs = st.tabs(["📝 GESTIÓN", "📊 ESTRATEGIA 360", "🗺️ GEO-TACTICAL", "📄 INFORME IA"])
    
    with tabs[0]:
        st.subheader("Control de Mando")
        df_ed = st.data_editor(df, column_config={"Link": st.column_config.LinkColumn("Enlace"), "Sentimiento": st.column_config.SelectboxColumn("Sentimiento", options=["Positivo","Negativo","Neutro","Irrelevante"])}, use_container_width=True, key="main_ed")
        st.session_state.data_faro = df_ed
        df_clean = df_ed[df_ed.Sentimiento != "Irrelevante"]

    with tabs[1]:
        k1, k2, k3 = st.columns(3); vol = len(df_clean)
        k1.metric("Volumen", vol); k2.metric("Positivos", len(df_clean[df_clean.Sentimiento=='Positivo'])); k3.metric("Negativos", len(df_clean[df_clean.Sentimiento=='Negativo']))
        
        c_sun, c_gauge = st.columns([2, 1])
        with c_sun:
            st.subheader("🕸️ Sunburst (Clic para profundizar)")
            fig_sun = px.sunburst(df_clean, path=['Sentimiento', 'Fuente', 'Titular'], color='Sentimiento', color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
            fig_sun.update_layout(height=500, margin=dict(t=0, b=0, l=0, r=0), paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_sun, use_container_width=True)

        with c_gauge:
            st.subheader("🌡️ Velocímetro")
            pos, neg = len(df_clean[df_clean.Sentimiento=='Positivo']), len(df_clean[df_clean.Sentimiento=='Negativo'])
            sc = ((pos*100)+(vol-neg-pos)*50)/vol if vol>0 else 0
            fig_g = go.Figure(go.Indicator(mode="gauge+number", value=sc, gauge={'axis':{'range':[0,100]}, 'steps':[{'range':[0,40],'color':'#ef4444'},{'range':[60,100],'color':'#10b981'}]}))
            fig_g.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", font={'color':'white'})
            st.plotly_chart(fig_g, use_container_width=True)

        st.subheader("🌳 Treemap (Clima por Lugar)")
        fig_tree = px.treemap(df_clean, path=['Lugar', 'Fuente', 'Titular'], color='Sentimiento', color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
        fig_tree.update_traces(textinfo="label+value", textfont=dict(size=18))
        fig_tree.update_layout(height=500, margin=dict(t=30, b=30, l=10, r=10))
        st.plotly_chart(fig_tree, use_container_width=True)

    with tabs[2]:
        m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
        for _, r in df_clean.iterrows():
            folium.Marker([r.Lat, r.Lon], popup=f"<a href='{r.Link}' target='_blank'>{r.Fuente}</a>").add_to(m)
        st_folium(m, width="100%", height=550)

    with tabs[3]:
        st.subheader("🤖 Informe IA Narrativo")
        if st.button("✍️ GENERAR REPORTE"):
            txt = f"""
            INFORME ESTRATÉGICO EL FARO
            ---------------------------
            OBJETIVO: {obj_input.upper()}
            PERIODO: {f_ini} al {f_fin}
            
            1. ANÁLISIS DE SENTIMIENTO:
            Se detectaron {vol} señales. El clima es predominantemente {('Positivo' if pos>neg else 'Negativo')}.
            
            2. FOCOS TERRITORIALES:
            La actividad se concentra en {df_clean['Lugar'].mode()[0]}, liderada por {df_clean['Fuente'].mode()[0]}.
            
            3. RECOMENDACIÓN ESTRATÉGICA:
            {'Escenario de confort.' if pos>neg else 'Se requiere gestión de crisis inmediata en prensa regional.'}
            """
            st.text_area("Borrador:", txt, height=300)
            
            # Gráfico para PDF
            fig_pdf, ax = plt.subplots(figsize=(5,3))
            df_clean['Sentimiento'].value_counts().plot(kind='bar', ax=ax, color=['#10b981','#ef4444','#f59e0b'])
            plt.tight_layout()
            img_path = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
            plt.savefig(img_path)

            # PDF
            pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 10, f"REPORTE EL FARO: {obj_input.upper()}", 0, 1, 'C')
            pdf.set_font("Arial", size=10); pdf.cell(0, 10, f"Rango: {f_ini} a {f_fin}", 0, 1, 'C')
            pdf.ln(5); pdf.set_font("Arial", size=11); pdf.multi_cell(0, 7, txt.encode('latin-1','replace').decode('latin-1'))
            pdf.image(img_path, x=50, w=100)
            
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            pdf.output(tmp.name)
            with open(tmp.name, "rb") as f:
                st.download_button("📥 DESCARGAR INFORME PDF", f, "Informe_Faro.pdf")
else:
    st.info("👋 Radar en espera. Configura el objetivo y enciende El Faro.")
