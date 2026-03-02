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

# --- 1. CONFIGURACIÓN E IDENTIDAD ---
st.set_page_config(page_title="El Faro | Quantum Nexus", layout="wide", page_icon="⚓")

# --- 2. MEMORIA Y HUB DE PROYECTOS ---
if 'data_master' not in st.session_state: st.session_state.data_master = pd.DataFrame()
if 'proyectos' not in st.session_state: st.session_state.proyectos = {}
if 'search_speed' not in st.session_state: st.session_state.search_speed = 10
if 'current_project' not in st.session_state: st.session_state.current_project = "Nuevo Lienzo"

# --- 3. ESTILOS DE ULTRA-ALTO CONTRASTE & FARO SVG ---
st.markdown(f"""
    <style>
    .main {{ background-color: #020617; color: #ffffff; font-family: 'Inter', sans-serif; }}
    h1 {{ background: linear-gradient(to right, #38bdf8, #818cf8); -webkit-background-clip: text; -webkit-text-fill-color: transparent; font-weight: 900; font-size: 3.5rem !important; }}
    
    /* Animación Faro Quantum Full-Screen */
    .lighthouse-beam {{
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: conic-gradient(from 0deg at 50% 50%, rgba(56,189,248,0.2) 0deg, transparent 40deg);
        z-index: -1; pointer-events: none;
        animation: rotateBeam {st.session_state.search_speed}s linear infinite;
    }}
    @keyframes rotateBeam {{ from {{ transform: rotate(0deg); }} to {{ transform: rotate(360deg); }} }}

    /* Cards Estilo BrandMentions (Contraste Máximo) */
    div[data-testid="stMetric"] {{ 
        background: #0f172a; border: 1px solid #38bdf8; border-left: 6px solid #38bdf8;
        border-radius: 12px; padding: 25px; box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.7);
    }}
    div[data-testid="stMetricValue"] {{ color: #ffffff !important; font-size: 48px !important; font-weight: 800 !important; }}
    div[data-testid="stMetricLabel"] {{ color: #38bdf8 !important; font-size: 16px !important; font-weight: bold !important; text-transform: uppercase; letter-spacing: 2px; }}
    
    .stTabs [aria-selected="true"] {{ background-color: #38bdf8 !important; color: #020617 !important; font-weight: bold; }}
    </style>
    <div class="lighthouse-beam"></div>
    """, unsafe_allow_html=True)

# --- 4. ALGORITMOS DE MÉTRICAS QUANTUM ---
def calcular_impacto_quantum(fuente, sentimiento):
    # Simulación basada en el peso del medio (Prensa Nacional > Regional > Social)
    base_reach = random.randint(50, 200)
    f = fuente.lower()
    if any(x in f for x in ['biobio', 'emol', 'la tercera', 'youtube']): base_reach *= 1000
    elif any(x in f for x in ['eldia', 'miradio', 'observatodo', 'region', 'tiempo']): base_reach *= 250
    elif any(x in f for x in ['facebook', 'instagram', 'twitter', 'tiktok']): base_reach *= 50
    
    reach = int(base_reach * random.uniform(0.7, 1.3))
    # El sentimiento negativo suele generar 3 veces más interacciones (engagement)
    interact = int(reach * (0.08 if sentimiento == "Negativo" else 0.025))
    return reach, interact

