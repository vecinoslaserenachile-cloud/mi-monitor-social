import feedparser
import pandas as pd
from transformers import pipeline
from datetime import datetime

# --- 1. CONFIGURACIÓN ---
print("🧠 Cargando cerebro digital... (Espera un momento)")
analizador = pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

# Fuentes de noticias (RSS)
fuentes = {
    "Google News (Tecnología)": "https://news.google.com/rss/search?q=tecnologia&hl=es-419&gl=CL&ceid=CL:es-419",
    "El País (Internacional)": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/internacional/portada",
    # Agrega aquí más fuentes si quieres
}

datos_recolectados = []

# --- 2. EL PROCESO DE MONITOREO ---
print("\n🕵️  Iniciando rastreo de medios...\n")

for nombre_fuente, url in fuentes.items():
    print(f"📡 Leyendo: {nombre_fuente}...")
    try:
        noticias = feedparser.parse(url)
        
        # Analizamos las primeras 5 noticias de cada fuente
        for noticia in noticias.entries[:5]:
            titulo = noticia.title
            link = noticia.link
            fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
            
            # La IA lee y clasifica
            resultado = analizador(titulo)[0]
            estrellas = int(resultado['label'].split()[0])
            
            if estrellas <= 2:
                sentimiento = "🔴 NEGATIVO"
            elif estrellas == 3:
                sentimiento = "🟡 NEUTRO"
            else:
                sentimiento = "🟢 POSITIVO"

            datos_recolectados.append({
                "Fecha": fecha,
                "Fuente": nombre_fuente,
                "Titular": titulo,
                "Sentimiento": sentimiento,
                "Score IA": f"{estrellas}/5",
                "Link": link
            })
    except Exception as e:
        print(f"⚠️ Error leyendo {nombre_fuente}: {e}")

# --- 3. GUARDAR EL REPORTE EN EXCEL ---
if datos_recolectados:
    print("\n💾 Guardando resultados en Excel...")
    
    # Creamos la tabla
    df = pd.DataFrame(datos_recolectados)
    
    # Nombre del archivo con la fecha de hoy (ej: reporte_2023-10-27.xlsx)
    nombre_archivo = f"reporte_sentimiento_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    
    # Guardamos el archivo
    df.to_excel(nombre_archivo, index=False)
    
    print(f"✅ ¡ÉXITO! Se ha creado el archivo: {nombre_archivo}")
    print(f"   (Búscalo en la barra lateral izquierda para descargarlo)")
else:
    print("❌ No se encontraron noticias para analizar.")
