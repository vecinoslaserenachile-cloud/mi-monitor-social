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
import re

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sentinel AI: Master Dashboard", 
    layout="wide", 
    page_icon="📡",
    initial_sidebar_state="collapsed"
)

# --- ESTILOS CSS "PREMIUM DARK" ---
st.markdown("""
    <style>
    /* Fondo General */
    .main { background-color: #0e1117; }
    
    /* Tipografía */
    h1, h2, h3 { font-family: 'Roboto', sans-serif; color: #e0e0e0; font-weight: 300; }
    h1 { font-weight: 700; background: -webkit-linear-gradient(#00ffbf, #00b8ff); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
    
    /* Tarjetas Métricas (Glassmorphism) */
    div[data-testid="stMetric"] {
        background-color: rgba(38, 39, 48, 0.7);
        border: 1px solid #4e4e4e;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* Botones Neón */
    .stButton>button {
        background: linear-gradient(45deg, #ff4b4b, #ff0055);
        color: white;
        border-radius: 8px;
        border: none;
        padding: 12px 24px;
        font-weight: bold;
        letter-spacing: 1px;
        width: 100%;
        transition: all 0.3s ease;
    }
    .stButton>button:hover {
        box-shadow: 0 0 15px #ff4b4b;
        transform: scale(1.02);
    }
    
    /* Tablas */
    div[data-testid="stDataEditor"] {
        border: 1px solid #333;
        border-radius: 10px;
        overflow: hidden;
    }
    </style>
    """, unsafe_allow_html=True)

# --- MEMORIA DE SESIÓN ---
if 'df_noticias' not in st.session_state:
    st.session_state.df_noticias = pd.DataFrame(columns=['Fecha', 'Fuente', 'Titular', 'Sentimiento', 'Link', 'Score', 'Alcance', 'Manual'])

# --- FUNCIONES DE INTELIGENCIA ---
@st.cache_resource
def cargar_modelo():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def clasificar_alcance(fuente):
    # Base de conocimiento de medios (Personalizable)
    fuente = fuente.lower()
    regionales = ['el día', 'el observatodo', 'mi radio', 'laserenaonline', 'diario la región', 'norte visión', 'guayacán', 'serenaycoquimbo']
    nacionales = ['biobio', 'emol', 'la tercera', 'cooperativa', '24 horas', 'meganoticias', 'cnn chile', 'el mostrador', 'lun']
    
    if any(x in fuente for x in regionales): return "Regional"
    if any(x in fuente for x in nacionales): return "Nacional"
    return "Internacional/Web"

def construir_url(tema, tipo, sitios_extra):
    base_query = tema
    if tipo == "Redes Sociales":
        base_query += " site:twitter.com OR site:facebook.com OR site:instagram.com OR site:tiktok.com OR site:reddit.com"
    elif tipo == "Solo Prensa":
        base_query += " when:7d"
        
    if sitios_extra:
        for sitio in sitios_extra.split(","):
            if sitio.strip(): base_query += f" OR site:{sitio.strip()}"
            
    return f"https://news.google.com/rss/search?q={quote(base_query)}&hl=es-419&gl=CL&ceid=CL:es-419"

def escanear_web(tema, tipo, inicio, fin, sitios_extra):
    analizador = cargar_modelo()
    url = construir_url(tema, tipo, sitios_extra)
    feed = feedparser.parse(url)
    nuevas = []
    
    for item in feed.entries:
        try:
            fecha = datetime.fromtimestamp(time.mktime(item.published_parsed)).date()
        except: fecha = datetime.now().date()
            
        if not (inicio <= fecha <= fin): continue
        
        # Evitar duplicados
        if not st.session_state.df_noticias.empty:
            if item.link in st.session_state.df_noticias['Link'].values: continue

        try:
            # Análisis IA
            pred = analizador(item.title[:512])[0]
            score = int(pred['label'].split()[0])
            sent = "Negativo" if score <= 2 else "Neutro" if score == 3 else "Positivo"
            fuente_nombre = item.source.title if 'source' in item else "Web Desconocida"
            
            nuevas.append({
                'Fecha': fecha,
                'Fuente': fuente_nombre,
                'Titular': item.title,
                'Sentimiento': sent,
                'Link': item.link,
                'Score': score,
                'Alcance': clasificar_alcance(fuente_nombre), # Nueva clasificación
                'Manual': False
            })
        except: pass
        
    if nuevas:
        df_new = pd.DataFrame(nuevas)
        st.session_state.df_noticias = pd.concat([st.session_state.df_noticias, df_new], ignore_index=True)
        return len(df_new)
    return 0

