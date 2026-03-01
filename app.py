import streamlit as st
import feedparser
import pandas as pd
from transformers import pipeline
from datetime import datetime, timedelta
import time
import plotly.express as px
from urllib.parse import quote
from wordcloud import WordCloud
import matplotlib.pyplot as plt
import re

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Sentinel AI Pro", layout="wide", page_icon="📡")

# --- ESTILOS CSS PERSONALIZADOS ---
st.markdown("""
    <style>
    .big-font { font-size:20px !important; }
    .metric-card { background-color: #f0f2f6; padding: 15px; border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True)

st.title("📡 Sentinel AI: Monitor de Medios 360°")
st.markdown("Inteligencia de reputación, influencers y escucha social avanzada.")

# --- BARRA LATERAL ---
st.sidebar.header("🎛️ Centro de Comando")

tema_busqueda = st.sidebar.text_input("Tema a monitorear", "La Serena")
tipo_fuente = st.sidebar.radio("Fuentes", ("Todo Internet", "Solo Prensa", "Redes Sociales (Twitter/TikTok/IG)"))

st.sidebar.subheader("📅 Filtro Temporal")
col1, col2 = st.sidebar.columns(2)
fecha_inicio = col1.date_input("Inicio", datetime.now() - timedelta(days=30))
fecha_fin = col2.date_input("Fin", datetime.now())

btn_actualizar = st.sidebar.button("🚀 Ejecutar Análisis", type="primary")

# --- FUNCIONES ---
@st.cache_resource
def cargar_modelo():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def limpiar_texto(texto):
    # Limpieza básica para la nube de palabras
    texto = re.sub(r'http\S+', '', texto) # Quitar links
    texto = re.sub(r'[^\w\s]', '', texto) # Quitar signos raros
    return texto

def construir_url(tema, tipo):
    # LÓGICA CORREGIDA PARA EVITAR EL ERROR InvalidURL
    # Primero construimos la frase completa en texto plano
    if tipo == "Redes Sociales (Twitter/TikTok/IG)":
        query_raw = f"{tema} site:twitter.com OR site:facebook.com OR site:instagram.com OR site:tiktok.com OR site:reddit.com"
    elif tipo == "Solo Prensa":
        query_raw = f"{tema} when:14d"
    else:
        query_raw = tema
    
    # Luego codificamos TODO para que sea seguro para internet
    query_encoded = quote(query_raw)
    
    return f"https://news.google.com/rss/search?q={query_encoded}&hl=es-419&gl=CL&ceid=CL:es-419"

def analizar_datos(tema, tipo, f_inicio, f_fin):
    analizador = cargar_modelo()
    url = construir_url(tema, tipo)
    noticias = feedparser.parse(url)
    
    datos = []
    
    if not noticias.entries:
        return pd.DataFrame()

    progreso = st.progress(0)
    total = len(noticias.entries)
    
    for i, item in enumerate(noticias.entries):
        # Fecha
        try:
            fecha_obj = datetime.fromtimestamp(time.mktime(item.published_parsed)).date()
        except:
            fecha_obj = datetime.now().date()
            
        if not (f_inicio <= fecha_obj <= f_fin):
            continue
            
        # IA Sentimiento
        titulo = item.title
        try:
            pred = analizador(titulo[:512])[0]
            score = int(pred['label'].split()[0])
            
            if score <= 2: 
                sent, color = "Negativo", "🔴"
            elif score == 3: 
                sent, color = "Neutro", "🟡"
            else: 
                sent, color = "Positivo", "🟢"
                
            # Identificar Fuente (Limpiamos el nombre)
            fuente_raw = item.source.title if 'source' in item else "Web Desconocida"
            
            datos.append({
                "Fecha": fecha_obj,
                "Fuente": fuente_raw,
                "Titular": titulo,
                "Sentimiento": sent,
                "Color": color,
                "Link": item.link,
                "Score": score
            })
        except:
            pass
        
        progreso.progress((i + 1) / total)
        
    progreso.empty()
    return pd.DataFrame(datos)

# --- VISUALIZACIÓN ---
if btn_actualizar:
    with st.spinner(f"Escaneando ecosistema digital sobre '{tema_busqueda}'..."):
        df = analizar_datos(tema_busqueda, tipo_fuente, fecha_inicio, fecha_fin)
        
    if not df.empty:
        # 1. KPIs Principales
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Menciones Totales", len(df))
        kpi2.metric("Positivas", len(df[df.Sentimiento=='Positivo']), delta="🟢")
        kpi3.metric("Negativas", len(df[df.Sentimiento=='Negativo']), delta="-🔴", delta_color="inverse")
        
        # Fuente principal
        top_fuente = df['Fuente'].mode()[0] if not df.empty else "N/A"
        kpi4.metric("Fuente Top", top_fuente, "Más activa")
        
        st.divider()
        
        # 2. ANÁLISIS DE FUENTES Y SENTIMIENTO (FILA 1)
        c1, c2 = st.columns(2)
        
        with c1:
            st.subheader("📢 ¿Quién está hablando?")
            # Gráfico de torta de Fuentes
            fig_fuentes = px.pie(df, names='Fuente', title='Share of Voice (Participación por Medio)', hole=0.3)
            st.plotly_chart(fig_fuentes, use_container_width=True)
            
        with c2:
            st.subheader("❤️ Salud de Marca")
            fig_sent = px.bar(df, x='Sentimiento', color='Sentimiento', 
                              color_discrete_map={'Positivo':'#2ecc71', 'Negativo':'#e74c3c', 'Neutro':'#f1c40f'},
                              title="Volumen por Sentimiento")
            st.plotly_chart(fig_sent, use_container_width=True)

        # 3. NUBE DE PALABRAS Y RANKING (FILA 2)
        c3, c4 = st.columns([2, 1])
        
        with c3:
            st.subheader("☁️ Temas Candentes (WordCloud)")
            text_combined = " ".join(titulo for titulo in df.Titular)
            wordcloud = WordCloud(width=800, height=400, background_color='white', colormap='viridis').generate(text_combined)
            
            fig, ax = plt.subplots()
            ax.imshow(wordcloud, interpolation='bilinear')
            ax.axis("off")
            st.pyplot(fig)
            
        with c4:
            st.subheader("🏆 Top Influenciadores")
            # Tabla simple de quién publica más
            ranking = df['Fuente'].value_counts().reset_index()
            ranking.columns = ['Medio/Red', 'Menciones']
            st.dataframe(ranking, hide_index=True, use_container_width=True)

        # 4. TABLA DETALLADA
        st.subheader("🗞️ Monitor en Tiempo Real")
        for index, row in df.iterrows():
            with st.expander(f"{row['Color']} {row['Fuente']}: {row['Titular']}"):
                st.write(f"**Fecha:** {row['Fecha']}")
                st.write(f"**Análisis IA:** {row['Score']}/5")
                st.markdown(f"[Leer noticia original]({row['Link']})")

    else:
        st.warning("No encontramos resultados. Prueba ampliar las fechas.")
        
else:
    st.info("👈 Configura los parámetros y pulsa 'Ejecutar Análisis'")