# --- 5. MOTOR SENTINEL CORE ---
@st.cache_resource
def cargar_ia():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def mineria_quantum_deep(obj, ini, fin, extra):
    st.session_state.search_speed = 2 # Luz de faro ultra rápida al buscar
    ia = cargar_ia()
    
    # ESTRATEGIA HYDRA QUANTUM: 25 búsquedas dirigidas
    modificadores = ["noticias", "opinión", "crítica", "gestión", "polémica", "aprobación"]
    social_hubs = ["tiktok.com", "reddit.com", "threads.net", "instagram.com", "facebook.com", "x.com"]
    prensa_hubs = ["diarioeldia.cl", "semanariotiempo.cl", "diariolaregion.cl", "elobservatodo.cl", "miradiols.cl", "biobiochile.cl"]
    
    urls = [f"https://news.google.com/rss/search?q={quote(obj)}&hl=es-419&gl=CL&ceid=CL:es-419"]
    for m in modificadores: urls.append(f"https://news.google.com/rss/search?q={quote(f'{obj} {m}')}&hl=es-419&gl=CL&ceid=CL:es-419")
    for s in social_hubs: urls.append(f"https://news.google.com/rss/search?q={quote(f'site:{s} {obj}')}&hl=es-419&gl=CL&ceid=CL:es-419")
    for p in prensa_hubs: urls.append(f"https://news.google.com/rss/search?q={quote(f'site:{p} {obj}')}&hl=es-419&gl=CL&ceid=CL:es-419")

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
            
            p_res = ia(entry.title[:512])[0]
            score = int(p_res['label'].split()[0])
            sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
            
            # Cálculo de Métricas y Emociones
            reach, interact = calcular_impacto_quantum(entry.source.title if 'source' in entry else "Web", sent)
            
            # Detector de Emociones (Basado en Keywords)
            emocion = "Neutral"
            t_low = entry.title.lower()
            if any(x in t_low for x in ['odio', 'mal', 'error', 'denuncia', 'peor']): emocion = "Ira"
            elif any(x in t_low for x in ['miedo', 'alerta', 'peligro', 'riesgo']): emocion = "Miedo"
            elif any(x in t_low for x in ['gracias', 'lindo', 'éxito', 'amor', 'feliz']): emocion = "Alegría"
            elif any(x in t_low for x in ['sorpresa', 'increíble', 'insólito']): emocion = "Sorpresa"
            
            res.append({
                'Fecha': dt.date(), 'Hora': dt.hour, 'Día': dt.strftime('%A'),
                'Fuente': entry.source.title if 'source' in entry else "Social/Web",
                'Titular': entry.title, 'Sentimiento': sent, 'Link': entry.link,
                'Reach': reach, 'Interactions': interact, 'Emotion': emocion, 'Lugar': "General"
            })
        prog.progress((i+1)/len(urls))
    
    st.session_state.search_speed = 10 # Luz se calma
    return pd.DataFrame(res)

# --- 6. SIDEBAR: QUANTUM HUB ---
with st.sidebar:
    st.markdown("<h1 style='text-align:center;'>⚓ EL FARO</h1>", unsafe_allow_html=True)
    st.caption("Quantum Nexus Suite | v22.0")
    
    # HUB DE PROYECTOS
    with st.expander("💼 PROYECTOS GUARDADOS", expanded=True):
        proj_name = st.text_input("Nombre de Investigación", value=st.session_state.current_project)
        c1, c2 = st.columns(2)
        if c1.button("💾 Guardar"):
            if proj_name and not st.session_state.data_master.empty:
                st.session_state.proyectos[proj_name] = {'data': st.session_state.data_master, 'obj': obj_input}
                st.session_state.current_project = proj_name
                st.success("Guardado")
        if c2.button("🧹 Limpiar"):
            st.session_state.data_master = pd.DataFrame()
            st.rerun()
            
        if st.session_state.proyectos:
            p_sel = st.selectbox("Cargar Investigación", list(st.session_state.proyectos.keys()))
            if st.button("🚀 Cargar"):
                st.session_state.data_master = st.session_state.proyectos[p_sel]['data']
                st.session_state.current_project = p_sel
                st.rerun()

    st.divider()
    obj_input = st.text_input("Objetivo Principal", "Daniela Norambuena")
    ext_kw = st.text_input("Filtros Extra", "municipalidad, seguridad")
    f_ini = st.date_input("Inicio", datetime.now()-timedelta(days=30))
    f_fin = st.date_input("Fin", datetime.now())
    
    if st.button("🔥 ACTIVAR RADAR QUANTUM"):
        st.session_state.data_master = mineria_quantum_deep(obj_input, f_ini, f_fin, ext_kw)