# --- CLASE PDF ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.set_text_color(0, 50, 100)
        self.cell(0, 10, 'SENTINEL AI - INFORME ESTRATEGICO', 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Pagina {self.page_no()}', 0, 0, 'C')

def generar_pdf_pro(df, tema):
    pdf = PDF()
    pdf.add_page()
    
    # Resumen Ejecutivo
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"Objetivo: {tema} | Fecha: {datetime.now().date()}", 0, 1)
    
    pos = len(df[df.Sentimiento=='Positivo'])
    neg = len(df[df.Sentimiento=='Negativo'])
    total = len(df)
    
    pdf.set_font("Arial", size=10)
    pdf.multi_cell(0, 8, f"Se han analizado {total} menciones.\nIndice de Positividad: {int((pos/total)*100) if total else 0}%\nFuentes Activas: {df['Fuente'].nunique()}")
    pdf.ln(5)
    
    # Detalle por Alcance
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 10, "Desglose por Noticias:", 0, 1)
    pdf.set_font("Arial", size=9)
    
    for i, row in df.iterrows():
        try:
            tit = row['Titular'].encode('latin-1', 'replace').decode('latin-1')
            src = row['Fuente'].encode('latin-1', 'replace').decode('latin-1')
            pdf.multi_cell(0, 6, f"[{row['Alcance']}] {src}: {tit} ({row['Sentimiento']})")
            pdf.ln(1)
        except: pass
        
    t = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    pdf.output(t.name)
    return t.name

# --- INTERFAZ PRINCIPAL ---

# Header con Logo Texto
st.title("📡 SENTINEL AI: COMMAND CENTER")
st.caption("Sistema de Inteligencia, Reputación y Escucha Social 5.0")

# --- BARRA LATERAL (CONTROLES) ---
with st.sidebar:
    st.header("🎛️ Centro de Control")
    
    with st.expander("📝 INGRESO MANUAL (WhatsApp/Radio)"):
        with st.form("manual_entry"):
            m_tit = st.text_input("Mensaje/Titular")
            m_src = st.text_input("Fuente", "Radio/WhatsApp")
            m_alc = st.selectbox("Alcance", ["Regional", "Nacional", "Internacional"])
            m_sen = st.selectbox("Sentimiento", ["Positivo", "Negativo", "Neutro"])
            m_date = st.date_input("Fecha", datetime.now())
            if st.form_submit_button("💾 Guardar Dato"):
                new = {'Fecha':m_date, 'Fuente':m_src, 'Titular':m_tit, 'Sentimiento':m_sen, 
                       'Link':'#', 'Score':0, 'Alcance':m_alc, 'Manual':True}
                st.session_state.df_noticias = pd.concat([st.session_state.df_noticias, pd.DataFrame([new])], ignore_index=True)
                st.success("Dato guardado")

    st.markdown("---")
    tema = st.text_input("OBJETIVO A RASTREAR", "La Serena")
    tipo = st.selectbox("MODO DE ESCUCHA", ["Todo Internet", "Solo Prensa", "Redes Sociales"])
    sitios = st.text_area("SITIOS ESPECÍFICOS (Separa con comas)", placeholder="ej: elobservatodo.cl, miradiols.cl")
    
    col1, col2 = st.columns(2)
    f_ini = col1.date_input("Inicio", datetime.now()-timedelta(days=7))
    f_fin = col2.date_input("Fin", datetime.now())

# --- BOTÓN DE ACCIÓN PRINCIPAL ---
st.markdown("###")
if st.button(f"🔴 INICIAR ESCANEO DE LA RED PARA: {tema.upper()}"):
    with st.spinner("🛰️ Satélites alineados. Rastreando información..."):
        n = escanear_web(tema, tipo, f_ini, f_fin, sitios)
        if n > 0: st.success(f"¡Éxito! {n} nuevas señales detectadas.")
        else: st.warning("Sin señales nuevas. Intenta ampliar fechas.")

