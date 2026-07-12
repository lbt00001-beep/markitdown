# MarkItDown Dashboard

Copyright (c) 2026 Luis Benedicto Tuzón. Creado con GPT-5.6 Sol.

Una app local para usar [MarkItDown de Microsoft](https://github.com/microsoft/markitdown) desde un cuadro de mandos web. Convierte archivos, lotes, texto y direcciones a Markdown; permite configurar plugins, IA y servicios de Azure; y ofrece historial y descargas.

## Requisitos

- Python 3.10 o superior

## Instalacion

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Ejecucion

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Abre http://127.0.0.1:8000.

En Windows tambien puedes abrir `EJECUTAR.bat`.

## Version portatil para Windows

Para crear una version que funcione sin instalar Python:

```bat
CREAR_EXE.bat
```

El proceso genera:

- `dist\MarkItDownDashboard\MarkItDownDashboard.exe`: ejecutable dentro de su carpeta de dependencias.
- `dist\MarkItDownDashboard-Windows.zip`: archivo listo para compartir.

El destinatario debe descomprimir el ZIP completo y abrir `MarkItDownDashboard.exe`. No debe sacar solamente el `.exe` de la carpeta. Los resultados se guardan en `%LOCALAPPDATA%\MarkItDown Dashboard\outputs`.

Una segunda ejecucion cierra el servidor y las ventanas de navegador que pertenecen a la ejecucion anterior. El programa usa un perfil de navegador separado para no cerrar las pestañas personales.

## Funcionalidades

- Conversion de archivos individuales o multiples.
- Selector para revisar cualquier resultado de un lote y ZIP para descargar el lote completo.
- Conversion de URLs HTTP/HTTPS con validacion basica de destinos privados.
- Conversion de texto pegado mediante `convert_stream`.
- Conversion de URI avanzada: `http`, `https`, `data` y `file` si el usuario lo permite.
- Descarga de Markdown convertido.
- Historial de trabajos de la sesion.
- Opciones de MarkItDown:
  - Conversores internos activables.
  - Plugins de terceros.
  - Pistas de extension, MIME type y charset.
  - Conservacion de data URIs completas.
  - Modo HTML estricto o recuperacion como texto si el HTML es demasiado complejo.
  - Ruta de `exiftool`.
  - Style map para Word/DOCX.
  - Descripciones de imagen con LLM compatible con OpenAI.
  - Azure Document Intelligence.
  - Azure Content Understanding.
- Vista de ayuda para usuarios no tecnicos.

## Variables opcionales

- `OPENAI_API_KEY`: necesaria si activas descripciones de imagen con LLM.
- `OPENAI_BASE_URL`: direccion opcional de una API compatible con OpenAI.
- `AZURE_API_KEY`: clave opcional para los dos servicios de Azure. Sin ella, MarkItDown intenta usar la sesion de Azure del ordenador.
- `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT`: endpoint por defecto para Document Intelligence.
- `AZURE_CONTENT_UNDERSTANDING_ENDPOINT`: endpoint por defecto para Content Understanding.
- `EXIFTOOL_PATH`: ruta opcional a exiftool para metadatos.

Las claves tambien se pueden escribir en Opciones avanzadas. Se usan para la conversion actual y no se guardan en archivos ni en el historial.

## OpenAI y Azure

- OpenAI se usa unicamente para describir imagenes cuando se activa la opcion LLM. La imagen se envia a la API y su descripcion se incorpora al Markdown. Consulta la [guia oficial de imagenes y vision](https://developers.openai.com/api/docs/guides/images-vision).
- Azure Document Intelligence mejora la lectura de documentos complejos o escaneados, incluidas tablas y estructura.
- Azure Content Understanding analiza documentos, imagenes, audio y video y puede devolver campos estructurados. Consulta la [documentacion oficial de Content Understanding](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/overview).
- Estos servicios funcionan por internet y pueden cobrar por uso. Una cuenta de ChatGPT y una cuenta de la API de OpenAI tienen facturacion separada.
- Cada persona debe usar sus propias claves. Nunca incluyas una clave personal dentro del ZIP que compartas.

## Cobertura de MarkItDown 0.1.6

- Conversores incluidos: texto, HTML, RSS/Atom, Wikipedia, YouTube, resultados de Bing, CSV, PDF, Word, PowerPoint, Excel moderno y antiguo, imagen JPEG/PNG, audio WAV/MP3/M4A/MP4, Jupyter, Outlook MSG, EPUB y ZIP.
- Entradas de la API: archivo local, stream o texto pegado, URL HTTP/HTTPS, `data:` y `file:` autorizado.
- Extensiones: conversores internos, plugins instalados, pistas de extension/MIME/charset, data URIs, ExifTool, style map de Word y descripciones de imagen con LLM.
- Azure Document Intelligence: documentos Office, HTML, PDF y las imagenes admitidas por la dependencia.
- Azure Content Understanding: documentos, correo, imagen, audio y video; incluye seleccion de tipos y analyzer propio.

La pantalla Formatos separa lo que funciona en el ordenador de los formatos que necesitan Azure. Content Understanding realiza llamadas de pago al servicio para los tipos enviados.

MarkItDown accede a archivos y URLs con los permisos del proceso local. La app bloquea por defecto destinos privados y `file://`, salvo permiso explicito del usuario.
