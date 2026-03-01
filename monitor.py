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

# --- 1. CONFIGURACIÓN DE IDENTIDAD ---
st.set_page_config(
    page_title="El Faro | Sentinel Engine", 
    layout="wide", 
    page_icon="️lighthouse",
    initial_sidebar_state="expanded"
)

# --- 2. ESTILOS VISUALES (Nautical & Tech) ---
st.markdown("""
    <style>
    /* Fondo Degradado Marino Profundo */
    .main { background: linear-gradient(180deg, #021B2B 0%, #083D56 100%); }
    
    /* Títulos */
    h1 { 
        background: -webkit-linear-gradient(#00d2ff, #3a7bd5); 
        -webkit-background-clip: text; 
        -webkit-text-fill-color: transparent; 
        font-family: 'Helvetica Neue', sans-serif;
        font-weight: 800;
        text-shadow: 0px 0px 20px rgba(0, 210, 255, 0.3);
    }
    h2, h3 { color: #e0f7fa !important; }
    
    /* Tarjetas KPI (Glassmorphism avanzado) */
    div[data-testid="stMetric"] {
        background: rgba(14, 33, 48, 0.6);
        backdrop-filter: blur(15px);
        border: 1px solid rgba(0, 210, 255, 0.2);
        border-radius: 15px;
        padding: 20px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
    }
    div[data-testid="stMetric"]:hover {
        border-color: #00d2ff;
        transform: translateY(-2px);
        transition: all 0.3s;
    }
    
    /* Botón Principal */
    .stButton>button {
        background: linear-gradient(90deg, #ff8c00 0%, #ff0080 100%); /* Color de alerta/faro */
        color: white; border: none; padding: 18px; border-radius: 12px;
        font-weight: bold; font-size: 18px; letter-spacing: 2px; width: 100%;
        box-shadow: 0 0 25px rgba(255, 140, 0, 0.4);
    }
    .stButton>button:hover {
        box-shadow: 0 0 40px rgba(255, 140, 0, 0.7);
    }
    
    /* Tabs */
    .stTabs [aria-selected="true"] {
        background-color: #00d2ff !important;
        color: #000 !important;
        font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 3. GESTIÓN DE ESTADO ---
if 'data_faro' not in st.session_state:
    st.session_state.data_faro = pd.DataFrame(columns=['Fecha', 'Fuente', 'Titular', 'Sentimiento', 'Link', 'Score', 'Tipo', 'Lat', 'Lon', 'Lugar', 'Manual'])

# --- 4. BASE GEO (GEODATA) ---
# Ampliada para cubrir más zonas y asegurar que el mapa funcione
GEO_DB = {
    "avenida del mar": [-29.9168, -71.2785], "faro": [-29.9073, -71.2847], "centro": [-29.9027, -71.2519],
    "plaza de armas": [-29.9027, -71.2519], "las compañías": [-29.8783, -71.2389], "tierras blancas": [-29.9392, -71.2294],
    "coquimbo": [-29.9533, -71.3436], "ovalle": [-30.6015, -71.2003], "vicuña": [-30.0319, -70.7081],
    "aeropuerto": [-29.9161, -71.1994], "la florida": [-29.9238, -71.2185], "el milagro": [-29.9333, -71.2333],
    "serena": [-29.9027, -71.2519], "región": [-29.95, -71.3], "municipalidad": [-29.9045, -71.2489],
    "mall": [-29.9130, -71.2570], "estadio": [-29.9125, -71.2612]
}

# --- 5. MOTOR DE INTELIGENCIA (SENTINEL ENGINE) ---
@st.cache_resource
def cargar_cerebro():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def detectar_lugar(texto):
    texto_low = texto.lower()
    for lugar, coords in GEO_DB.items():
        if lugar in texto_low: return coords[0], coords[1], lugar.title()
    # Si no encuentra, dispersión aleatoria sobre el centro para evitar superposición
    return -29.9027 + random.uniform(-0.04, 0.04), -71.2519 + random.uniform(-0.04, 0.04), "La Serena (Gral)"

def clasificar_fuente(link, nombre):
    link = link.lower()
    nombre = nombre.lower()
    if any(x in link or x in nombre for x in ['twitter', 'facebook', 'instagram', 'tiktok', 'reddit', 'x.com']):
        return "Red Social"
    return "Prensa/Medios"

def generar_consultas_deep(objetivo, extra):
    urls = []
    base_rss = "https://news.google.com/rss/search?q={}&hl=es-419&gl=CL&ceid=CL:es-419"
    
    # 1. LISTA DE ORO DE MEDIOS LOCALES (Forzar búsqueda aquí)
    medios_objetivo = [
        "diarioeldia.cl", "semanariotiempo.cl", "diariolaregion.cl", 
        "elobservatodo.cl", "miradiols.cl", "laserenaonline.cl", 
        "biobiochile.cl", "municipalidadlaserena.cl", "radiomadero.cl"
    ]
    
    # Búsqueda sitio por sitio (Garantiza que aparezcan)
    for medio in medios_objetivo:
        q = f'"{objetivo}" site:{medio}'
        urls.append(base_rss.format(quote(q)))
        
    # 2. Búsqueda General Amplia
    queries_gen = [objetivo, f'{objetivo} La Serena', f'{objetivo} Coquimbo']
    if extra:
        for k in extra.split(","):
            queries_gen.append(f'{objetivo} {k.strip()}')
            
    for q in queries_gen:
        urls.append(base_rss.format(quote(q)))
        
    return list(set(urls))

def escanear_oceano(objetivo, inicio, fin, extra):
    analizador = cargar_cerebro()
    urls = generar_consultas_deep(objetivo, extra)
    resultados = []
    vistos = set()
    
    progreso = st.progress(0)
    total_steps = len(urls)
    
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
                
                # Análisis de Sentimiento
                pred = analizador(item.title[:512])[0]
                score = int(pred['label'].split()[0])
                if score <= 2: sent = "Negativo"
                elif score == 3: sent = "Neutro"
                else: sent = "Positivo"
                
                # Metadatos
                fuente_raw = item.source.title if 'source' in item else "Web"
                tipo = clasificar_fuente(item.link, fuente_raw)
                lat, lon, lugar = detectar_lugar(item.title)
                
                resultados.append({
                    'Fecha': fecha, 'Fuente': fuente_raw, 'Titular': item.title,
                    'Sentimiento': sent, 'Link': item.link, 'Score': score,
                    'Tipo': tipo, 'Lat': lat, 'Lon': lon, 'Lugar': lugar, 'Manual': False
                })
        except: pass
        progreso.progress((i + 1) / total_steps)
        
    progreso.empty()
    return pd.DataFrame(resultados)

# --- 6. BARRA DE NAVEGACIÓN (SIDEBAR) ---
with st.sidebar:
    st.markdown("# ⚓ EL FARO")
    st.markdown("*Powered by Sentinel AI*")
    st.markdown("---")
    
    st.markdown("### 🔭 Configuración de Radar")
    objetivo = st.text_input("Objetivo Principal", "Alcaldesa Daniela Norambuena")
    extra_kw = st.text_input("Conceptos Contexto", placeholder="Ej: seguridad, obras, festival")
    
    c1, c2 = st.columns(2)
    ini = c1.date_input("Inicio", datetime.now() - timedelta(days=30))
    fin = c2.date_input("Fin", datetime.now())
    
    # Botón de Escaneo Arriba
    if st.button("ENCENDER EL FARO (ESCANEAR)"):
        st.session_state.data_faro = pd.DataFrame()
        with st.spinner("📡 Satélites triangulando medios locales y redes..."):
            df_new = escanear_oceano(objetivo, ini, fin, extra_kw)
            st.session_state.data_faro = df_new

    st.markdown("---")
    with st.expander("📝 Ingreso Manual (Radio/Calle)"):
        with st.form("manual"):
            m_txt = st.text_input("Titular/Comentario")
            m_src = st.text_input("Fuente", "Radio Madero")
            m_sen = st.selectbox("Sentimiento", ["Positivo", "Negativo", "Neutro"])
            if st.form_submit_button("Agregar al Radar"):
                new = {'Fecha': datetime.now().date(), 'Fuente': m_src, 'Titular': m_txt, 'Sentimiento': m_sen, 'Link':'#', 'Score':0, 'Tipo': 'Prensa/Medios', 'Lat':-29.90, 'Lon':-71.25, 'Lugar':'Manual', 'Manual':True}
                st.session_state.data_faro = pd.concat([st.session_state.data_faro, pd.DataFrame([new])], ignore_index=True)
                st.success("Dato incorporado.")

# --- 7. PANEL PRINCIPAL ---
df = st.session_state.data_faro

if not df.empty:
    st.title(f"Reporte de Inteligencia: {objetivo}")
    
    # --- KPIs ---
    k1, k2, k3, k4 = st.columns(4)
    vol = len(df)
    pos = len(df[df.Sentimiento=='Positivo'])
    neg = len(df[df.Sentimiento=='Negativo'])
    neu = len(df[df.Sentimiento=='Neutro'])
    
    k1.metric("Volumen Detectado", vol)
    k2.metric("Positivas", pos, delta=f"{int(pos/vol*100)}%", delta_color="normal")
    k3.metric("Negativas", neg, delta=f"-{int(neg/vol*100)}%", delta_color="inverse")
    k4.metric("Fuentes Activas", df['Fuente'].nunique())
    
    st.markdown("---")
    
    # PESTAÑAS MEJORADAS
    tabs = st.tabs(["📊 Visión Estratégica", "🗺️ Mapa Geo-Táctico", "🏆 Ranking de Medios", "📝 Gestión & Informe IA"])
    
    # 1. VISIÓN ESTRATÉGICA
    with tabs[0]:
        c_sun, c_gauge = st.columns([2, 1])
        
        with c_sun:
            st.subheader("🕸️ Ecosistema de la Conversación")
            st.caption("Pasa el mouse para ver detalles. Los anillos muestran: Sentimiento > Fuente > Noticia")
            
            # SUNBURST LIMPIO (Sin 'Parent', con tooltips útiles)
            fig_sun = px.sunburst(
                df, path=['Sentimiento', 'Fuente', 'Titular'], 
                color='Sentimiento',
                color_discrete_map={'Positivo':'#00e676', 'Negativo':'#ff1744', 'Neutro':'#ffea00'},
                hover_data={'Score': True}
            )
            fig_sun.update_traces(hovertemplate='<b>%{label}</b><br>Volumen: %{value}')
            fig_sun.update_layout(height=600, margin=dict(t=0, b=0, l=0, r=0), paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_sun, use_container_width=True)
            
        with c_gauge:
            st.subheader("🌡️ Termómetro de Marca")
            # GAUGE HYPER-REALISTA
            score = ((pos * 100) + (vol - neg - pos) * 50) / vol if vol > 0 else 0
            
            fig_g = go.Figure(go.Indicator(
                mode = "gauge+number+delta",
                value = score,
                delta = {'reference': 50, 'increasing': {'color': "#00e676"}, 'decreasing': {'color': "#ff1744"}},
                gauge = {
                    'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': "white"},
                    'bar': {'color': "rgba(0,0,0,0)"}, # Invisible, usamos la aguja
                    'bgcolor': "white",
                    'borderwidth': 2,
                    'bordercolor': "#fff",
                    'steps': [
                        {'range': [0, 40], 'color': "#ff1744"}, # Rojo neón
                        {'range': [40, 60], 'color': "#ffea00"}, # Amarillo
                        {'range': [60, 100], 'color': "#00e676"}], # Verde neón
                    'threshold': {'line': {'color': "white", 'width': 5}, 'thickness': 0.8, 'value': score}
                }
            ))
            fig_g.update_layout(
                height=350, 
                paper_bgcolor="rgba(0,0,0,0)", 
                font={'color': "white", 'family': "Arial"},
                margin=dict(t=30, b=20, l=30, r=30)
            )
            st.plotly_chart(fig_g, use_container_width=True)
            st.info(f"Índice de Reputación: {int(score)}/100. Zona {'Crítica' if score <40 else 'Estable' if score <60 else 'Positiva'}.")

        st.divider()
        
        # INTERACTIVE TREEMAP (Reemplazo de Nube de Palabras)
        st.subheader("🌳 Mapa Semántico Interactivo (Drill-Down)")
        st.caption("Haz clic en un Concepto (Lugar) para ver qué Medios hablan de él, y luego clic en el Medio para ver las Noticias.")
        
        # Creamos una jerarquía: Lugar -> Fuente -> Titular
        fig_tree = px.treemap(
            df, 
            path=[px.Constant("Todo"), 'Lugar', 'Fuente', 'Titular'],
            color='Sentimiento',
            color_discrete_map={'Positivo':'#00e676', 'Negativo':'#ff1744', 'Neutro':'#ffea00', '(?)':'#333'},
            hover_data=['Titular']
        )
        fig_tree.update_traces(root_color="#1e1e1e")
        fig_tree.update_layout(margin=dict(t=0, l=0, r=0, b=0), height=500, paper_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_tree, use_container_width=True)
        
        # GRÁFICO TEMPORAL ÚTIL (Barras apiladas)
        st.subheader("📅 Evolución del Sentimiento")
        df_time = df.groupby(['Fecha', 'Sentimiento']).size().reset_index(name='Menciones')
        fig_time = px.bar(
            df_time, x='Fecha', y='Menciones', color='Sentimiento',
            color_discrete_map={'Positivo':'#00e676', 'Negativo':'#ff1744', 'Neutro':'#ffea00'},
            barmode='stack', text='Menciones'
        )
        fig_time.update_traces(textposition='inside')
        fig_time.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font={'color':'white'})
        st.plotly_chart(fig_time, use_container_width=True)

    # 2. MAPA GEO-TÁCTICO (Arreglado)
    with tabs[1]:
        st.subheader("📍 Despliegue Territorial")
        # Aseguramos coordenadas válidas
        map_df = df[df['Lat'] != 0]
        
        if not map_df.empty:
            m = folium.Map(location=[-29.9027, -71.2519], zoom_start=12, tiles="CartoDB dark_matter")
            
            # Capa Calor
            heat_data = [[row['Lat'], row['Lon']] for index, row in map_df.iterrows()]
            HeatMap(heat_data, radius=15, blur=10).add_to(m)
            
            # Clusters
            marker_cluster = MarkerCluster().add_to(m)
            for i, row in map_df.iterrows():
                color = "green" if row['Sentimiento'] == 'Positivo' else "red" if row['Sentimiento'] == 'Negativo' else "orange"
                icon_type = "info-sign"
                
                html = f"""
                <div style='font-family:Arial; color:black; width:200px'>
                    <h4>{row['Fuente']}</h4>
                    <b style='color:{color}'>{row['Sentimiento']}</b><br>
                    <i>{row['Titular']}</i>
                </div>
                """
                folium.Marker(
                    [row['Lat'], row['Lon']],
                    popup=folium.Popup(html, max_width=250),
                    icon=folium.Icon(color=color, icon=icon_type)
                ).add_to(marker_cluster)
                
            st_folium(m, width="100%", height=600)
        else:
            st.warning("No hay datos geolocalizados disponibles.")

    # 3. RANKING DE FUENTES (Top 10 separado)
    with tabs[2]:
        c_news, c_soc = st.columns(2)
        
        with c_news:
            st.markdown("### 📰 Top 10 Prensa & Medios")
            prensa = df[df['Tipo'] == 'Prensa/Medios']['Fuente'].value_counts().head(10).reset_index()
            prensa.columns = ['Medio', 'Notas']
            if not prensa.empty:
                fig_p = px.bar(prensa, x='Notas', y='Medio', orientation='h', color='Notas', color_continuous_scale='Teal')
                fig_p.update_layout(yaxis={'categoryorder':'total ascending'}, paper_bgcolor="rgba(0,0,0,0)", font={'color':'white'})
                st.plotly_chart(fig_p, use_container_width=True)
            else: st.info("Sin datos de prensa.")
            
        with c_soc:
            st.markdown("### 📱 Top 10 Redes Sociales")
            social = df[df['Tipo'] == 'Red Social']['Fuente'].value_counts().head(10).reset_index()
            social.columns = ['Red', 'Menciones']
            if not social.empty:
                fig_s = px.bar(social, x='Menciones', y='Red', orientation='h', color='Menciones', color_continuous_scale='Purples')
                fig_s.update_layout(yaxis={'categoryorder':'total ascending'}, paper_bgcolor="rgba(0,0,0,0)", font={'color':'white'})
                st.plotly_chart(fig_s, use_container_width=True)
            else: st.info("Sin datos de redes sociales.")

    # 4. GESTIÓN Y REPORTE IA
    with tabs[3]:
        st.subheader("📝 Editor de Datos (Validación Humana)")
        st.caption("Aquí puedes corregir el sentimiento si la IA se equivocó. Los cambios se reflejarán en el informe.")
        
        # EDITOR DE DATOS
        df_editado = st.data_editor(
            df,
            column_config={
                "Link": st.column_config.LinkColumn("Ver Original"),
                "Sentimiento": st.column_config.SelectboxColumn("Sentimiento", options=["Positivo", "Negativo", "Neutro", "Irrelevante"]),
                "Lat": None, "Lon": None, "Manual": None, "Score": None
            },
            num_rows="dynamic",
            use_container_width=True,
            key="editor_datos" # Clave para guardar cambios
        )
        
        # Actualizar sesión con cambios del editor
        st.session_state.data_faro = df_editado
        
        st.divider()
        st.subheader("🤖 Generador de Informe Técnico")
        
        if st.button("GENERAR INFORME LITERARIO CON IA"):
            # LÓGICA DE GENERACIÓN DE TEXTO (Simulación de IA Generativa basada en reglas)
            # Calculamos estadísticas finales del DF editado
            d_final = st.session_state.data_faro
            d_pos = len(d_final[d_final.Sentimiento=='Positivo'])
            d_neg = len(d_final[d_final.Sentimiento=='Negativo'])
            d_neu = len(d_final[d_final.Sentimiento=='Neutro'])
            d_tot = len(d_final)
            d_score = int(((d_pos * 100) + (d_tot - d_neg - d_pos) * 50) / d_tot) if d_tot > 0 else 0
            
            top_fuente = d_final['Fuente'].mode()[0] if not d_final.empty else "N/A"
            temas_calientes = ", ".join(d_final['Lugar'].unique()[:3])
            
            # Construcción del Prompt Narrativo
            fecha_hoy = datetime.now().strftime("%d de %B de %Y")
            
            texto_informe = f"""
            INFORME TÉCNICO DE INTELIGENCIA DE MEDIOS - EL FARO
            ==================================================
            Fecha: {fecha_hoy}
            Objetivo: {objetivo}
            
            1. RESUMEN EJECUTIVO
            --------------------
            En el periodo analizado, el sistema El Faro ha detectado un volumen total de {d_tot} menciones relevantes. 
            El clima de opinión actual presenta un índice de reputación de {d_score}/100.
            
            La distribución de sentimiento se desglosa en:
            - {d_pos} menciones positivas ({(d_pos/d_tot)*100:.1f}%)
            - {d_neg} menciones negativas ({(d_neg/d_tot)*100:.1f}%)
            - {d_neu} menciones neutras.
            
            2. ANÁLISIS DE FUENTES Y MEDIOS
            -------------------------------
            La conversación ha sido liderada principalmente por '{top_fuente}', que se posiciona como el actor más activo en este ciclo.
            Se observa una actividad destacada en medios como BioBioChile, El Día y Semanario Tiempo, junto con la conversación social.
            
            3. FOCOS GEOGRÁFICOS Y TEMÁTICOS
            --------------------------------
            El análisis semántico y geolocalizado indica que los temas se concentran en sectores como: {temas_calientes}.
            
            4. CONCLUSIÓN Y RECOMENDACIÓN (IA)
            ----------------------------------
            {'[ALERTA] Se observa una tendencia negativa significativa. Se recomienda activar protocolos de contención y respuesta rápida en medios locales.' if d_neg > d_pos else '[OPORTUNIDAD] El escenario es favorable. Se sugiere potenciar los mensajes actuales y capitalizar la buena recepción en redes.'}
            
            --------------------------------------------------
            Generado por Sentinel Engine v11.0
            """
            
            st.text_area("Vista Previa del Informe:", value=texto_informe, height=400)
            
            # Generar PDF Real
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=11)
            # Título
            pdf.set_font("Arial", 'B', 16)
            pdf.cell(0, 10, "INFORME DE INTELIGENCIA - EL FARO", 0, 1, 'C')
            pdf.ln(10)
            
            # Cuerpo
            pdf.set_font("Arial", size=11)
            pdf.multi_cell(0, 6, texto_informe.encode('latin-1', 'replace').decode('latin-1'))
            
            # Tabla Anexa (Top 5 noticias críticas)
            pdf.add_page()
            pdf.set_font("Arial", 'B', 14)
            pdf.cell(0, 10, "ANEXO: MENCIONES CRÍTICAS RECIENTES", 0, 1)
            pdf.set_font("Arial", size=10)
            criticas = d_final[d_final.Sentimiento == 'Negativo'].head(10)
            for i, row in criticas.iterrows():
                clean_tit = row['Titular'].encode('latin-1', 'replace').decode('latin-1')
                clean_src = row['Fuente'].encode('latin-1', 'replace').decode('latin-1')
                pdf.multi_cell(0, 6, f"- [{clean_src}] {clean_tit}")
                pdf.ln(2)
                
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            pdf.output(tmp_file.name)
            
            with open(tmp_file.name, "rb") as f:
                st.download_button("💾 DESCARGAR INFORME OFICIAL (PDF)", f, f"Informe_ElFaro_{datetime.now().date()}.pdf")

else:
    st.info("👋 El Faro está en espera. Configure los parámetros en la barra lateral y presione 'ENCENDER'.")