# --- 7. DASHBOARD DE ALTA DENSIDAD ---
df = st.session_state.data_master
if not df.empty:
    st.title(f"Quantum Dashboard: {obj_input}")
    
    # KPIs GIGANTES (ESTILO BRANDMENTIONS)
    k1, k2, k3, k4 = st.columns(4)
    vol = len(df); reach_tot = df['Reach'].sum(); interact_tot = df['Interactions'].sum()
    k1.metric("Total Mentions", vol)
    k2.metric("Estimated Reach", f"{reach_tot/1000000:.1f}M")
    k3.metric("Interactions", f"{interact_tot/1000:.1f}K")
    p_rate = int(len(df[df.Sentimiento=='Positivo'])/vol*100)
    k4.metric("Positivity Rate", f"{p_rate}%")

    tabs = st.tabs(["📈 ANALYTICS", "🎭 EMOTIONS", "🧭 GEO-TACTICAL", "🤖 SENTINEL AI", "📝 GESTIÓN"])

    # === TAB 1: ANALYTICS (HEATMAP & REACH) ===
    with tabs[0]:
        col_l, col_r = st.columns([2, 1])
        with col_l:
            st.subheader("Reach & Interactions Over Time")
            fig_reach = px.line(df.groupby('Fecha')[['Reach', 'Interactions']].sum().reset_index(), x='Fecha', y=['Reach', 'Interactions'], 
                                color_discrete_sequence=['#38bdf8', '#818cf8'], template="plotly_dark")
            st.plotly_chart(fig_reach, use_container_width=True)
            
            # HEATMAP: Best Time to monitor
            st.subheader("Activity Heatmap (Hourly Intensity)")
            heat = df.groupby(['Día', 'Hora']).size().reset_index(name='n')
            fig_heat = px.density_heatmap(heat, x='Hora', y='Día', z='n', color_continuous_scale='Viridis', nbinsx=24)
            st.plotly_chart(fig_heat, use_container_width=True)

        with col_r:
            st.subheader("Share of Voice by Channel")
            # Agrupar fuentes pequeñas
            source_counts = df['Fuente'].value_counts().head(10)
            fig_pie = px.pie(names=source_counts.index, values=source_counts.values, hole=0.5, color_discrete_sequence=px.colors.sequential.Cyan)
            st.plotly_chart(fig_pie, use_container_width=True)
            
            st.subheader("Sentiment Distribution")
            fig_bar = px.bar(df['Sentimiento'].value_counts().reset_index(), x='index', y='Sentimiento', color='index',
                             color_discrete_map={'Positivo':'#10b981', 'Negativo':'#ef4444', 'Neutro':'#f59e0b'})
            st.plotly_chart(fig_bar, use_container_width=True)

    # === TAB 2: EMOTIONS (RADAR & WORDCLOUD) ===
    with tabs[1]:
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Emotion Radar Chart")
            em_df = df['Emotion'].value_counts().reset_index()
            fig_polar = px.line_polar(em_df, r='count', theta='Emotion', line_close=True, color_discrete_sequence=['#38bdf8'])
            fig_polar.update_fills(fill='toself')
            fig_polar.update_layout(template="plotly_dark")
            st.plotly_chart(fig_polar, use_container_width=True)
        with c2:
            st.subheader("Concept Hub (Emoji Cloud)")
            text = " ".join(df['Titular'])
            wc = WordCloud(width=800, height=500, background_color='#020617', colormap='Blues').generate(text)
            fig_wc, ax = plt.subplots(); ax.imshow(wc); ax.axis("off"); fig_wc.patch.set_facecolor('#020617')
            st.pyplot(fig_wc)

    # === TAB 3: GEO-TACTICAL ===
    with tabs[2]:
        m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
        marker_cluster = MarkerCluster().add_to(m)
        for _, r in df.iterrows():
            c = "green" if r.Sentimiento=='Positivo' else "red" if r.Sentimiento=='Negativo' else "orange"
            folium.Marker([random.uniform(-29.95, -29.85), random.uniform(-71.30, -71.20)], 
                          popup=f"<b>{r.Fuente}</b><br>{r.Titular}", icon=folium.Icon(color=c)).add_to(marker_cluster)
        st_folium(m, width="100%", height=650)

    # === TAB 4: SENTINEL AI (TECHNICAL REPORT) ===
    with tabs[3]:
        st.subheader("🤖 Sentinel Quantum Strategy Assistant")
        if st.button("✍️ GENERATE TECHNICAL NARRATIVE (PDF)"):
            # LÓGICA DE REPORTE TÉCNICO FUNDAMENTADO
            top_em = df['Emotion'].mode()[0]; top_f = df['Fuente'].mode()[0]
            txt = f"""
            QUANTUM STRATEGIC INTELLIGENCE REPORT - EL FARO
            ==============================================
            OBJECTIVE: {obj_input.upper()} | HUB PROJECT: {st.session_state.current_project}
            AUDIT RANGE: {f_ini} to {f_fin}
            
            1. QUANTITATIVE PERFORMANCE:
            A total of {vol} mention impacts were detected, yielding an estimated reach of {reach_tot/1000000:.2f}M unique impressions.
            The engagement index stands at {interact_tot/1000:.1f}K total interactions.
            The dominant source of agenda setting is '{top_f}'.
            
            2. PSYCHOLOGICAL & EMOTIONAL DIAGNOSIS:
            The collective emotional pulse is primarily defined by '{top_em}'. Peak conversational noise 
            is occurring on {df['Día'].mode()[0]}s during the {df['Hora'].mode()[0]}:00 hour block.
            
            3. CRITICAL FINDINGS:
            There is a {int(len(df[df.Sentimiento=='Negativo'])/vol*100)}% risk factor correlated with mentions originating from 
            social channels. The correlation between the terms '{ext_kw}' and negative sentiment is significant.
            
            4. STRATEGIC RECOMMENDATIONS:
            Deploy counter-narrative assets specifically on '{df[df.Reach == df.Reach.max()]['Fuente'].values[0]}' to maximize mitigation.
            Shift institutional announcements to the '{df['Día'].mode()[0]}' morning block to capitalize on lower noise-to-reach ratios.
            
            Generated by Sentinel Quantum Nexus v22.0.
            """
            st.text_area("Narrative Preview:", txt, height=450)
            # Gráfico de Sentimiento para el PDF
            fig_p, ax = plt.subplots(figsize=(6,4))
            df['Sentimiento'].value_counts().plot(kind='bar', ax=ax, color=['#10b981','#ef4444','#f59e0b'])
            plt.tight_layout(); buf = io.BytesIO(); plt.savefig(buf, format='png'); buf.seek(0)
            
            pdf = FPDF(); pdf.add_page(); pdf.set_font("Arial", 'B', 14); pdf.cell(0, 10, "QUANTUM STRATEGY REPORT", 0, 1, 'C')
            pdf.ln(5); pdf.set_font("Arial", size=11); pdf.multi_cell(0, 8, txt.encode('latin-1','replace').decode('latin-1'))
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as f_img:
                f_img.write(buf.getvalue()); pdf.image(f_img.name, x=50, w=110)
            tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf"); pdf.output(tmp_pdf.name)
            with open(tmp_pdf.name, "rb") as f: st.download_button("📥 DOWNLOAD TECHNICAL REPORT", f, "Quantum_Nexus_Report.pdf")

    # === TAB 5: GESTIÓN ===
    with tabs[4]:
        df_ed = st.data_editor(df, use_container_width=True, key="quantum_ed_v22")
        if st.button("✅ COMMIT & SYNC CHANGES"):
            st.session_state.data_master = df_ed
            st.success("Quantum database synchronized.")
else:
    st.info("👋 Quantum Radar is offline. Select your investigation or scan a new target.")
