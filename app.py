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
st.set_page_config(page_title="El Faro | Sentinel Intelligence", layout="wide", page_icon="⚓")

# --- 2. ESTILOS PRO & ILUSTRACIÓN FARO ---
st.markdown("""
    <style>
    .main { background: #020617; color: #f8fafc; }
    h1 { background: linear-gradient(to right, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 900; }
    
    /* Animación Faro Realista */
    .lighthouse-wrap { position: relative; width: 100%; text-align: center; padding: 20px; }
    .lighthouse { font-size: 60px; filter: drop-shadow(0 0 10px #38bdf8); }
    .light-beam {
        position: absolute; top: 30px; left: 50%; width: 200px; height: 100px;
        background: conic-gradient(from 0deg at 0% 50%, rgba(56,189,248,0.5) 0deg, transparent 60deg);
        transform-origin: 0% 50%; animation: rotateBeam 4s linear infinite;
    }
    @keyframes rotateBeam { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

    /* KPIs ALTO CONTRASTE */
    div[data-testid="stMetric"] { background: #1e293b; border: 2px solid #38bdf8; border-radius: 15px; padding: 20px; }
    div[data-testid="stMetricValue"] { color: #ffffff !important; font-size: 35px !important; }
    div[data-testid="stMetricLabel"] { color: #38bdf8 !important; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. PERSISTENCIA ---
if 'data_master' not in st.session_state: st.session_state.data_master = pd.DataFrame()
if 'proyectos' not in st.session_state: st.session_state.proyectos = {}

# --- 4. GEODATA LA SERENA/COQUIMBO ---
GEO_DB = {
    "avenida del mar": [-29.9168, -71.2785], "faro": [-29.9073, -71.2847], "centro": [-29.9027, -71.2519],
    "plaza de armas": [-29.9027, -71.2519], "las compañías": [-29.8783, -71.2389], "tierras blancas": [-29.9392, -71.2294],
    "coquimbo": [-29.9533, -71.3436], "ovalle": [-30.6015, -71.2003], "vicuña": [-30.0319, -70.7081],
    "municipalidad": [-29.9045, -71.2489], "el milagro": [-29.9333, -71.2333]
}

# --- 5. MOTOR SENTINEL (DEEP HYDRA) ---
@st.cache_resource
def cargar_ia():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def clasificar_redes(link):
    l = link.lower()
    redes = ['tiktok', 'reddit', 'threads', 'instagram', 'facebook', 'x.com', 'twitter', 'youtube']
    for r in redes:
        if r in l: return "Red Social"
    return "Prensa/Medios"

def mineria_profunda(obj, ini, fin, extra):
    ia = cargar_ia()
    # ESTRATEGIA HYDRA: Triangulación de Redes + Prensa
    targets = [
        "diarioeldia.cl", "semanariotiempo.cl", "elobservatodo.cl", "miradiols.cl", "diariolaregion.cl",
        "tiktok.com", "reddit.com", "threads.net", "instagram.com", "twitter.com"
    ]
    
    urls = [f"https://news.google.com/rss/search?q={quote(obj)}&hl=es-419&gl=CL&ceid=CL:es-419"]
    for t in targets:
        urls.append(f"https://news.google.com/rss/search?q={quote(f'site:{t} {obj}')}&hl=es-419&gl=CL&ceid=CL:es-419")
    
    res = []
    vistos = set() # Solo eliminamos si el LINK es idéntico. Fuentes distintas con misma nota se mantienen.
    prog = st.progress(0)
    
    for i, u in enumerate(urls):
        feed = feedparser.parse(u)
        for entry in feed.entries:
            try: f_dt = datetime.fromtimestamp(time.mktime(entry.published_parsed)).date()
            except: f_dt = datetime.now().date()
            if not (ini <= f_dt <= fin) or entry.link in vistos: continue
            vistos.add(entry.link)
            
            p = ia(entry.title[:512])[0]
            s_val = int(p['label'].split()[0])
            sent = "Negativo" if s_val <= 2 else "Neutro" if s_val == 3 else "Positivo"
            
            # Geo-Engine
            t_low = entry.title.lower()
            lat, lon, lug = -29.9027, -71.2519, "General"
            for k, v in GEO_DB.items():
                if k in t_low: lat, lon, lug = v[0], v[1], k.title(); break
            
            res.append({
                'Fecha': f_dt, 'Fuente': entry.source.title if 'source' in entry else "Digital",
                'Titular': entry.title, 'Sentimiento': sent, 'Link': entry.link,
                'Tipo': clasificar_redes(entry.link), 'Lat': lat, 'Lon': lon, 'Lugar': lug, 'Etiqueta': obj
            })
        prog.progress((i+1)/len(urls))
    prog.empty()
    return pd.DataFrame(res)

# --- 6. SIDEBAR ---
with st.sidebar:
    st.markdown("""<div class='lighthouse-wrap'><div class='light-beam'></div><div class='lighthouse'>⚓</div></div>""", unsafe_allow_html=True)
    st.title("EL FARO")
    
    with st.expander("💾 Mis Proyectos"):
        p_name = st.text_input("Nombre Proyecto")
        if st.button("Guardar"):
            st.session_state.proyectos[p_name] = {"obj": obj_main, "extra": ext_kw, "ini": f_ini, "fin": f_fin}
            st.success("Guardado")
        if st.session_state.proyectos:
            p_sel = st.selectbox("Cargar", list(st.session_state.proyectos.keys()))
            if st.button("Cargar"): st.info(f"Cargado {p_sel}. Pulse ENCENDER.")

    st.divider()
    modo = st.radio("Modo", ["Individual", "Versus"])
    obj_main = st.text_input("Objetivo", "Daniela Norambuena")
    obj_vs = st.text_input("Contra", "") if modo == "Versus" else None
    ext_kw = st.text_input("Extra", "seguridad, obras")
    c1, c2 = st.columns(2)
    f_ini, f_fin = c1.date_input("Desde", datetime.now()-timedelta(days=30)), c2.date_input("Hasta", datetime.now())
    
    if st.button("🔥 ENCENDER EL FARO"):
        with st.spinner("Minando redes y prensa regional..."):
            df_a = mineria_profunda(obj_main, f_ini, f_fin, ext_kw)
            st.session_state.data_master = df_a
            if modo == "Versus" and obj_vs:
                df_b = mineria_profunda(obj_vs, f_ini, f_fin, ext_kw)
                st.session_state.data_master = pd.concat([df_a, df_b], ignore_index=True)

# --- 7. PANEL DE CONTROL ---
df = st.session_state.data_master
if not df.empty:
    st.markdown(f"# 🛰️ Radar Activo: {obj_main}")
    tabs = st.tabs(["📊 ESTRATEGIA", "🗺️ GEO-TACTICAL", "🛠️ GESTIÓN", "📄 INFORME IA"])
    
    with tabs[0]:
        c1, c2, c3 = st.columns(3)
        c1.metric("Impactos", len(df))
        c2.metric("Positivos", len(df[df.Sentimiento=='Positivo']), "🟢")
        c3.metric("Riesgo", len(df[df.Sentimiento=='Negativo']), "🔴", delta_color="inverse")
        
        col_l, col_r = st.columns([2, 1])
        with col_l:
            fig = px.sunburst(df, path=['Sentimiento', 'Fuente', 'Titular'], color='Sentimiento', 
                              color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
            fig.update_layout(height=600, paper_bgcolor="rgba(0,0,0,0)", font_color="white")
            st.plotly_chart(fig, use_container_width=True)
            
        with col_r:
            st.subheader("🌡️ Reputación")
            pos, neg, tot = len(df[df.Sentimiento=='Positivo']), len(df[df.Sentimiento=='Negativo']), len(df)
            val = ((pos*100)+(tot-neg-pos)*50)/tot if tot > 0 else 0
            fig_g = go.Figure(go.Indicator(mode="gauge+number", value=val, gauge={'axis':{'range':[0,100], 'tickcolor':"white"}, 'bar':{'color':"#38bdf8"},
                                                                         'steps':[{'range':[0,40],'color':'#ef4444'},{'range':[40,60],'color':'#f59e0b'},{'range':[60,100],'color':'#10b981'}]}))
            fig_g.update_layout(height=350, paper_bgcolor="rgba(0,0,0,0)", font_color="white")
            st.plotly_chart(fig_g, use_container_width=True)

        st.subheader("🌳 Clima por Zona")
        fig_tree = px.treemap(df, path=['Lugar', 'Fuente', 'Titular'], color='Sentimiento', 
                              color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
        fig_tree.update_traces(textinfo="label+value", textfont=dict(size=20))
        st.plotly_chart(fig_tree, use_container_width=True)

    with tabs[1]:
        m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
        for _, r in df.iterrows():
            c = "green" if r.Sentimiento=='Positivo' else "red" if r.Sentimiento=='Negativo' else "orange"
            folium.Marker([r.Lat, r.Lon], popup=f"<a href='{r.Link}' target='_blank'>{r.Fuente}</a>", icon=folium.Icon(color=c)).add_to(m)
        st_folium(m, width="100%", height=600)

    with tabs[2]:
        st.subheader("Validación Humana (Edita Sentimientos)")
        df_edit = st.data_editor(df, column_config={"Link": st.column_config.LinkColumn("Ver"), "Sentimiento": st.column_config.SelectboxColumn("Sentimiento", options=["Positivo","Negativo","Neutro","Irrelevante"])}, use_container_width=True, key="editor_v18")
        st.session_state.data_master = df_edit

    with tabs[3]:
        if st.button("✍️ GENERAR INFORME ESTRATÉGICO"):
            p_perc = int(pos/tot*100) if tot>0 else 0
            txt_ia = f"""
            INFORME DE INTELIGENCIA EL FARO - ESTRATEGIA DIGITAL
            ====================================================
            OBJETIVO: {obj_main.upper()}
            RANGO ANALIZADO: {f_ini} al {f_fin}
            
            ANÁLISIS NARRATIVO:
            Durante el ciclo analizado, el motor Sentinel ha capturado un volumen de {tot} menciones. El clima de opinión es predominantemente {('Positivo' if pos>neg else 'Negativo')}, 
            presentando una favorabilidad del {p_perc}%. Se ha detectado una intensa actividad en la fuente '{df['Fuente'].mode()[0]}'.
            
            FOCOS TERRITORIALES:
            La conversación gira principalmente sobre {df['Lugar'].mode()[0]}, donde los conceptos de {ext_kw} han generado mayor tracción. 
            Es imperativo monitorear los focos críticos detectados en redes sociales para prevenir escaladas.
            
            RECOMENDACIÓN:
            {'Mantener la línea comunicacional actual.' if p_perc > 50 else 'Activar protocolo de respuesta en prensa regional y mitigar comentarios en TikTok/Reddit.'}
            
            Informe generado por Sentinel Engine v18.0.
            """
            st.text_area("Borrador:", txt_ia, height=400)
            
            # Gráfico para PDF
            fig_p, ax = plt.subplots(figsize=(6,4))
            df['Sentimiento'].value_counts().plot(kind='bar', ax=ax, color=['#10b981','#ef4444','#f59e0b'])
            plt.tight_layout()
            buf = io.BytesIO(); plt.savefig(buf, format='png'); buf.seek(0)

            pdf = FPDF()
            pdf.add_page(); pdf.set_font("Arial", 'B', 16); pdf.cell(0, 10, "REPORTE EL FARO", 0, 1, 'C')
            pdf.set_font("Arial", size=10); pdf.cell(0, 10, f"Rango: {f_ini} - {f_fin}", 0, 1, 'C')
            pdf.ln(10); pdf.set_font("Arial", size=11); pdf.multi_cell(0, 8, txt_ia.encode('latin-1','replace').decode('latin-1'))
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f_img:
                f_img.write(buf.getvalue()); pdf.image(f_img.name, x=50, w=110)
            
            tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            pdf.output(tmp_pdf.name)
            with open(tmp_pdf.name, "rb") as f: st.download_button("📥 BAJAR PDF", f, "Informe_Faro_Titan.pdf")
else:
    st.info("👋 Pulse ENCENDER EL FARO para iniciar el escaneo profundo.")
