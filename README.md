# MarkItDown Dashboard

## Descripción del Proyecto
MarkItDown Dashboard es una aplicación web backend (construida en Python con FastAPI) diseñada para extraer y convertir texto limpio en formato Markdown desde una gran variedad de archivos y fuentes (PDFs, documentos de Office, imágenes, archivos de audio, páginas web, etc.). La aplicación ofrece una interfaz visual, de forma que el usuario sube los archivos y el servidor devuelve tanto el contenido extraído en pantalla como opciones para descargar el resultado en Markdown puro o generar un PDF básico a partir de él.

## Arquitectura y Tecnologías
- **Framework Backend:** FastAPI (Python).
- **Conversor Core:** `markitdown` (Librería principal).
- **Conversor PDF:** `markdown-pdf` (Genera versiones PDF descargables del texto extraído).
- **Despliegue:** Preparado para funcionar de forma "Serverless" nativa en **Vercel** (`vercel.json`).
- **Archivos Estáticos:** UI servida mediante HTML/CSS planos gestionados desde el directorio `/app/static/`.

## Cómo Ejecutar en Local
1. Abre un terminal en el directorio del proyecto (`c:\Users\Gaming\Documents\MarkItDown`).
2. Instala las dependencias necesarias:
   ```bash
   pip install -r requirements.txt
   ```
3. Arranca el servidor local con `uvicorn`:
   ```bash
   uvicorn app.main:app --reload
   ```
4. Accede a la interfaz web en: `http://localhost:8000`

## Cómo Desplegar (Vercel)
El proyecto está optimizado para funcionar en **Vercel**. Todo cambio que se suba a la rama `main` de GitHub detonará una publicación automática.
1. Haz commit y push de tus cambios a la rama `main`:
   ```bash
   git add .
   git commit -m "Descripción de tu cambio"
   git push origin main
   ```
2. Vercel leerá el archivo `vercel.json` e iniciará la compilación.
3. El proyecto está vivo en: [https://markitdown-1zg1.vercel.app](https://markitdown-1zg1.vercel.app)

**Nota sobre Vercel:** 
- Evita forzar enrutamientos estáticos en `vercel.json`. FastAPI se encarga de montar el directorio `/static/`.
- Usa solo dependencias estables en `requirements.txt` (ej. `markitdown[pdf]`), ya que Vercel rechaza paquetes en fase beta (como sucedía con `markitdown[all]` debido a plugins experimentales de Azure).

## Estado Actual y Próximos Pasos (Historial)
- **Logrado:** Se ha solventado un conflicto de dependencias en Vercel, se ha arreglado el CSS eliminando una regla estricta en el `vercel.json`, y la app está 100% funcional y conectada en vivo desde el dashboard de la web principal `mbainative.com`.
- **Consideración:** El proceso de "Descargar en PDF" usa una librería (`markdown-pdf`) que crea un PDF en blanco y negro muy plano con el texto extraído. Si se desea un PDF con estilos CSS aplicados en el futuro, habrá que reemplazar esta librería por un motor más pesado (como `WeasyPrint` o `pdfkit`), aunque esto podría sobrepasar los límites gratuitos de Vercel.
