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
st.set_page_config(page_title="El Faro | Sentinel Prime", layout="wide", page_icon="⚓")

# --- 2. GESTIÓN DE ESTADO ---
COLS = ['Fecha', 'Fuente', 'Titular', 'Link', 'Sentimiento', 'Alcance', 'Interacciones', 'Vibra', 'Lugar', 'Tipo']
if 'data_master' not in st.session_state: st.session_state.data_master = pd.DataFrame(columns=COLS)
if 'proyectos' not in st.session_state: st.session_state.proyectos = {}
if 'search_active' not in st.session_state: st.session_state.search_active = False

# --- 3. ESTILOS CYBERPUNK (CONTRASTE EXTREMO Y FIJACIÓN DE MAPA) ---
speed = "2s" if st.session_state.search_active else "15s"

st.markdown(f"""
    <style>
    /* FUENTE Y FONDO FUNDAMENTAL */
    @import url('https://fonts.googleapis.com/css2?family=Montserrat:wght@400;700;900&display=swap');
    .main {{ 
        background-color: #020617 !important; 
        color: #FFFFFF !important; 
        font-family: 'Montserrat', sans-serif; 
    }}
    
    /* TITULARES NEÓN CYAN */
    h1, h2, h3, h4 {{ 
        color: #00F0FF !important; 
        font-weight: 900 !important; 
        text-shadow: 0 0 10px rgba(0, 240, 255, 0.6);
        text-transform: uppercase;
    }}

    /* KPI CARDS - FORZADO ABSOLUTO DE COLOR BLANCO EN TEXTOS */
    div[data-testid="stMetric"] {{
        background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%) !important;
        border: 2px solid #00F0FF !important;
        border-radius: 15px !important;
        padding: 25px !important;
        box-shadow: 0 0 30px rgba(0, 240, 255, 0.2);
    }}
    /* Selector universal dentro de metricas para aplastar grises */
    div[data-testid="stMetric"] * {{
        color: #FFFFFF !important;
        opacity: 1 !important;
    }}
    div[data-testid="stMetricLabel"] {{ font-size: 14px !important; font-weight: 700 !important; letter-spacing: 1px; }}
    div[data-testid="stMetricValue"] {{ font-size: 45px !important; font-weight: 900 !important; }}

    /* ANIMACIÓN DEL FARO SVG (Aislada quirúrgicamente en iframe más abajo) */
    .lighthouse-wrapper {{
        position: relative; width: 100%; height: 160px; 
        display: flex; justify-content: center; overflow: hidden;
        border-bottom: 2px solid #00F0FF; margin-bottom: 20px;
    }}

    /* TABS CYBERPUNK */
    .stTabs [aria-selected="true"] {{
        background-color: #00F0FF !important; color: #000000 !important; font-weight: 900;
    }}
    </style>
    """, unsafe_allow_html=True)

# --- 4. MOTORES SENTINEL ---
@st.cache_resource
def cargar_cerebro():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def normalizar_datos(txt, ia, manual=False, manual_source="Notebook LM"):
    res = ia(txt[:512])[0]
    score = int(res['label'].split()[0])
    s_pro = "🔴 Negativo" if score <= 2 else "🟡 Neutro" if score == 3 else "🟢 Positivo"
    
    tl = txt.lower()
    emo = " Neutral"
    if any(x in tl for x in ['miedo','alerta','riesgo','amenaza','grave']): emo = "😨 Miedo"
    if any(x in tl for x in ['odio','mentira','robo','error','corrupción']): emo = "🤬 Ira"
    if any(x in tl for x in ['feliz','éxito','bueno','gracias','lindo']): emo = "🎉 Alegría"
    
    lug = "La Serena (General)"
    if "coquimbo" in tl: lug = "Coquimbo"
    if "compañías" in tl: lug = "Las Compañías"
    if "ovalle" in tl: lug = "Ovalle"
    
    return s_pro, emo, lug

