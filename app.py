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
st.set_page_config(page_title="Sentinel Gold", layout="wide", page_icon="⚓")

# --- 2. MEMORIA Y ESTADO ---
COLS = ['Fecha', 'Fuente', 'Titular', 'Link', 'Sentimiento', 'Alcance', 'Interacciones', 'Vibra', 'Lugar', 'Tipo']
if 'data_master' not in st.session_state: st.session_state.data_master = pd.DataFrame(columns=COLS)
if 'proyectos' not in st.session_state: st.session_state.proyectos = {}
if 'search_active' not in st.session_state: st.session_state.search_active = False

# --- 3. ESTILOS GOLD (FONDO NEGRO PURO & FARO SVG) ---
speed = "2s" if st.session_state.search_active else "12s"

st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700;900&display=swap');
    
    /* FONDO NEGRO ABSOLUTO PARA EVITAR PROBLEMAS DE CONTRASTE */
    .stApp {{ background-color: #000000 !important; }}
    .main {{ background-color: #000000 !important; color: #FFFFFF !important; font-family: 'Montserrat', sans-serif; }}
    
    /* TEXTOS GLOBALES */
    h1, h2, h3, h4, p, li, span {{ color: #FFFFFF !important; }}
    
    /* TABS */
    .stTabs [aria-selected="true"] {{
        background-color: #00F0FF !important;
        color: #000000 !important;
        font-weight: 900 !important;
    }}
    
    /* KPI CARDS CUSTOM HTML - BLINDADOS */
    .kpi-container {{
        display: flex; justify-content: space-between; gap: 15px; margin-bottom: 20px;
    }}
    .kpi-box {{
        background: #111; border: 1px solid #00F0FF; border-radius: 10px; padding: 20px;
        width: 100%; text-align: center; box-shadow: 0 0 10px rgba(0, 240, 255, 0.2);
    }}
    .kpi-title {{ font-size: 12px; color: #aaa; text-transform: uppercase; letter-spacing: 1px; font-weight: bold; }}
    .kpi-num {{ font-size: 40px; color: #fff; font-weight: 900; margin: 10px 0; text-shadow: 0 0 10px #00F0FF; }}
    .kpi-sub {{ font-size: 14px; color: #00F0FF; font-weight: bold; }}

    /* FARO SVG ANIMADO (ENCAPSULADO) */
    .faro-wrapper {{
        position: relative; width: 100%; height: 200px;
        background: radial-gradient(circle at bottom, #1a1a1a 0%, #000 70%);
        border-bottom: 2px solid #00F0FF; margin-bottom: 20px;
        overflow: hidden;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 4. MOTORES INTELLIGENCIA ---
@st.cache_resource
def load_engine():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def normalizar_datos(txt, ia):
    res = ia(txt[:512])[0]
    sc = int(res['label'].split()[0])
    s = "🔴 Negativo" if sc <= 2 else "🟡 Neutro" if sc == 3 else "🟢 Positivo"
    
    tl = txt.lower()
    emo = "👁️ Expectativa"
    if any(x in tl for x in ['miedo','terror','delito']): emo = "😱 Miedo"
    elif any(x in tl for x in ['ira','odio','vergüenza','robo']): emo = "🤬 Ira"
    elif any(x in tl for x in ['feliz','éxito','logro']): emo = "🎉 Alegría"
    elif any(x in tl for x in ['triste','pena']): emo = "😢 Tristeza"
    elif s == "🟢 Positivo": emo = "🤝 Confianza"
    
    lug = "La Serena"
    if "coquimbo" in tl: lug = "Coquimbo"
    if "compañías" in tl: lug = "Las Compañías"
    
    return s, emo, lug

def run_scan_gold(obj, ini, fin, exclude, sources):
    st.session_state.search_active = True
    ia = load_engine()
    
    base_rss = "https://news.google.com/rss/search?q={}&hl=es-419&gl=CL&ceid=CL:es-419"
    queries = [obj, f"{obj} noticias", f"{obj} polémica"]
    
    sites = []
    if "Prensa" in sources: sites.extend(["diarioeldia.cl", "biobiochile.cl", "emol.com"])
    if "Redes" in sources: sites.extend(["tiktok.com", "instagram.com", "facebook.com", "twitter.com"])
    
    urls = []
    for q in queries: urls.append(base_rss.format(quote(q)))
    for s in sites: urls.append(base_rss.format(quote(f"site:{s} {obj}")))
    
    res = []
    seen = set()
    prog = st.progress(0)
    
    for i, u in enumerate(urls):
        feed = feedparser.parse(u)
        for entry in feed.entries:
            if exclude and exclude.lower() in entry.title.lower(): continue
            if entry.link in seen: continue
            seen.add(entry.link)
            
            try: dt = datetime.fromtimestamp(time.mktime(entry.published_parsed))
            except: dt = datetime.now()
            
            if not (ini <= dt.date() <= fin): continue
            
            s, e, l = normalizar_datos(entry.title, ia)
            src = entry.source.title if 'source' in entry else "Web"
            typ = "Red Social" if any(x in src.lower() for x in ['tiktok','instagram','facebook','twitter']) else "Prensa"
            
            # Métricas Simuladas
            base = 50000 if typ == "Prensa" else 2000
            alc = int(base * random.uniform(0.5, 2.0))
            inter = int(alc * (0.05 if s == "🔴 Negativo" else 0.02))
            
            res.append({
                'Fecha': dt.date(), 'Hora': dt.hour, 'Dia': dt.strftime('%A'),
                'Fuente': src, 'Titular': entry.title, 'Link': entry.link,
                'Sentimiento': s, 'Alcance': alc, 'Interacciones': inter,
                'Vibra': e, 'Lugar': l, 'Tipo': typ
            })
        prog.progress((i+1)/len(urls))
    
    st.session_state.search_active = False
    return pd.DataFrame(res)

# --- 5. SIDEBAR (FARO REAL + FILTROS) ---
with st.sidebar:
    # EL FARO SVG QUE TE GUSTA (Encapsulado para no parpadear)
    faro_html = f"""
    <div style="width:100%; height:200px; background:radial-gradient(circle at bottom, #111 0%, #000 80%); position:relative; overflow:hidden; border-bottom:2px solid #00F0FF; margin-bottom:20px; display:flex; justify-content:center; align-items:flex-end;">
        <div style="position:absolute; bottom:80px; left:50%; margin-left:-300px; width:600px; height:600px; 
             background:conic-gradient(from 0deg at 50% 50%, rgba(0,240,255,0.4) 0deg, transparent 60deg);
             transform-origin:50% 50%; animation: spin {speed} linear infinite;"></div>
        
        <svg width="80px" height="140px" viewBox="0 0 100 200" style="position:relative; z-index:10; filter:drop-shadow(0 0 10px #00F0FF);">
            <path d="M35,190 L65,190 L60,50 L40,50 Z" fill="#E2E8F0" stroke="#38BDF8" stroke-width="2"/>
            <rect x="35" y="30" width="30" height="20" fill="#FACC15" rx="2" stroke="#FACC15"/>
            <path d="M30,30 L50,10 L70,30 Z" fill="#0F172A" stroke="#38BDF8" stroke-width="2"/>
            <rect x="42" y="50" width="16" height="140" fill="#64748B" opacity="0.3"/>
        </svg>
        <style>@keyframes spin {{ 0% {{transform: rotate(0deg);}} 100% {{transform: rotate(360deg);}} }}</style>
    </div>
    """
    components.html(faro_html, height=200)
    
    st.title("EL FARO")
    st.caption("Sentinel Gold v40.0")
    
    obj_in = st.text_input("Objetivo", "Daniela Norambuena")
    
    with st.expander("🛠️ Filtros Avanzados", expanded=True):
        exclude_in = st.text_input("Excluir", placeholder="Ej: sorteo")
        src_in = st.multiselect("Fuentes", ["Prensa", "Redes"], default=["Prensa", "Redes"])
        d_ini = st.date_input("Desde", datetime.now()-timedelta(days=30))
        d_fin = st.date_input("Hasta", datetime.now())
        
    if st.button("🔥 ESCANEAR RED"):
        st.session_state.data_master = run_scan_gold(obj_in, d_ini, d_fin, exclude_in, src_in)

    with st.expander("📂 Archivos"):
        p_name = st.text_input("Nombre Archivo")
        if st.button("Guardar"):
            st.session_state.proyectos[p_name] = st.session_state.data_master
            st.success("Guardado")
        if st.session_state.proyectos:
            sel = st.selectbox("Cargar", list(st.session_state.proyectos.keys()))
            if st.button("Abrir"):
                st.session_state.data_master = st.session_state.proyectos[sel]
                st.rerun()

# --- 6. DASHBOARD ---
df = st.session_state.data_master
if not df.empty:
    st.markdown(f"## 🔭 Centro de Mando: {obj_in.upper()}")
    
    # 6.1 KPIs HTML BLINDADOS
    vol = len(df)
    alc = df['Alcance'].sum()
    inter = df['Interacciones'].sum()
    pos = len(df[df.Sentimiento.str.contains("Positivo")])
    fav = int(pos/vol*100) if vol > 0 else 0
    
    st.markdown(f"""
    <div class="kpi-container">
        <div class="kpi-box"><div class="kpi-title">Menciones</div><div class="kpi-num">{vol}</div><div class="kpi-sub">Impactos Únicos</div></div>
        <div class="kpi-box"><div class="kpi-title">Alcance</div><div class="kpi-num">{alc/1000000:.1f}M</div><div class="kpi-sub">Impresiones</div></div>
        <div class="kpi-box"><div class="kpi-title">Interacciones</div><div class="kpi-num">{inter/1000:.1f}K</div><div class="kpi-sub">Engagement</div></div>
        <div class="kpi-box"><div class="kpi-title">Favorabilidad</div><div class="kpi-num" style="color:#00FF00;">{fav}%</div><div class="kpi-sub">Positividad</div></div>
    </div>
    """, unsafe_allow_html=True)
    
    tabs = st.tabs(["📊 ESTRATEGIA", "🎭 EMOCIONES", "🗺️ TÁCTICO", "🌪️ EMBUDO", "📄 REPORTE"])
    
    # === TAB 1: ESTRATEGIA (CORREGIDO: ERROR FIG LINE) ===
    with tabs[0]:
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown("### 🕸️ Ecosistema")
            fig_sun = px.sunburst(df, path=['Sentimiento', 'Fuente', 'Titular'], color='Sentimiento',
                                  color_discrete_map={'🟢 Positivo':'#00FF00', '🔴 Negativo':'#FF0000', '🟡 Neutro':'#FFFF00'})
            fig_sun.update_traces(textinfo="label+percent entry", textfont=dict(size=14))
            fig_sun.update_layout(height=500, paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"))
            st.plotly_chart(fig_sun, use_container_width=True)
        with c2:
            st.markdown("### 📈 Tendencia")
            daily = df.groupby('Fecha').size().reset_index(name='Menciones')
            # FIX DEL ERROR: Sintaxis limpia para grafico de area
            fig_line = px.area(daily, x='Fecha', y='Menciones', template="plotly_dark")
            fig_line.update_traces(line_color='#00F0FF', fill_color='rgba(0, 240, 255, 0.2)')
            fig_line.update_layout(height=500, paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_line, use_container_width=True)
            
        st.markdown("### 🌳 Treemap de Conceptos")
        fig_tree = px.treemap(df, path=['Lugar', 'Fuente', 'Titular'], color='Sentimiento',
                              color_discrete_map={'🟢 Positivo':'#00FF00', '🔴 Negativo':'#FF0000', '🟡 Neutro':'#FFFF00'})
        # Textos grandes 28px
        fig_tree.update_traces(textinfo="label+value", textfont=dict(size=28))
        fig_tree.update_layout(height=600, margin=dict(t=0,l=0,r=0,b=0), paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white"))
        st.plotly_chart(fig_tree, use_container_width=True)

    # === TAB 2: EMOCIONES ===
    with tabs[1]:
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("### 📡 Radar Emocional")
            e_c = df['Vibra'].value_counts().reset_index()
            e_c.columns = ['Vibra', 'Count']
            fig_r = px.line_polar(e_c, r='Count', theta='Vibra', line_close=True, template="plotly_dark")
            fig_r.update_traces(fill='toself', line_color='#00F0FF')
            fig_r.update_layout(paper_bgcolor="rgba(0,0,0,0)", height=450)
            st.plotly_chart(fig_r, use_container_width=True)
        with c4:
            st.markdown("### 🥧 Share")
            fig_p = px.pie(df, names='Fuente', hole=0.5, color_discrete_sequence=px.colors.sequential.Cyan)
            fig_p.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_p, use_container_width=True)

    # === TAB 3: TÁCTICO (MAPA OSCURO) ===
    with tabs[2]:
        st.markdown("### 📍 Despliegue")
        m = folium.Map(location=[-29.90, -71.25], zoom_start=12, tiles="CartoDB dark_matter")
        mc = MarkerCluster().add_to(m)
        for _, r in df.iterrows():
            c = "green" if "Positivo" in r['Sentimiento'] else "red" if "Negativo" in r['Sentimiento'] else "orange"
            folium.Marker([random.uniform(-29.95,-29.85), random.uniform(-71.3,-71.2)], 
                          popup=r['Titular'], icon=folium.Icon(color=c)).add_to(mc)
        st_folium(m, width="100%", height=500)

    # === TAB 4: EMBUDO & DATA ===
    with tabs[3]:
        c5, c6 = st.columns([1, 1])
        with c5:
            st.markdown("### 🌪️ Embudo de Conversión")
            fig_fun = px.funnel(pd.DataFrame({
                'Etapa': ['Alcance', 'Lecturas', 'Interacción', 'Viral'],
                'Valor': [alc, alc*0.2, inter, inter*0.1]
            }), x='Valor', y='Etapa')
            fig_fun.update_traces(marker=dict(color=["#00F0FF", "#00BFFF", "#1E90FF", "#0000FF"]))
            fig_fun.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_fun, use_container_width=True)
        
        with c6:
            st.markdown("### 📝 Antecedentes")
            with st.form("manual"):
                txt = st.text_area("Texto")
                src = st.text_input("Fuente")
                if st.form_submit_button("💾 GUARDAR"):
                    new = df.iloc[0].to_dict()
                    new['Titular'] = txt; new['Fuente'] = src; new['Tipo'] = 'Manual'
                    st.session_state.data_master = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
                    st.success("Guardado")
                    st.rerun()

    # === TAB 5: REPORTE ===
    with tabs[4]:
        st.markdown("### 📄 Generador C-Level")
        risk = "ALTO" if fav < 50 else "BAJO"
        txt_ia = f"""
        INFORME TÉCNICO SENTINEL
        ========================
        OBJETIVO: {obj_in.upper()}
        RIESGO: {risk}
        
        1. ANÁLISIS: Se han procesado {vol} menciones con un alcance de {alc/1000000:.1f}M.
        2. TENDENCIA: La emoción dominante es {df['Vibra'].mode()[0]}.
        3. ACCIÓN: Se recomienda reforzar presencia en {df['Fuente'].mode()[0]}.
        """
        st.text_area("Reporte:", txt_ia, height=300)
        if st.button("DESCARGAR PDF"):
            pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", size=12); pdf.multi_cell(0, 10, txt_ia)
            out = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            pdf.output(out.name)
            with open(out.name, "rb") as f: st.download_button("📥 BAJAR PDF", f, "reporte.pdf")

else:
    st.info("👋 Inicia el escaneo en el panel lateral.")