# --- VISUALIZACIÓN DE DATOS ---
if not st.session_state.df_noticias.empty:
    
    # 1. EDITOR DE DATOS (HUMAN IN THE LOOP)
    with st.expander("🛠️ TABLA DE DATOS (Corrige a la IA aquí)", expanded=True):
        df_edited = st.data_editor(
            st.session_state.df_noticias,
            column_config={
                "Sentimiento": st.column_config.SelectboxColumn("Sentimiento", options=["Positivo", "Negativo", "Neutro", "Irrelevante"], required=True),
                "Alcance": st.column_config.SelectboxColumn("Alcance", options=["Regional", "Nacional", "Internacional/Web"], required=True),
                "Link": st.column_config.LinkColumn("Link"),
                "Score": None, "Manual": None
            },
            use_container_width=True,
            num_rows="dynamic",
            key="main_editor"
        )

    # Filtrar irrelevantes
    df_final = df_edited[df_edited.Sentimiento != 'Irrelevante']
    
    if not df_final.empty:
        st.divider()
        
        # 2. TABLERO DE MANDO (HUD)
        pos = len(df_final[df_final.Sentimiento=='Positivo'])
        neg = len(df_final[df_final.Sentimiento=='Negativo'])
        tot = len(df_final)
        score = ((pos * 100) + (tot - neg - pos) * 50) / tot if tot > 0 else 0
        
        c1, c2 = st.columns([1, 2])
        
        with c1:
            # VELOCÍMETRO ESTILO "GAUGE"
            fig_g = go.Figure(go.Indicator(
                mode = "gauge+number", value = score,
                title = {'text': "SALUD DE MARCA"},
                gauge = {
                    'axis': {'range': [None, 100], 'tickcolor': "white"},
                    'bar': {'color': "rgba(0,0,0,0)"}, # Invisible
                    'bgcolor': "rgba(0,0,0,0)",
                    'borderwidth': 2,
                    'bordercolor': "#333",
                    'steps': [
                        {'range': [0, 40], 'color': '#ff4b4b'},
                        {'range': [40, 70], 'color': '#f1c40f'},
                        {'range': [70, 100], 'color': '#00ffbf'}],
                    'threshold': {'line': {'color': "white", 'width': 4}, 'thickness': 0.75, 'value': score}
                }
            ))
            fig_g.update_layout(height=300, margin=dict(t=50,b=20,l=30,r=30), paper_bgcolor="rgba(0,0,0,0)", font={'color':"white"})
            st.plotly_chart(fig_g, use_container_width=True)
            
        with c2:
            # KPIs NEÓN
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Menciones", tot)
            k2.metric("Positivas", pos, delta="🟢")
            k3.metric("Negativas", neg, delta="-🔴", delta_color="inverse")
            # Métrica de Regionalidad
            reg = len(df_final[df_final.Alcance=='Regional'])
            k4.metric("Alcance Local", f"{int((reg/tot)*100)}%", "Medios Regionales")
            
            # GRÁFICO DE BARRAS: ALCANCE
            st.markdown("#### 🌍 Distribución Geográfica")
            fig_bar = px.histogram(df_final, x="Alcance", color="Sentimiento", 
                                   color_discrete_map={'Positivo':'#00ffbf', 'Negativo':'#ff4b4b', 'Neutro':'#f1c40f'},
                                   barmode='group')
            fig_bar.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font={'color':'white'}, height=200)
            st.plotly_chart(fig_bar, use_container_width=True)

        st.divider()
        
        # 3. ANÁLISIS PROFUNDO (SUNBURST + INFLUENCERS)
        c3, c4 = st.columns([3, 2])
        
        with c3:
            st.markdown("### 🕸️ Mapa Conceptual Interactivo")
            st.caption("Haz clic en el centro para expandir | Anillos: Alcance -> Sentimiento -> Fuente -> Noticia")
            # Sunburst mejorado
            fig_sun = px.sunburst(
                df_final, 
                path=['Alcance', 'Sentimiento', 'Fuente', 'Titular'], 
                color='Sentimiento',
                color_discrete_map={'Positivo':'#00ffbf', 'Negativo':'#ff4b4b', 'Neutro':'#f1c40f'},
                maxdepth=3
            )
            fig_sun.update_layout(height=600, margin=dict(t=0, b=0, l=0, r=0), paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig_sun, use_container_width=True)
            
        with c4:
            st.markdown("### 🏆 Top Influenciadores")
            st.caption("Medios/Cuentas con más actividad")
            top_media = df_final['Fuente'].value_counts().head(10).reset_index()
            top_media.columns = ['Fuente', 'Menciones']
            
            fig_inf = px.bar(top_media, x='Menciones', y='Fuente', orientation='h', text='Menciones',
                             color='Menciones', color_continuous_scale='Bluyl')
            fig_inf.update_layout(yaxis={'categoryorder':'total ascending'}, paper_bgcolor="rgba(0,0,0,0)", 
                                  plot_bgcolor="rgba(0,0,0,0)", font={'color':'white'}, height=550)
            st.plotly_chart(fig_inf, use_container_width=True)

        # 4. NUBE DE PALABRAS Y PDF
        st.divider()
        c5, c6 = st.columns(2)
        
        with c5:
            st.markdown("### ☁️ Conceptos Clave")
            text = " ".join(titulo for titulo in df_final.Titular)
            wc = WordCloud(width=800, height=400, background_color='#0e1117', colormap='Wistia').generate(text)
            fig_wc, ax = plt.subplots()
            ax.imshow(wc, interpolation='bilinear')
            ax.axis("off")
            fig_wc.patch.set_facecolor('#0e1117')
            st.pyplot(fig_wc)
            
        with c6:
            st.markdown("### 📥 Reporte Oficial")
            st.info("Generar documento PDF profesional para distribución.")
            if st.button("Generar PDF Ejecutivo"):
                f_pdf = generar_pdf_pro(df_final, tema)
                with open(f_pdf, "rb") as f:
                    st.download_button("⬇️ Descargar Informe PDF", f, f"Sentinel_{datetime.now().date()}.pdf", use_container_width=True)

else:
    st.info("👋 Sistema en espera. Inicia un escaneo o carga datos manuales.")