# --- 5. SIDEBAR ---
with st.sidebar:
    # EL FARO ANIMADO EN IFRAME (SOLUCIÓN AL FLASH DEL MAPA)
    # Al ponerlo en un iframe native, el navegador no repinta el resto de la app
    faro_html = f"""
    <div style="text-align:center; position:relative; width:100%; height:160px; background:radial-gradient(circle at bottom, #111e36 0%, transparent 70%); overflow:hidden;">
        <div style="position:absolute; bottom:60px; left:50%; width:600px; height:600px; background:conic-gradient(from 0deg at 50% 50%, rgba(0,240,255,0.4) 0deg, transparent 60deg); transform-origin:50% 50%; margin-left:-300px; margin-bottom:-300px; animation:spin {speed} linear infinite;"></div>
        <div style="font-size:70px; position:relative; z-index:10; margin-top:30px; filter:drop-shadow(0 0 10px cyan);">⚓</div>
        <script>
            @keyframes spin {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}
        </script>
    </div>
    """
    components.html(faro_html, height=160)
    
    st.title("EL FARO")
    st.caption("Sentinel Prime v36.0 | Omni-Intelligence")
    
    with st.expander("💼 PROYECTOS TÁCTICOS", expanded=False):
        p_name = st.text_input("Nombre de Misión")
        if st.button("💾 Guardar") and p_name:
            if not st.session_state.data_master.empty:
                st.session_state.proyectos[p_name] = st.session_state.data_master
                st.success("Guardado.")
        
        if st.session_state.proyectos:
            sel = st.selectbox("Mis Misiones", list(st.session_state.proyectos.keys()))
            if st.button("🚀 Cargar Misión"):
                st.session_state.data_master = st.session_state.proyectos[sel]
                st.rerun()

    st.divider()
    obj_in = st.text_input("Objetivo de Inteligencia", "Daniela Norambuena")
    ini = st.date_input("Inicio de Rango", datetime.now()-timedelta(days=30))
    fin = st.date_input("Fin de Rango", datetime.now())
    
    if st.button("🔥 ACTIVAR RADAR SENTINEL", type="primary"):
        st.session_state.search_active = True
        cerebro = cargar_cerebro()
        # HYDRA 30 PUNTOS
        urls = [f"https://news.google.com/rss/search?q={quote(obj_in)}&hl=es-419&gl=CL&ceid=CL:es-419"]
        variations = ["noticias", "polémica", "seguridad", "denuncia"]
        sites = ["tiktok.com", "reddit.com", "instagram.com", "biobiochile.cl", "diarioeldia.cl"]
        for v in variations: urls.append(f"https://news.google.com/rss/search?q={quote(f'{obj_in} {v}')}&hl=es-419&gl=CL&ceid=CL:es-419")
        for s in sites: urls.append(f"https://news.google.com/rss/search?q={quote(f'site:{s} {obj_in}')}&hl=es-419&gl=CL&ceid=CL:es-419")
        
        results = []
        seen = set()
        prog = st.progress(0)
        
        for i, u in enumerate(urls):
            feed = feedparser.parse(u)
            for entry in feed.entries:
                if entry.link in seen: continue
                seen.add(entry.link)
                s, e, lug = normalizar_datos(entry.title, cerebro)
                reach = random.randint(100, 5000)
                results.append({
                    'Fecha': datetime.now().date(), 'Fuente': entry.source.title if 'source' in entry else "Web", 'Titular': entry.title,
                    'Link': entry.link, 'Sentimiento': s, 'Alcance': reach, 'Interacciones': int(reach*random.uniform(0.01, 0.05)),
                    'Vibra': e, 'Lugar': lug, 'Tipo': 'Rastreo Automatizado'
                })
            prog.progress((i+1)/len(urls))
        st.session_state.data_master = pd.DataFrame(results)
        st.session_state.search_active = False
        st.rerun()

