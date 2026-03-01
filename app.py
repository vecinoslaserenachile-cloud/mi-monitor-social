import streamlit as st
import feedparser
import pandas as pd
from transformers import pipeline
from datetime import datetime, timedelta
import time
import plotly.express as px
from urllib.parse import quote

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Sentinel AI Pro", layout="wide", page_icon="📡")

st.title("📡 Sentinel AI: Monitor de Medios Pro")
st.markdown("Monitor de reputación, análisis de sentimiento y escucha social.")

# --- BARRA LATERAL (CONTROLES) ---
st.sidebar.header("🎛️ Panel de Control")

# 1. INPUT DE TEMA
tema_busqueda = st.sidebar.text_input("Tema o Persona a monitorear", "La Serena")

# 2. SELECTOR DE FUENTES
tipo_fuente = st.sidebar.radio(
    "¿Dónde buscar?",
    ("Todo Internet", "Solo Prensa/Noticias", "Redes Sociales (TikTok/IG/X)")
)

# 3. FILTRO DE FECHAS
st.sidebar.subheader("📅 Rango de Fechas")
col_fecha1, col_fecha2 = st.sidebar.columns(2)
fecha_inicio = col_fecha1.date_input("Desde", datetime.now() - timedelta(days=7))
fecha_fin = col_fecha2.date_input("Hasta", datetime.now())

btn_actualizar = st.sidebar.button("🔄 Ejecutar Análisis", type="primary")

# --- FUNCIONES ---
@st.cache_resource
def cargar_modelo():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def construir_url_rss(tema, tipo):
    tema_seguro = quote(tema)
    
    # Truco Legal: Usamos "Google Dorks" (site:...) para buscar dentro de las redes
    if tipo == "Redes Sociales (TikTok/IG/X)":
        # AQUI AGREGAMOS TIKTOK
        query = f"{tema_seguro} site:twitter.com OR site:x.com OR site:facebook.com OR site:instagram.com OR site:tiktok.com OR site:reddit.com"
    elif tipo == "Solo Prensa/Noticias":
        query = f"{tema_seguro} when:7d" # Prioriza noticias recientes
    else:
        query = tema_seguro

    return f"https://news.google.com/rss/search?q={query}&hl=es-419&gl=CL&ceid=CL:es-419"

def convertir_fecha(struct_time):
    # Convierte la fecha rara del RSS a una fecha normal
    if struct_time:
        return datetime.fromtimestamp(time.mktime(struct_time)).date()
    return datetime.now().date()

def analizar_noticias(tema, tipo, f_inicio, f_fin):
    analizador = cargar_modelo()
    url = construir_url_rss(tema, tipo)
    
    noticias = feedparser.parse(url)
    resultados = []
    
    if not noticias.entries:
        return pd.DataFrame()

    barra = st.progress(0)
    total_items = len(noticias.entries)
    
    for i, noticia in enumerate(noticias.entries):
        # CORRECCIÓN AQUÍ: Usamos el nombre correcto de la función
        fecha_noticia = convertir_fecha(noticia.published_parsed)
        
        # Filtro de fecha
        if not (f_inicio <= fecha_noticia <= f_fin):
            continue

        titulo = noticia.title
        link = noticia.link
        
        try:
            # Análisis IA (cortamos texto largo para no saturar)
            pred = analizador(titulo[:512])[0]
            score = int(pred['label'].split()[0])
            
            if score <= 2:
                sent = "Negativo"
                color = "🔴"
            elif score == 3:
                sent = "Neutro"
                color = "🟡"
            else:
                sent = "Positivo"
                color = "🟢"
                
            resultados.append({
                "Fecha": fecha_noticia,
                "Fuente": noticia.source.title if 'source' in noticia else "Web",
                "Titular": titulo,
                "Sentimiento": sent,
                "Icono": color,
                "Score": score,
                "Link": link
            })
        except Exception as e:
            pass
        
        if total_items > 0:
            barra.progress((i + 1) / total_items)
            
    barra.empty()
    return pd.DataFrame(resultados)

# --- INTERFAZ PRINCIPAL ---

if btn_actualizar:
    st.markdown(f"### 🔎 Analizando: *{tema_busqueda}*")
    st.caption(f"Buscando en: {tipo_fuente} | Desde: {fecha_inicio} Hasta: {fecha_fin}")
    
    with st.spinner('Escaneando TikTok, Instagram, X y Prensa...'):
        df = analizar_noticias(tema_busqueda, tipo_fuente, fecha_inicio, fecha_fin)
        
    if not df.empty:
        # MÉTRICAS
        col1, col2, col3, col4 = st.columns(4)
        positivos = len(df[df['Sentimiento'] == 'Positivo'])
        negativos = len(df[df['Sentimiento'] == 'Negativo'])
        neutros = len(df[df['Sentimiento'] == 'Neutro'])
        
        col1.metric("Total Hallazgos", len(df))
        col2.metric("Positivos", positivos, delta="🟢")
        col3.metric("Negativos", negativos, delta="🔴", delta_color="inverse")
        col4.metric("Neutros", neutros, delta="🟡", delta_color="off")
        
        st.divider()

        # GRÁFICOS
        c1, c2 = st.columns([1, 1])
        
        with c1:
            st.subheader("📊 Sentimiento General")
            fig_torta = px.pie(df, names='Sentimiento', 
                               color='Sentimiento',
                               color_discrete_map={'Positivo':'#2ECC71', 'Negativo':'#E74C3C', 'Neutro':'#F1C40F'},
                               hole=0.4)
            st.plotly_chart(fig_torta, use_container_width=True)
            
        with c2:
            st.subheader("📈 Evolución Temporal")
            df_trend = df.groupby(['Fecha', 'Sentimiento']).size().reset_index(name='Cantidad')
            if not df_trend.empty:
                fig_linea = px.bar(df_trend, x='Fecha', y='Cantidad', color='Sentimiento',
                                    color_discrete_map={'Positivo':'#2ECC71', 'Negativo':'#E74C3C', 'Neutro':'#F1C40F'})
                st.plotly_chart(fig_linea, use_container_width=True)
            else:
                st.info("No hay suficientes datos para ver la evolución.")

        st.subheader("📰 Últimos Titulares Detectados")
        
        for index, row in df.iterrows():
            with st.container():
                col_icono, col_texto = st.columns([1, 10])
                with col_icono:
                    st.markdown(f"## {row['Icono']}")
                with col_texto:
                    st.markdown(f"**[{row['Titular']}]({row['Link']})**")
                    st.caption(f"📅 {row['Fecha']} | 🏢 {row['Fuente']} | ⭐ IA: {row['Score']}/5")
                st.divider()
            
    else:
        st.warning("No se encontraron resultados en ese rango de fechas. Intenta ampliar el rango (ej: busca desde el mes pasado).")

else:
    st.info("👈 Selecciona 'Redes Sociales' en el menú para buscar en TikTok, Instagram y X.")
