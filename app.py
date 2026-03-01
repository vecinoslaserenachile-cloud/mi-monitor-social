import streamlit as st
import feedparser
import pandas as pd
from transformers import pipeline
from datetime import datetime
import plotly.express as px # Para gráficos bonitos

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Sentinel AI Dashboard", layout="wide")

st.title("📡 Sentinel AI: Monitor de Medios")
st.markdown("Monitor de reputación y análisis de sentimiento en tiempo real.")

# --- BARRA LATERAL (CONTROLES) ---
st.sidebar.header("Configuración")
tema_busqueda = st.sidebar.text_input("Tema a monitorear en Google News", "Tecnología")
btn_actualizar = st.sidebar.button("🔄 Ejecutar Análisis")

# --- FUNCIONES (EL CEREBRO) ---
@st.cache_resource # Esto evita cargar la IA cada vez, lo hace más rápido
def cargar_modelo():
    return pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

def analizar_noticias(tema):
    analizador = cargar_modelo()
    # URL dinámica de Google News
    url = f"https://news.google.com/rss/search?q={tema}&hl=es-419&gl=CL&ceid=CL:es-419"
    noticias = feedparser.parse(url)
    
    resultados = []
    barra_progreso = st.progress(0)
    total = min(len(noticias.entries), 10) # Analizamos máx 10 noticias para ir rápido
    
    for i, noticia in enumerate(noticias.entries[:10]):
        titulo = noticia.title
        link = noticia.link
        fecha = datetime.now().strftime("%H:%M")
        
        # IA Analiza
        pred = analizador(titulo)[0]
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
            "Hora": fecha,
            "Fuente": "Google News",
            "Titular": titulo,
            "Sentimiento": sent,
            "Icono": color,
            "Score": score,
            "Link": link
        })
        barra_progreso.progress((i + 1) / total)
        
    barra_progreso.empty()
    return pd.DataFrame(resultados)

# --- INTERFAZ PRINCIPAL ---

if btn_actualizar:
    with st.spinner(f'Analizando "{tema_busqueda}" en la web...'):
        df = analizar_noticias(tema_busqueda)
        
    if not df.empty:
        # MÉTRICAS ARRIBA
        col1, col2, col3 = st.columns(3)
        positivos = len(df[df['Sentimiento'] == 'Positivo'])
        negativos = len(df[df['Sentimiento'] == 'Negativo'])
        
        col1.metric("Noticias Positivas", positivos, delta="🟢 Buena reputación")
        col2.metric("Noticias Negativas", negativos, delta="-🔴 Riesgo", delta_color="inverse")
        col3.metric("Total Analizado", len(df))
        
        # GRÁFICOS
        c1, c2 = st.columns([2, 1])
        
        with c1:
            st.subheader("Tendencia de Sentimiento")
            fig_torta = px.pie(df, names='Sentimiento', title='Distribución de Opinión', 
                               color='Sentimiento',
                               color_discrete_map={'Positivo':'green', 'Negativo':'red', 'Neutro':'gold'})
            st.plotly_chart(fig_torta, use_container_width=True)
            
        with c2:
            st.subheader("Últimos Titulares")
            for index, row in df.iterrows():
                st.markdown(f"{row['Icono']} **[{row['Titular']}]({row['Link']})**")
                st.caption(f"Score IA: {row['Score']}/5")
                st.divider()

        # TABLA DE DATOS
        with st.expander("Ver tabla completa de datos"):
            st.dataframe(df)
            
    else:
        st.warning("No se encontraron noticias recientes.")

else:
    st.info("👈 Escribe un tema en la barra lateral y presiona 'Ejecutar Análisis'")