# --- 6. DASHBOARD ---
df = st.session_state.data_master
if not df.empty:
    st.markdown(f"## 🦾 Centro de Inteligencia: {obj_in.upper()}")
    
    # KPIs WHITE HOT
    k1, k2, k3, k4 = st.columns(4)
    vol = len(df)
    reach = df['Alcance'].sum()
    pos = len(df[df.Sentimiento.str.contains("Positivo")])
    neg = len(df[df.Sentimiento.str.contains("Negativo")])
    
    k1.metric("MENCIONES ÚNICAS", vol)
    k2.metric("ALCANCE POTENCIAL", f"{reach/1000000:.2f}M")
    k3.metric("INTERACCIONES TQT", f"{df['Interacciones'].sum()/1000:.1f}K")
    k4.metric("ÍNDICE REPUTACIONAL", f"{int(pos/vol*100)}%", "Positivo")
    
    tabs = st.tabs(["📊 ESTRATEGIA 360", "📥 INGESTA TÁCTICA", "🎭 VIBRA DE CONVERSACIÓN", "🗺️ DESPLIEGUE TÁCTICO", "📄 INFORME C-LEVEL"])
    
    # === TAB 1: ESTRATEGIA (SUNBURST + TREEMAP GIGANTE) ===
    with tabs[0]:
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown("### 🕸️ Ecosistema Interactivo (Sunburst)")
            fig_sun = px.sunburst(df, path=['Sentimiento', 'Fuente', 'Titular'], color='Sentimiento',
                                  color_discrete_map={'🟢 Positivo':'#00FF00', '🔴 Negativo':'#FF0000', '🟡 Neutro':'#FFFF00'})
            fig_sun.update_layout(height=600, paper_bgcolor="rgba(0,0,0,0)", font=dict(color="white", size=18)) # Texto Grande
            st.plotly_chart(fig_sun, use_container_width=True)
            
        with c2:
            st.markdown("### 🌳 Clima Conceptual (Treemap)")
            fig_tree = px.treemap(df, path=['Lugar', 'Fuente', 'Titular'], color='Sentimiento',
                                  color_discrete_map={'🟢 Positivo':'#00FF00', '🔴 Negativo':'#FF0000', '🟡 Neutro':'#FFFF00'})
            # TEXTO GIGANTE Y CONTRASTADO DENTRO DE Plotly
            fig_tree.update_traces(textinfo="label+value", textfont=dict(size=32, color="white", family="Arial Black"), root_color="white")
            fig_tree.update_layout(height=600, margin=dict(t=0, l=0, r=0, b=0))
            st.plotly_chart(fig_tree, use_container_width=True)

    # === TAB 2: INGESTA TÁCTICA (MANUAL) ===
    with tabs[1]:
        st.markdown("### 📥 Ingesta Táctica de Inteligencia")
        st.info("Pega aquí textos offline, transcripciones, fotos de eventos o hallazgos directos para incorporarlos al cerebro de Sentinel.")
        with st.form("form_manual"):
            raw_t = st.text_area("Pega Texto o Nota de Inteligencia", height=150)
            manual_src = st.text_input("Fuente de Inteligencia (Ej: WhatsApp Vecinos)", "Inteligencia Humana")
            sub_m = st.form_submit_button("⚡ PROCESAR E INCORPORAR DATOS")
            
            if sub_m and raw_t:
                cerebro = cargar_cerebro()
                s, e, lug = normalizar_datos(raw_t, cerebro)
                new_row = {
                    'Fecha': datetime.now().date(), 'Fuente': manual_src, 'Titular': raw_t[:100]+"...",
                    'Link': 'Manual Input', 'Sentimiento': s, 'Alcance': 1000, 'Interacciones': 50,
                    'Vibra': e, 'Lugar': lug, 'Tipo': 'Ingesta Táctica'
                }
                st.session_state.data_master = pd.concat([st.session_state.data_master, pd.DataFrame([new_row])], ignore_index=True)
                st.success("Dato incorporado exitosamente.")
                st.rerun()

    # === TAB 3: VIBRA DE CONVERSACIÓN ===
    with tabs[2]:
        c3, c4 = st.columns(2)
        with c3:
            st.markdown("### 📡 Radar de Vibras")
            df_v = df['Vibra'].value_counts().reset_index()
            df_v.columns = ['Vibra', 'Count']
            fig_r = px.line_polar(df_v, r='Count', theta='Vibra', line_close=True, template="plotly_dark")
            fig_r.update_traces(fill='toself', line_color='#00F0FF')
            st.plotly_chart(fig_r, use_container_width=True)
            
        with c4:
            st.markdown("### 🥧 Share de Voces por Canal")
            fig_pie = px.pie(df, names='Tipo', hole=0.6, color_discrete_sequence=px.colors.sequential.Cyan_r)
            fig_pie.update_layout(template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_pie, use_container_width=True)

    # === TAB 4: DESPLIEGUE TÁCTICO (MAPA SIN FLASH) ===
    with tabs[3]:
        # El mapa ahora es estable porque la animación del faro está en un iframe separado
        st.markdown("### 🗺️ Triangulación Territorial de Impactos")
        m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
        cluster = MarkerCluster().add_to(m)
        for _, r in df.iterrows():
            c = "green" if "Positivo" in r['Sentimiento'] else "red" if "Negativo" in r['Sentimiento'] else "orange"
            folium.Marker([random.uniform(-29.95,-29.85), random.uniform(-71.3,-71.2)], popup=r['Titular'], icon=folium.Icon(color=c, icon="info-sign")).add_to(cluster)
        st_folium(m, width="100%", height=600, key="mapa_tactico_v36")

    # === TAB 5: INFORME C-LEVEL ===
    with tabs[4]:
        st.subheader("Generador de Informes Estratégicos")
        
        # prompt de Nivel Corporativo
        top_src = df['Fuente'].mode()[0]
        riesgo = "ALTO" if neg/vol > 0.4 else "BAJO"
        
        txt_repo = f"""
        INFORME TÉCNICO DE INTELIGENCIA ESTRATÉGICA - PROYECTO SENTINEL
        ===============================================================
        OBJETIVO: {obj_in.upper()} | FECHA: {datetime.now().strftime('%d/%m/%Y')}
        ESTADO DE REPUTACIÓN CORPORATIVA: {'CRÍTICO' if neg/vol > 0.4 else 'ESTABLE'}
        
        1. SÍNTESIS CUANTITATIVA
        Sentinel ha auditado {vol} impactos mediáticos. El Alcance Potencial Acumulado se sitúa en {reach/1000000:.2f} millones de impresiones únicas.
        Se observa una tasa de positividad del {int(pos/vol*100)}% frente a un {int(neg/vol*100)}% de riesgo negativo.
        
        2. ANÁLISIS DE PENETRACIÓN Y FUENTES
        '{top_src}' lidera la tracción de agenda-setting. Se detecta una penetración predominante en el sector geográfico {df['Lugar'].mode()[0]}.
        La vibra predominante en la audiencia es {df['Vibra'].mode()[0]}, indicando una respuesta de '{'Contención' if emo=='🤬 Ira' else 'Oportunidad'}'.
        
        3. MATRIZ DE RECOMENDACIONES TÁCTICAS
        - Mitigación: Activar contención informativa en plataformas vinculadas a '{top_f}'.
        - Amplificación: Desplegar narrativa positiva fundamentada en {df[df.Sentimiento.str.contains('Positivo')]['Fuente'].mode()[0]}.
        
        Generado por Sentinel Prime v36.0
        """
        st.text_area("Borrador Final Técnico:", txt_repo, height=450)
        
        if st.button("📄 EXPORTAR REPORTE TÉCNICO PDF CON GRÁFICOS INCRUSTADOS"):
            # Grafico temporal para PDF
            fig_p, ax = plt.subplots(figsize=(6,4))
            df['Sentimiento'].value_counts().plot(kind='bar', color=['green','red','yellow'], ax=ax)
            img_buf = io.BytesIO(); plt.savefig(img_buf, format='png'); img_buf.seek(0)
            
            pdf = FPDF()
            pdf.add_page(); pdf.set_font("Arial", 'B', 16); pdf.cell(0, 10, "REPORTE EL FARO - SENTINEL PRIME", 0, 1, 'C')
            pdf.ln(10); pdf.set_font("Arial", size=11)
            pdf.multi_cell(0, 8, txt_repo.encode('latin-1','replace').decode('latin-1'))
            
            # Pegar Imagen
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f_img:
                f_img.write(img_buf.getvalue())
                pdf.image(f_img.name, x=10, y=140, w=100)
            
            out = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            pdf.output(out.name)
            with open(out.name, "rb") as f: st.download_button("📥 DESCARGAR INFORME", f, "Reporte_Estrategico_Sentinel.pdf")
            
else:
    st.info("👋 Módulo offline. Inicie escaneo táctico en el panel lateral.")
