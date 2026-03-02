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
import json

# --- 1. CONFIGURACIÓN E IDENTIDAD ---
st.set_page_config(page_title="El Faro | Sentinel Intelligence", layout="wide", page_icon="⚓")

# --- 2. ESTILOS PRO & ANIMACIÓN FARO ---
st.markdown("""
    <style>
    .main { background: #020617; color: #f8fafc; }
    h1 { background: linear-gradient(to right, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 900; }
    
    /* Animación del Faro/Radar */
    .faro-container {
        display: flex; justify-content: center; align-items: center; padding: 20px;
    }
    .faro-luz {
        width: 100px; height: 100px; background: #38bdf8; border-radius: 50%;
        box-shadow: 0 0 50px #38bdf8; position: relative;
        animation: pulso 2s infinite;
    }
    @keyframes pulso {
        0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(56, 189, 248, 0.7); }
        70% { transform: scale(1); box-shadow: 0 0 0 30px rgba(56, 189, 248, 0); }
        100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(56, 189, 248, 0); }
    }
    
    div[data-testid="stMetric"] { background: rgba(30, 41, 59, 0.8); border: 1px solid #38bdf8; border-radius: 15px; padding: 20px; }
    .stTabs [aria-selected="true"] { background-color: #0284c7 !important; color: white !important; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. GESTOR DE PROYECTOS (MEMORIA) ---
if 'proyectos' not in st.session_state:
    st.session_state.proyectos = {}
if 'data_master' not in st.session_state:
    st.session_state.data_master = pd.DataFrame()

# --- 4. GEODATA LA SERENA/COQUIMBO ---
GEO_DB = {
    "avenida del mar": [-29.9168, -71.2785], "faro": [-29.9073, -71.2847], "centro": [-29.9027, -71.2519],
    "plaza de armas": [-29.9027, -71.2519], "las compañías": [-29.8783, -71.2389], "tierras blancas": [-29.9392, -71.2294],
    "coquimbo": [-29.9533, -71.3436], "ovalle": [-30.6015, -71.2003], "vicuña": [-30.0319, -70.7081],
    "municipalidad": [-29.9045, -71.2489], "el milagro": [-29.9333, -71.2333]
}

# --- 5. MOTOR SENTINEL CORE ---
@st.cache_resource
def cargar_cerebro():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def clasificar_fuente_pro(link, nombre):
    l, n = link.lower(), nombre.lower()
    social = ['twitter', 'facebook', 'instagram', 'tiktok', 'x.com', 'youtube', 'reddit', 'threads']
    if any(x in l or x in n for x in social): return "Red Social"
    return "Prensa/Medios"

def escanear_deep(obj, ini, fin, extra_kw, sitios):
    ia = cargar_cerebro()
    queries = [obj, f'"{obj}"']
    if extra_kw: queries.append(f"{obj} {extra_kw}")
    
    urls = []
    base_rss = "https://news.google.com/rss/search?q={}&hl=es-419&gl=CL&ceid=CL:es-419"
    
    # Búsqueda amplificada
    for q in queries:
        urls.append(base_rss.format(quote(q)))
    if sitios:
        for s in sitios.split(","):
            urls.append(base_rss.format(quote(f'site:{s.strip()} {obj}')))
            
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
            
            p = ia(entry.title[:512])[0]
            score = int(p['label'].split()[0])
            sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
            
            # Geo-Inteligencia
            t_low = entry.title.lower()
            lat, lon, lug = -29.9027, -71.2519, "General"
            for k, v in GEO_DB.items():
                if k in t_low: lat, lon, lug = v[0], v[1], k.title(); break
            
            res.append({
                'Fecha': dt, 'Fuente': entry.source.title if 'source' in entry else "Web",
                'Titular': entry.title, 'Sentimiento': sent, 'Link': entry.link,
                'Tipo': clasificar_fuente_pro(entry.link, entry.source.title if 'source' in entry else ""),
                'Lat': lat, 'Lon': lon, 'Lugar': lug, 'Etiqueta': obj
            })
        prog.progress((i+1)/len(urls))
    prog.empty()
    return pd.DataFrame(res)

# --- 6. INTERFAZ SIDEBAR ---
with st.sidebar:
    st.markdown("<div class='faro-container'><div class='faro-luz'></div></div>", unsafe_allow_html=True)
    st.title("⚓ EL FARO")
    st.caption("v16.0 Titan Core")
    
    # PROYECTOS
    with st.expander("📂 Mis Proyectos (Guardar/Cargar)"):
        p_nombre = st.text_input("Nombre del Proyecto")
        if st.button("💾 Guardar Config Actual"):
            if p_nombre:
                st.session_state.proyectos[p_nombre] = {
                    "obj": obj_input, "ext": extra_kw, "sitios": sitios_prio, "ini": f_ini, "fin": f_fin
                }
                st.success(f"Proyecto {p_nombre} guardado.")
        
        if st.session_state.proyectos:
            p_select = st.selectbox("Cargar Proyecto", list(st.session_state.proyectos.keys()))
            if st.button("📂 Cargar"):
                config = st.session_state.proyectos[p_select]
                # Nota: Los inputs se actualizan por la clave interna de Streamlit en la siguiente ejecución
                st.info(f"Cargado {p_select}. Pulse 'ENCENDER' para procesar.")

    st.divider()
    
    # CONFIG DE BÚSQUEDA
    modo = st.radio("Modo Operativo", ["Individual", "Versus (Comparativo)"])
    if modo == "Individual":
        obj_input = st.text_input("Objetivo", "Daniela Norambuena")
        obj_b = None
    else:
        obj_input = st.text_input("Objetivo A", "Daniela Norambuena")
        obj_b = st.text_input("Objetivo B", "Roberto Jacob")
        
    extra_kw = st.text_input("Palabras Clave Extra", placeholder="seguridad, festival")
    sitios_prio = st.text_area("Sitios Específicos", "semanariotiempo.cl, diariolaregion.cl, diarioeldia.cl, elobservatodo.cl")
    
    col1, col2 = st.columns(2)
    f_ini = col1.date_input("Inicio", datetime.now()-timedelta(days=30))
    f_fin = col2.date_input("Fin", datetime.now())
    
    if st.button("🔥 ENCENDER EL FARO"):
        st.session_state.data_master = pd.DataFrame()
        with st.spinner("Rastreando ecosistema digital..."):
            df_a = escanear_deep(obj_input, f_ini, f_fin, extra_kw, sitios_prio)
            st.session_state.data_master = df_a
            if modo == "Versus (Comparativo)" and obj_b:
                df_b = escanear_deep(obj_b, f_ini, f_fin, extra_kw, sitios_prio)
                st.session_state.data_master = pd.concat([df_a, df_b], ignore_index=True)

# --- 7. DASHBOARD TITAN ---
df = st.session_state.data_master

if not df.empty:
    st.markdown(f"## ⚓ Dashboard de Inteligencia: {obj_input}")
    
    tabs = st.tabs(["📊 ESTRATEGIA 360", "⚔️ VERSUS", "🗺️ GEO-TACTICAL", "📝 GESTIÓN", "📄 INFORME IA"])
    
    # TAB 1: ESTRATEGIA
    with tabs[0]:
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Volumen Total", len(df))
        k2.metric("Positivos", len(df[df.Sentimiento=='Positivo']), "🟢")
        k3.metric("Negativos", len(df[df.Sentimiento=='Negativo']), "-🔴", delta_color="inverse")
        k4.metric("Fuentes", df['Fuente'].nunique())
        
        c1, c2 = st.columns([2, 1])
        with c1:
            st.subheader("🕸️ Sunburst Conceptual")
            fig_sun = px.sunburst(df, path=['Etiqueta', 'Sentimiento', 'Fuente', 'Titular'], color='Sentimiento', 
                                  color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
            fig_sun.update_layout(height=600, paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_sun, use_container_width=True)
            
        with c2:
            st.subheader("🌡️ Reputación")
            pos, neg, vol = len(df[df.Sentimiento=='Positivo']), len(df[df.Sentimiento=='Negativo']), len(df)
            sc = ((pos*100)+(vol-neg-pos)*50)/vol if vol>0 else 0
            fig_g = go.Figure(go.Indicator(mode="gauge+number", value=sc, gauge={'axis':{'range':[0,100]}, 'bar':{'color':"#38bdf8"}, 
                                                                         'steps':[{'range':[0,40],'color':'#ef4444'},{'range':[60,100],'color':'#10b981'}]}))
            fig_g.update_layout(height=300, paper_bgcolor="rgba(0,0,0,0)", font={'color':'white'})
            st.plotly_chart(fig_g, use_container_width=True)
            
            st.subheader("🏆 Top Fuentes")
            st.bar_chart(df['Fuente'].value_counts().head(10))

    # TAB 2: VERSUS
    with tabs[1]:
        if modo == "Versus (Comparativo)":
            st.subheader("⚔️ Análisis Comparativo")
            fig_vs = px.bar(df, x="Etiqueta", color="Sentimiento", barmode="group",
                            color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
            st.plotly_chart(fig_vs, use_container_width=True)
        else:
            st.info("Activa el modo Versus en el menú lateral para comparar objetivos.")

    # TAB 3: GEO
    with tabs[2]:
        st.subheader("📍 Despliegue Geo-Tactical")
        m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
        for _, r in df.iterrows():
            c = "green" if r.Sentimiento=='Positivo' else "red" if r.Sentimiento=='Negativo' else "orange"
            folium.Marker([r.Lat, r.Lon], popup=f"<a href='{r.Link}' target='_blank'>{r.Fuente}</a>", icon=folium.Icon(color=c)).add_to(m)
        st_folium(m, width="100%", height=600)

    # TAB 4: GESTIÓN
    with tabs[3]:
        st.subheader("🛠️ Editor de Mando")
        df_ed = st.data_editor(df, column_config={"Link": st.column_config.LinkColumn("Enlace")}, use_container_width=True)
        st.session_state.data_master = df_ed

    # TAB 5: INFORME IA
    with tabs[4]:
        if st.button("✍️ GENERAR INFORME IA LITERARIO"):
            txt = f"""
            INFORME DE INTELIGENCIA ESTRATÉGICA - EL FARO
            --------------------------------------------
            OBJETIVO: {obj_input.upper()}
            RANGO ANALIZADO: {f_ini} al {f_fin}
            ESTADO DE REPUTACIÓN: {'ESTABLE' if sc > 50 else 'CRÍTICO'}
            
            En la presente auditoría digital, el motor Sentinel ha identificado un volumen de {len(df)} menciones. 
            Se observa que el {int(pos/vol*100)}% de la conversación es favorable, mientras que un {int(neg/vol*100)}% presenta riesgos reputacionales.
            
            La fuente predominante en este periodo ha sido '{df['Fuente'].mode()[0]}', centrando la atención en el sector de {df['Lugar'].mode()[0]}.
            Se detecta una fuerte vinculación entre los conceptos de {extra_kw} y el objetivo analizado. 
            Se recomienda encarecidamente fortalecer la presencia en medios regionales para mitigar los focos de negatividad detectados.
            
            Este informe constituye un resumen técnico avanzado para la toma de decisiones.
            Generado por Vecinos La Serena spa.
            """
            st.text_area("Vista Previa:", txt, height=400)
            
            pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", size=12)
            pdf.multi_cell(0, 7, txt.encode('latin-1','replace').decode('latin-1'))
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); pdf.output(tmp.name)
            with open(tmp.name, "rb") as f: st.download_button("📥 DESCARGAR PDF", f, "Informe_Faro.pdf")
else:
    st.info("👋 Radar en espera. Configura tu proyecto y enciende El Faro.")
