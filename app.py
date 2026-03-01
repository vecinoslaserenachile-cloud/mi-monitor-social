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
st.set_page_config(page_title="El Faro | Sentinel Master", layout="wide", page_icon="⚓")

# --- 2. ESTILOS VISUALES ---
st.markdown("""
    <style>
    .main { background: #0f172a; color: #f1f5f9; }
    h1 { background: linear-gradient(to right, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 900; }
    div[data-testid="stMetric"] { background: rgba(30, 41, 59, 0.7); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 12px; padding: 15px; }
    .stButton>button { background: linear-gradient(135deg, #0284c7 0%, #4f46e5 100%); color: white; border: none; padding: 12px; border-radius: 8px; font-weight: bold; width: 100%; box-shadow: 0 4px 15px rgba(0,0,0,0.3); }
    .stTabs [aria-selected="true"] { background-color: #0284c7 !important; color: white !important; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. MEMORIA ---
if 'data_raw' not in st.session_state:
    st.session_state.data_raw = pd.DataFrame(columns=['Fecha', 'Fuente', 'Titular', 'Sentimiento', 'Link', 'Score', 'Tipo', 'Lat', 'Lon', 'Lugar'])

# --- 4. GEODATA ---
GEO_DB = {
    "avenida del mar": [-29.9168, -71.2785], "faro": [-29.9073, -71.2847], "centro": [-29.9027, -71.2519],
    "plaza de armas": [-29.9027, -71.2519], "las compañías": [-29.8783, -71.2389], "tierras blancas": [-29.9392, -71.2294],
    "coquimbo": [-29.9533, -71.3436], "ovalle": [-30.6015, -71.2003], "vicuña": [-30.0319, -70.7081],
    "municipalidad": [-29.9045, -71.2489], "la florida": [-29.9238, -71.2185]
}

# --- 5. MOTOR SENTINEL ---
@st.cache_resource
def cargar_ia():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def detectar_geo(texto):
    t = texto.lower()
    for l, c in GEO_DB.items():
        if l in t: return c[0], c[1], l.title()
    return -29.9027 + random.uniform(-0.02, 0.02), -71.2519 + random.uniform(-0.02, 0.02), "La Serena"

def clasificar_fuente(link, nombre):
    l, n = link.lower(), nombre.lower()
    social = ['twitter', 'facebook', 'instagram', 'tiktok', 'x.com', 'youtube']
    if any(x in l or x in n for x in social): return "Red Social"
    if any(x in l for x in ['eldia', 'observatodo', 'miradio', 'region', 'semanariotiempo']): return "Prensa Regional"
    return "Prensa Nacional/Web"

def escanear_deep(objetivo, inicio, fin, extra):
    ia = cargar_ia()
    urls = [f"https://news.google.com/rss/search?q={quote(objetivo)}&hl=es-419&gl=CL&ceid=CL:es-419"]
    # Agregar búsquedas específicas para forzar medios locales
    locales = ["diarioeldia.cl", "semanariotiempo.cl", "elobservatodo.cl", "miradiols.cl"]
    for m in locales:
        urls.append(f"https://news.google.com/rss/search?q={quote(f'site:{m} {objetivo}')}&hl=es-419&gl=CL&ceid=CL:es-419")
    
    resultados = []
    vistos = set()
    prog = st.progress(0)
    for i, u in enumerate(urls):
        feed = feedparser.parse(u)
        for entry in feed.entries:
            try: f = datetime.fromtimestamp(time.mktime(entry.published_parsed)).date()
            except: f = datetime.now().date()
            if not (inicio <= f <= fin) or entry.link in vistos: continue
            vistos.add(entry.link)
            pred = ia(entry.title[:512])[0]
            s = int(pred['label'].split()[0])
            sent = "Negativo" if s <= 2 else "Neutro" if s == 3 else "Positivo"
            lat, lon, lug = detectar_geo(entry.title)
            resultados.append({
                'Fecha': f, 'Fuente': entry.source.title if 'source' in entry else "Web",
                'Titular': entry.title, 'Sentimiento': sent, 'Link': entry.link,
                'Score': s, 'Tipo': clasificar_fuente(entry.link, entry.source.title if 'source' in entry else ""),
                'Lat': lat, 'Lon': lon, 'Lugar': lug
            })
        prog.progress((i+1)/len(urls))
    prog.empty()
    return pd.DataFrame(resultados)

# --- 6. SIDEBAR ---
with st.sidebar:
    st.title("⚓ EL FARO")
    obj = st.text_input("Objetivo", "Daniela Norambuena")
    ext = st.text_input("Contexto", "seguridad")
    c1, c2 = st.columns(2)
    ini, f_fin = c1.date_input("Inicio", datetime.now()-timedelta(days=30)), c2.date_input("Fin", datetime.now())
    if st.button("📡 ACTIVAR RADAR"):
        st.session_state.data_raw = escanear_deep(obj, ini, f_fin, ext)

# --- 7. DASHBOARD ---
df_master = st.session_state.data_raw
if not df_master.empty:
    tabs = st.tabs(["📝 GESTIÓN", "📊 ESTRATEGIA 360", "🗺️ GEO-TACTICAL", "📱 FUENTES", "📄 INFORME IA"])
    
    # --- TAB 1: GESTIÓN (EDITABLE) ---
    with tabs[0]:
        st.subheader("Validación de Inteligencia")
        df_edited = st.data_editor(df_master, column_config={"Link": st.column_config.LinkColumn("Ver"), "Sentimiento": st.column_config.SelectboxColumn("Sentimiento", options=["Positivo","Negativo","Neutro","Irrelevante"])}, use_container_width=True, num_rows="dynamic")
        df_clean = df_edited[df_edited.Sentimiento != "Irrelevante"]

    # --- TAB 2: ESTRATEGIA (CON LOS DOS GRÁFICOS) ---
    with tabs[1]:
        k1, k2, k3 = st.columns(3); vol = len(df_clean)
        k1.metric("Menciones", vol); k2.metric("Positivos", len(df_clean[df_clean.Sentimiento=='Positivo']), "🟢")
        k3.metric("Negativos", len(df_clean[df_clean.Sentimiento=='Negativo']), "-🔴", delta_color="inverse")
        
        c_sun, c_gauge = st.columns([2, 1])
        with c_sun:
            st.subheader("🕸️ Sunburst Interactivo (Explora con Clics)")
            fig_sun = px.sunburst(df_clean, path=['Sentimiento', 'Fuente', 'Titular'], color='Sentimiento', color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
            fig_sun.update_traces(hovertemplate='<b>%{label}</b><br>Menciones: %{value}')
            fig_sun.update_layout(height=500, margin=dict(t=0, b=0, l=0, r=0), paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_sun, use_container_width=True)

        with c_gauge:
            st.subheader("🌡️ Termómetro")
            p = len(df_clean[df_clean.Sentimiento=='Positivo'])
            n = len(df_clean[df_clean.Sentimiento=='Negativo'])
            sc = ((p*100)+(vol-n-p)*50)/vol if vol>0 else 0
            fig_g = go.Figure(go.Indicator(mode="gauge+number", value=sc, gauge={'axis':{'range':[0,100]}, 'bar':{'color':"white"}, 'steps':[{'range':[0,40],'color':'#ef4444'},{'range':[40,60],'color':'#f59e0b'},{'range':[60,100],'color':'#10b981'}]}))
            fig_g.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", font={'color':'white'})
            st.plotly_chart(fig_g, use_container_width=True)

        st.subheader("🌳 Treemap de Lugares")
        fig_tree = px.treemap(df_clean, path=['Lugar', 'Fuente', 'Titular'], color='Sentimiento', color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
        st.plotly_chart(fig_tree, use_container_width=True)

    # --- TAB 3: MAPA (ARREGLADO) ---
    with tabs[2]:
        m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
        for _, r in df_clean.iterrows():
            c = "green" if r.Sentimiento=='Positivo' else "red" if r.Sentimiento=='Negativo' else "orange"
            folium.Marker([r.Lat, r.Lon], popup=f"{r.Fuente}: {r.Titular}", icon=folium.Icon(color=c)).add_to(m)
        st_folium(m, width="100%", height=500)

    # --- TAB 4: FUENTES ---
    with tabs[3]:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📰 Top Prensa")
            st.bar_chart(df_clean[df_clean.Tipo != 'Red Social']['Fuente'].value_counts().head(10))
        with c2:
            st.subheader("📱 Top Redes")
            st.bar_chart(df_clean[df_clean.Tipo == 'Red Social']['Fuente'].value_counts().head(10))

    # --- TAB 5: INFORME ---
    with tabs[4]:
        if st.button("✍️ GENERAR REPORTE IA"):
            txt = f"INFORME EL FARO\nObjetivo: {obj}\nTotal menciones: {len(df_clean)}\nAnálisis: Se detecta un clima {'favorables' if p>n else 'de riesgo'}. Foco principal en {df_clean['Lugar'].mode()[0]}."
            st.text_area("Resultado:", txt, height=200)
            pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", size=12); pdf.multi_cell(0,10,txt.encode('latin-1','replace').decode('latin-1'))
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); pdf.output(tmp.name)
            with open(tmp.name, "rb") as f: st.download_button("Descargar PDF", f, "Informe.pdf")
