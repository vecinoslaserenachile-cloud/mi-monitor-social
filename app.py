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

# --- 1. CONFIGURACIÓN E IDENTIDAD ---
st.set_page_config(
    page_title="El Faro | Sentinel Intelligence", 
    layout="wide", 
    page_icon="️lighthouse",
    initial_sidebar_state="collapsed"
)

# --- 2. ESTILOS PRO (NEON & GLASS) ---
st.markdown("""
    <style>
    /* Fondo Oscuro Profundo */
    .main { background: #0f172a; color: #e2e8f0; }
    
    /* Títulos */
    h1 { 
        background: linear-gradient(to right, #0ea5e9, #22d3ee); 
        -webkit-background-clip: text; 
        -webkit-text-fill-color: transparent; 
        font-weight: 900; letter-spacing: -1px;
    }
    h2, h3 { color: #f1f5f9 !important; }
    
    /* Métricas */
    div[data-testid="stMetric"] {
        background: rgba(30, 41, 59, 0.7);
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-radius: 12px;
        padding: 15px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    
    /* Botones */
    .stButton>button {
        background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
        color: white; border: none; padding: 12px 24px;
        border-radius: 8px; font-weight: 600; text-transform: uppercase;
        box-shadow: 0 10px 15px -3px rgba(37, 99, 235, 0.4);
        width: 100%;
    }
    .stButton>button:hover { transform: scale(1.02); }
    
    /* Tabs */
    .stTabs [aria-selected="true"] {
        background-color: #0ea5e9 !important;
        color: white !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. MEMORIA ---
if 'data_raw' not in st.session_state:
    st.session_state.data_raw = pd.DataFrame(columns=['Fecha', 'Fuente', 'Titular', 'Sentimiento', 'Link', 'Score', 'Tipo', 'Lat', 'Lon', 'Lugar', 'Manual'])

# --- 4. GEODATA (AMPLIADA) ---
GEO_DB = {
    "avenida del mar": [-29.9168, -71.2785], "faro": [-29.9073, -71.2847], "centro": [-29.9027, -71.2519],
    "plaza de armas": [-29.9027, -71.2519], "las compañías": [-29.8783, -71.2389], "tierras blancas": [-29.9392, -71.2294],
    "coquimbo": [-29.9533, -71.3436], "ovalle": [-30.6015, -71.2003], "vicuña": [-30.0319, -70.7081],
    "aeropuerto": [-29.9161, -71.1994], "la florida": [-29.9238, -71.2185], "el milagro": [-29.9333, -71.2333],
    "serena": [-29.9027, -71.2519], "región": [-29.95, -71.3], "municipalidad": [-29.9045, -71.2489],
    "hospital": [-29.9150, -71.2550], "ruta 5": [-29.88, -71.26], "caleta": [-29.94, -71.33]
}

# --- 5. MOTOR DE INTELIGENCIA ---
@st.cache_resource
def cargar_cerebro():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def detectar_lugar(texto):
    texto = texto.lower()
    for lugar, coords in GEO_DB.items():
        if lugar in texto: return coords[0], coords[1], lugar.title()
    # Random ligero para evitar superposición exacta en el mapa
    return -29.9027 + random.uniform(-0.02, 0.02), -71.2519 + random.uniform(-0.02, 0.02), "La Serena (Gral)"

def clasificar_fuente_avanzada(link, nombre):
    link = link.lower()
    nombre = nombre.lower()
    
    # Detección de Redes Sociales
    social_kw = ['twitter', 'facebook', 'instagram', 'tiktok', 'reddit', 'x.com', 'youtube', 'linkedin']
    if any(x in link for x in social_kw) or any(x in nombre for x in social_kw):
        return "Red Social"
    
    # Detección de Prensa Local (Lista Blanca)
    local_kw = ['eldia', 'observatodo', 'miradio', 'laserenaonline', 'region', 'semanariotiempo', 'madero']
    if any(x in link for x in local_kw):
        return "Prensa Regional"
        
    return "Prensa Nacional/Web"

def generar_consultas_hydra(objetivo, extra):
    urls = []
    base_rss = "https://news.google.com/rss/search?q={}&hl=es-419&gl=CL&ceid=CL:es-419"
    
    # A. MEDIOS ESPECÍFICOS (Para garantizar Top Fuentes)
    medios = [
        "diarioeldia.cl", "semanariotiempo.cl", "diariolaregion.cl", 
        "elobservatodo.cl", "miradiols.cl", "biobiochile.cl", 
        "twitter.com", "facebook.com" # Intentar forzar redes
    ]
    for m in medios:
        urls.append(base_rss.format(quote(f'"{objetivo}" site:{m}')))
        
    # B. BÚSQUEDA GENERAL
    queries = [objetivo, f'{objetivo} La Serena', f'{objetivo} Coquimbo', f'{objetivo} denuncia', f'{objetivo} viral']
    if extra:
        for k in extra.split(","): queries.append(f'{objetivo} {k.strip()}')
        
    for q in queries: urls.append(base_rss.format(quote(q)))
    return list(set(urls))

def escanear_red(objetivo, inicio, fin, extra):
    analizador = cargar_cerebro()
    urls = generar_consultas_hydra(objetivo, extra)
    resultados = []
    vistos = set()
    
    progreso = st.progress(0)
    for i, url in enumerate(urls):
        try:
            feed = feedparser.parse(url)
            for item in feed.entries:
                try:
                    fecha = datetime.fromtimestamp(time.mktime(item.published_parsed)).date()
                except: fecha = datetime.now().date()
                
                if not (inicio <= fecha <= fin): continue
                if item.link in vistos: continue
                vistos.add(item.link)
                
                pred = analizador(item.title[:512])[0]
                score = int(pred['label'].split()[0])
                sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
                
                fuente_raw = item.source.title if 'source' in item else "Web"
                tipo = clasificar_fuente_avanzada(item.link, fuente_raw)
                lat, lon, lugar = detectar_lugar(item.title)
                
                resultados.append({
                    'Fecha': fecha, 'Fuente': fuente_raw, 'Titular': item.title,
                    'Sentimiento': sent, 'Link': item.link, 'Score': score,
                    'Tipo': tipo, 'Lat': lat, 'Lon': lon, 'Lugar': lugar, 'Manual': False
                })
        except: pass
        progreso.progress((i+1)/len(urls))
    progreso.empty()
    return pd.DataFrame(resultados)

# --- 6. SIDEBAR ---
with st.sidebar:
    st.title("⚓ EL FARO")
    st.caption("Intelligence Command Center")
    
    objetivo = st.text_input("Objetivo", "Daniela Norambuena")
    extra_kw = st.text_input("Contexto (Opcional)", "seguridad, festival")
    fechas = st.columns(2)
    ini = fechas[0].date_input("Inicio", datetime.now()-timedelta(days=30))
    fin = fechas[1].date_input("Fin", datetime.now())
    
    if st.button("📡 INICIAR ESCANEO"):
        with st.spinner("Triangulando señales..."):
            st.session_state.data_raw = escanear_red(objetivo, ini, fin, extra_kw)

    st.divider()
    with st.expander("➕ Ingreso Manual"):
        with st.form("man"):
            mt = st.text_input("Texto")
            ms = st.text_input("Fuente")
            msen = st.selectbox("Sentimiento", ["Positivo","Negativo","Neutro"])
            if st.form_submit_button("Guardar"):
                row = {'Fecha':datetime.now().date(), 'Fuente':ms, 'Titular':mt, 'Sentimiento':msen, 'Link':'#', 'Score':0, 'Tipo':'Manual', 'Lat':-29.90, 'Lon':-71.25, 'Lugar':'Manual', 'Manual':True}
                st.session_state.data_raw = pd.concat([st.session_state.data_raw, pd.DataFrame([row])], ignore_index=True)
                st.success("OK")

# --- 7. LOGICA DE DATOS (EDICIÓN VIVA) ---
# Aquí está la magia: Si hay datos, primero los mostramos para editar, LUEGO graficamos lo editado.
df_master = st.session_state.data_raw

if not df_master.empty:
    
    # --- ENCABEZADO ---
    c_logo, c_title = st.columns([1, 6])
    with c_title:
        st.title(f"Radar Activo: {objetivo}")
        st.caption(f"Última actualización: {datetime.now().strftime('%H:%M:%S')}")

    # --- PESTAÑAS ---
    tabs = st.tabs(["📝 GESTIÓN DE DATOS (Validar)", "📊 ESTRATEGIA 360", "🗺️ GEO-TACTICAL", "📱 FUENTES & MEDIOS", "📄 INFORME IA"])

    # === TAB 1: GESTIÓN DE DATOS (PRIMERO PARA PODER EDITAR) ===
    with tabs[0]:
        st.info("💡 INSTRUCCIONES: Edita esta tabla. Si cambias un sentimiento o borras una fila, los gráficos de las otras pestañas se actualizarán automáticamente.")
        
        # EDITOR DE DATOS CRUCIAL
        df_edited = st.data_editor(
            df_master,
            column_config={
                "Link": st.column_config.LinkColumn("Link"),
                "Sentimiento": st.column_config.SelectboxColumn("Sentimiento", options=["Positivo", "Negativo", "Neutro", "Irrelevante"]),
                "Tipo": st.column_config.SelectboxColumn("Tipo", options=["Prensa Regional", "Prensa Nacional/Web", "Red Social", "Manual"]),
                "Lat": None, "Lon": None, "Score": None, "Manual": None
            },
            num_rows="dynamic",
            use_container_width=True,
            key="data_editor_main"
        )
        
        # FILTRO DE BASURA (Lo que el usuario marcó como irrelevante o borró se va)
        df_clean = df_edited[df_edited.Sentimiento != "Irrelevante"]

    # === TAB 2: ESTRATEGIA 360 ===
    with tabs[1]:
        # KPIs
        vol = len(df_clean)
        pos = len(df_clean[df_clean.Sentimiento=='Positivo'])
        neg = len(df_clean[df_clean.Sentimiento=='Negativo'])
        
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Volumen Validado", vol)
        k2.metric("Positivos", pos, delta="🟢")
        k3.metric("Negativos", neg, delta="-🔴", delta_color="inverse")
        k4.metric("Ratio de Crisis", f"{int(neg/vol*100) if vol>0 else 0}%")

        st.divider()

        # FILA 1: MAPA CONCEPTUAL + TERMÓMETRO
        c_tree, c_gauge = st.columns([2, 1])
        
        with c_tree:
            st.subheader("🌳 Mapa Semántico (Treemap)")
            st.caption("Jerarquía: Lugar -> Medio -> Noticia. Haz clic para profundizar.")
            fig_tree = px.treemap(
                df_clean, path=[px.Constant("Ecosistema"), 'Lugar', 'Fuente', 'Titular'], 
                color='Sentimiento',
                color_discrete_map={'Positivo':'#00E676', 'Negativo':'#FF1744', 'Neutro':'#FFEA00'},
                hover_data=['Titular']
            )
            fig_tree.update_layout(margin=dict(t=0, l=0, r=0, b=0), height=450, paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_tree, use_container_width=True)
            
            # TABLA DE DETALLE (Para leer lo del Treemap)
            with st.expander("🔍 Ver Detalle de Noticias del Mapa"):
                st.dataframe(df_clean[['Fuente', 'Titular', 'Sentimiento', 'Link']], use_container_width=True, hide_index=True)

        with c_gauge:
            st.subheader("🌡️ Termómetro")
            score = ((pos * 100) + (vol - neg - pos) * 50) / vol if vol > 0 else 0
            fig_g = go.Figure(go.Indicator(
                mode = "gauge+number+delta", value = score,
                delta = {'reference': 50},
                title = {'text': "Reputación"},
                gauge = {
                    'axis': {'range': [None, 100]}, 'bar': {'color': "rgba(0,0,0,0)"},
                    'steps': [{'range': [0, 40], 'color': "#FF1744"}, {'range': [40, 60], 'color': "#FFEA00"}, {'range': [60, 100], 'color': "#00E676"}],
                    'threshold': {'line': {'color': "white", 'width': 4}, 'thickness': 0.75, 'value': score}
                }
            ))
            fig_g.update_layout(height=300, margin=dict(t=0,b=0,l=20,r=20), paper_bgcolor="rgba(0,0,0,0)", font={'color':'white'})
            st.plotly_chart(fig_g, use_container_width=True)
            
            # Gráfico Extra: Sentimiento General
            fig_pie = px.donut(df_clean, names='Sentimiento', color='Sentimiento', 
                               color_discrete_map={'Positivo':'#00E676', 'Negativo':'#FF1744', 'Neutro':'#FFEA00'}, hole=0.6)
            fig_pie.update_layout(height=200, margin=dict(t=0,b=0,l=0,r=0), paper_bgcolor="rgba(0,0,0,0)", showlegend=False)
            st.plotly_chart(fig_pie, use_container_width=True)

        # FILA 2: EVOLUCIÓN
        st.subheader("📈 Línea de Tiempo de Impacto")
        df_time = df_clean.groupby(['Fecha', 'Sentimiento']).size().reset_index(name='Menciones')
        fig_line = px.area(df_time, x='Fecha', y='Menciones', color='Sentimiento', 
                           color_discrete_map={'Positivo':'#00E676', 'Negativo':'#FF1744', 'Neutro':'#FFEA00'})
        st.plotly_chart(fig_line, use_container_width=True)

    # === TAB 3: GEO-TACTICAL ===
    with tabs[2]:
        st.subheader("📍 Mapa de Calor Territorial")
        c_map, c_stats = st.columns([3, 1])
        
        with c_map:
            # MAPA ARREGLADO: Lat/Lon limpios
            map_data = df_clean[(df_clean.Lat != 0) & (df_clean.Lat.notna())]
            if not map_data.empty:
                m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
                HeatMap([[r.Lat, r.Lon] for i, r in map_data.iterrows()], radius=15, blur=10).add_to(m)
                mc = MarkerCluster().add_to(m)
                for i, r in map_data.iterrows():
                    color = "green" if r.Sentimiento=='Positivo' else "red" if r.Sentimiento=='Negativo' else "orange"
                    folium.Marker([r.Lat, r.Lon], popup=f"{r.Fuente}: {r.Titular}", icon=folium.Icon(color=color)).add_to(mc)
                st_folium(m, width="100%", height=600)
            else:
                st.warning("No hay datos geográficos suficientes.")
        
        with c_stats:
            st.markdown("#### Top Lugares")
            top_places = df_clean['Lugar'].value_counts().head(10)
            st.bar_chart(top_places)

    # === TAB 4: FUENTES & MEDIOS ===
    with tabs[3]:
        # Separación Clara
        prensa = df_clean[df_clean['Tipo'].str.contains('Prensa')]
        social = df_clean[df_clean['Tipo'] == 'Red Social']
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("### 📰 Top 10 Prensa")
            if not prensa.empty:
                # Gráfico Barras Horizontal
                fig_p = px.bar(prensa['Fuente'].value_counts().head(10), orientation='h', color_discrete_sequence=['#0ea5e9'])
                st.plotly_chart(fig_p, use_container_width=True)
                
                # Gráfico Sentimiento por Medio (Quién pega más fuerte)
                st.markdown("#### Quién habla bien/mal")
                fig_stack = px.histogram(prensa, y="Fuente", color="Sentimiento", barmode="stack", 
                                         color_discrete_map={'Positivo':'#00E676', 'Negativo':'#FF1744', 'Neutro':'#FFEA00'})
                st.plotly_chart(fig_stack, use_container_width=True)
            else: st.info("Sin datos de prensa.")
            
        with c2:
            st.markdown("### 📱 Top 10 Redes Sociales")
            if not social.empty:
                fig_s = px.bar(social['Fuente'].value_counts().head(10), orientation='h', color_discrete_sequence=['#d946ef'])
                st.plotly_chart(fig_s, use_container_width=True)
            else: 
                st.warning("Poca data social directa. Google limita tweets individuales.")
                st.info("Tip: Usa 'Ingreso Manual' para agregar reportes de redes específicos.")

    # === TAB 5: INFORME IA ===
    with tabs[4]:
        st.header("🤖 Generador de Informes")
        
        col_gen, col_prev = st.columns([1, 2])
        with col_gen:
            st.markdown("Genera un análisis narrativo basado en los datos validados.")
            if st.button("✍️ REDACTAR INFORME"):
                # Lógica Narrativa Simple
                top_f = df_clean['Fuente'].mode()[0] if not df_clean.empty else "N/A"
                concl = "CRÍTICO" if neg > pos else "POSITIVO"
                
                informe_txt = f"""
                INFORME DE INTELIGENCIA - EL FARO
                =================================
                OBJETIVO: {objetivo}
                FECHA: {datetime.now().strftime('%d/%m/%Y')}
                
                1. RESUMEN DE SITUACIÓN
                El sistema ha detectado {vol} señales relevantes. El sentimiento predominante es {('Positivo' if pos>neg else 'Negativo')}, 
                con un índice de riesgo del {int(neg/vol*100) if vol>0 else 0}%.
                
                2. ANÁLISIS DE MEDIOS
                La fuente más activa ha sido '{top_f}'. Se observa una fuerte polarización en prensa regional.
                
                3. CONCLUSIÓN TÉCNICA
                El escenario actual se califica como {concl}. Se recomienda monitorear los focos en {', '.join(df_clean['Lugar'].unique()[:3])}.
                """
                st.session_state['informe_cache'] = informe_txt
                
        with col_prev:
            if 'informe_cache' in st.session_state:
                st.text_area("Borrador:", st.session_state['informe_cache'], height=300)
                
                # PDF Export
                pdf = FPDF()
                pdf.add_page()
                pdf.set_font("Arial", size=12)
                pdf.multi_cell(0, 6, st.session_state['informe_cache'].encode('latin-1','replace').decode('latin-1'))
                
                tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
                pdf.output(tmp.name)
                with open(tmp.name, "rb") as f:
                    st.download_button("📥 DESCARGAR PDF", f, "Informe_ElFaro.pdf")

else:
    st.info("👋 El Faro en espera. Configura el radar a la izquierda.")
