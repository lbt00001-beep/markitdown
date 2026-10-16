from __future__ import annotations

import ipaddress
import codecs
import mimetypes
import os
import secrets
import shutil
import socket
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from io import BytesIO
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, entry_points, version
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

try:
    from markitdown import MarkItDown, StreamInfo
except Exception as exc:  # pragma: no cover - surfaced through /api/health
    MARKITDOWN_IMPORT_ERROR = f"MarkItDown no se pudo importar: {exc}"
    MarkItDown = None  # type: ignore[assignment]
    StreamInfo = None  # type: ignore[assignment]
else:
    MARKITDOWN_IMPORT_ERROR = None


ROOT = Path(__file__).resolve().parent.parent
BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", ROOT))
STATIC_DIR = BUNDLE_ROOT / "app" / "static"
if os.environ.get("VERCEL"):
    DATA_DIR = Path("/tmp")
else:
    DATA_DIR = (
        Path(os.getenv("LOCALAPPDATA", Path.home())) / "MarkItDown Dashboard"
        if getattr(sys, "frozen", False)
        else ROOT / "data"
    )
OUTPUT_DIR = DATA_DIR / "outputs"
UPLOAD_DIR = DATA_DIR / "uploads"
BATCH_DIR = DATA_DIR / "batches"

SUPPORTED_GROUPS = [
    {
        "name": "Documentos (en el ordenador)",
        "extensions": [".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".epub"],
        "description": "PDF, Word, PowerPoint, Excel y libros EPUB sin enviar el archivo a servicios externos.",
    },
    {
        "name": "Web y texto (en el ordenador)",
        "extensions": [".html", ".htm", ".csv", ".json", ".xml", ".txt", ".md", ".rss", ".atom"],
        "description": "Paginas HTML, fuentes RSS o Atom y archivos de texto o datos estructurados.",
    },
    {
        "name": "Imagen y audio (en el ordenador)",
        "extensions": [".png", ".jpg", ".jpeg", ".wav", ".mp3", ".m4a", ".mp4"],
        "description": "Metadatos, descripcion opcional de imagenes y transcripcion basica de audio. MP4 se trata como audio.",
    },
    {
        "name": "Codigo, correo y comprimidos",
        "extensions": [".ipynb", ".msg", ".zip"],
        "description": "Cuadernos Jupyter, mensajes de Outlook y ZIP, cuyos archivos compatibles se convierten uno tras otro.",
    },
    {
        "name": "Azure Document Intelligence",
        "extensions": [".pdf", ".docx", ".pptx", ".xlsx", ".html", ".jpg", ".jpeg", ".png", ".bmp", ".tiff"],
        "description": "Analisis avanzado de documentos e imagenes. Requiere un endpoint de Azure y permisos o clave.",
    },
    {
        "name": "Azure Content Understanding: documentos",
        "extensions": [".pdf", ".docx", ".pptx", ".xlsx", ".html", ".txt", ".md", ".rtf", ".xml", ".eml", ".msg"],
        "description": "Extraccion avanzada y campos estructurados. Requiere Azure Content Understanding.",
    },
    {
        "name": "Azure Content Understanding: multimedia",
        "extensions": [
            ".jpg", ".jpeg", ".jpe", ".png", ".bmp", ".tiff", ".heif", ".heic", ".mp4", ".m4v", ".mov", ".avi",
            ".mkv", ".webm", ".flv", ".wmv", ".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".wma",
        ],
        "description": "Imagen, audio y video mediante Azure. Es la opcion de MarkItDown que analiza video completo.",
    },
    {
        "name": "Direcciones y paginas web",
        "extensions": ["http://", "https://", "data:", "file:", "YouTube", "Wikipedia", "Bing SERP"],
        "description": "Paginas web, direcciones especiales y conversores especificos para varios sitios.",
    },
]


@dataclass
class ConversionJob:
    id: str
    batch_id: str | None
    source_name: str
    source_type: str
    status: str
    created_at: float
    duration_ms: int
    output_path: str | None = None
    markdown_chars: int = 0
    error: str | None = None
    options: dict[str, Any] | None = None


jobs: dict[str, ConversionJob] = {}

app = FastAPI(title="MarkItDown Dashboard", version="1.0.1")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    BATCH_DIR.mkdir(parents=True, exist_ok=True)


def configure_audio_backend() -> str | None:
    ffmpeg_path = shutil.which("ffmpeg")
    if ffmpeg_path:
        return ffmpeg_path

    try:
        import imageio_ffmpeg
        from pydub import AudioSegment

        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        AudioSegment.converter = ffmpeg_path
        return ffmpeg_path
    except Exception:
        return None


FFMPEG_PATH = configure_audio_backend()


def build_converter(
    *,
    enable_builtins: bool,
    enable_plugins: bool,
    strict_html: bool,
    use_llm: bool,
    openai_api_key: str | None,
    openai_base_url: str | None,
    llm_model: str | None,
    llm_prompt: str | None,
    exiftool_path: str | None,
    style_map: str | None,
    azure_api_key: str | None,
    docintel_endpoint: str | None,
    docintel_api_version: str | None,
    docintel_file_types: list[Any] | None,
    cu_endpoint: str | None,
    cu_analyzer_id: str | None,
    cu_file_types: list[Any] | None,
    **_: Any,
) -> Any:
    if MarkItDown is None:
        raise HTTPException(
            status_code=503,
            detail=f"{MARKITDOWN_IMPORT_ERROR or 'MarkItDown no esta instalado.'} Ejecuta: python -m pip install -r requirements.txt",
        )

    kwargs: dict[str, Any] = {"enable_builtins": enable_builtins, "enable_plugins": enable_plugins}

    if exiftool_path:
        kwargs["exiftool_path"] = exiftool_path

    if style_map:
        kwargs["style_map"] = style_map

    if docintel_endpoint:
        kwargs["docintel_endpoint"] = docintel_endpoint
        if azure_api_key:
            from azure.core.credentials import AzureKeyCredential

            kwargs["docintel_credential"] = AzureKeyCredential(azure_api_key)
        if docintel_api_version:
            kwargs["docintel_api_version"] = docintel_api_version
        if docintel_file_types:
            kwargs["docintel_file_types"] = docintel_file_types

    if cu_endpoint:
        kwargs["cu_endpoint"] = cu_endpoint
        if azure_api_key:
            from azure.core.credentials import AzureKeyCredential

            kwargs["cu_credential"] = AzureKeyCredential(azure_api_key)
        if cu_analyzer_id:
            kwargs["cu_analyzer_id"] = cu_analyzer_id
        if cu_file_types:
            kwargs["cu_file_types"] = cu_file_types

    if use_llm:
        api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise HTTPException(
                status_code=400,
                detail="Activa OPENAI_API_KEY para usar descripciones de imagen con LLM.",
            )
        try:
            from openai import OpenAI
        except Exception as exc:  # pragma: no cover
            raise HTTPException(status_code=503, detail=f"No se pudo cargar OpenAI: {exc}") from exc

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if openai_base_url:
            client_kwargs["base_url"] = openai_base_url
        kwargs["llm_client"] = OpenAI(**client_kwargs)
        kwargs["llm_model"] = llm_model or "gpt-4o"
        if llm_prompt:
            kwargs["llm_prompt"] = llm_prompt

    try:
        return MarkItDown(**kwargs)
    except TypeError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Las opciones seleccionadas no son compatibles con esta version de MarkItDown: {exc}",
        ) from exc


def result_text(result: Any) -> str:
    for attr in ("markdown", "text_content", "text"):
        value = getattr(result, attr, None)
        if isinstance(value, str):
            return value
    return str(result)


def save_markdown(source_name: str, markdown: str) -> Path:
    ensure_dirs()
    base_name = Path(source_name).stem or "conversion"
    safe_base = "".join(ch if ch.isalnum() or ch in ("-", "_") else "-" for ch in base_name).strip("-")
    output_path = OUTPUT_DIR / f"{safe_base}-{uuid.uuid4().hex[:8]}.md"
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def create_job(
    *,
    batch_id: str | None = None,
    source_name: str,
    source_type: str,
    status: str,
    started_at: float,
    output_path: Path | None = None,
    markdown: str = "",
    error: str | None = None,
    options: dict[str, Any] | None = None,
) -> ConversionJob:
    job = ConversionJob(
        id=uuid.uuid4().hex,
        batch_id=batch_id,
        source_name=source_name,
        source_type=source_type,
        status=status,
        created_at=time.time(),
        duration_ms=int((time.perf_counter() - started_at) * 1000),
        output_path=str(output_path) if output_path else None,
        markdown_chars=len(markdown),
        error=error,
        options=options,
    )
    jobs[job.id] = job
    return job


def convert_local_file(path: Path, display_name: str, options: dict[str, Any], batch_id: str | None = None) -> tuple[ConversionJob, str]:
    started_at = time.perf_counter()
    try:
        converter = build_converter(**options)
        stream_info = stream_info_from_options(options, filename=display_name, local_path=str(path))
        if hasattr(converter, "convert_local"):
            result = converter.convert_local(path, stream_info=stream_info, **conversion_kwargs(options))
        else:
            result = converter.convert(path, stream_info=stream_info, **conversion_kwargs(options))
        markdown = result_text(result)
        output_path = save_markdown(display_name, markdown)
        job = create_job(
            batch_id=batch_id,
            source_name=display_name,
            source_type="archivo",
            status="completed",
            started_at=started_at,
            output_path=output_path,
            markdown=markdown,
            options=safe_options(options),
        )
        return job, markdown
    except HTTPException:
        raise
    except Exception as exc:
        job = create_job(
            batch_id=batch_id,
            source_name=display_name,
            source_type="archivo",
            status="failed",
            started_at=started_at,
            error=str(exc),
            options=safe_options(options),
        )
        return job, ""


def safe_options(options: dict[str, Any]) -> dict[str, Any]:
    return {
        "enable_builtins": options.get("enable_builtins", True),
        "enable_plugins": options.get("enable_plugins", False),
        "strict_html": options.get("strict_html", False),
        "keep_data_uris": options.get("keep_data_uris", False),
        "use_llm": options.get("use_llm", False),
        "has_openai_api_key": bool(options.get("openai_api_key")),
        "openai_base_url": options.get("openai_base_url") or None,
        "llm_model": options.get("llm_model") or None,
        "has_llm_prompt": bool(options.get("llm_prompt")),
        "extension_hint": options.get("extension_hint") or None,
        "mime_type_hint": options.get("mime_type_hint") or None,
        "charset_hint": options.get("charset_hint") or None,
        "has_exiftool_path": bool(options.get("exiftool_path")),
        "has_style_map": bool(options.get("style_map")),
        "has_azure_api_key": bool(options.get("azure_api_key")),
        "docintel_enabled": bool(options.get("docintel_endpoint")),
        "docintel_api_version": options.get("docintel_api_version") or None,
        "docintel_file_types": [item.value for item in options.get("docintel_file_types") or []],
        "cu_enabled": bool(options.get("cu_endpoint")),
        "cu_analyzer_id": options.get("cu_analyzer_id") or None,
        "cu_file_types": [item.value for item in options.get("cu_file_types") or []],
    }


def parse_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").lower() in {"1", "true", "yes", "on"}


def form_options(
    enable_builtins: str | bool | None,
    enable_plugins: str | bool | None,
    strict_html: str | bool | None,
    keep_data_uris: str | bool | None,
    use_llm: str | bool | None,
    openai_api_key: str | None,
    openai_base_url: str | None,
    llm_model: str | None,
    llm_prompt: str | None,
    extension_hint: str | None,
    mime_type_hint: str | None,
    charset_hint: str | None,
    exiftool_path: str | None,
    style_map: str | None,
    azure_api_key: str | None,
    docintel_endpoint: str | None,
    docintel_api_version: str | None,
    docintel_file_types: str | None,
    cu_endpoint: str | None,
    cu_analyzer_id: str | None,
    cu_file_types: str | None,
) -> dict[str, Any]:
    return {
        "enable_builtins": parse_bool("true" if enable_builtins is None else enable_builtins),
        "enable_plugins": parse_bool(enable_plugins),
        "strict_html": parse_bool(strict_html),
        "keep_data_uris": parse_bool(keep_data_uris),
        "use_llm": parse_bool(use_llm),
        "openai_api_key": (openai_api_key or "").strip() or None,
        "openai_base_url": (openai_base_url or os.getenv("OPENAI_BASE_URL") or "").strip() or None,
        "llm_model": (llm_model or "").strip() or None,
        "llm_prompt": (llm_prompt or "").strip() or None,
        "extension_hint": normalize_extension(extension_hint),
        "mime_type_hint": normalize_mime_type(mime_type_hint),
        "charset_hint": normalize_charset(charset_hint),
        "exiftool_path": (exiftool_path or os.getenv("EXIFTOOL_PATH") or "").strip() or None,
        "style_map": (style_map or "").strip() or None,
        "azure_api_key": (azure_api_key or "").strip() or None,
        "docintel_endpoint": (docintel_endpoint or os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT") or "").strip()
        or None,
        "docintel_api_version": (docintel_api_version or "").strip() or None,
        "docintel_file_types": parse_docintel_file_types(docintel_file_types),
        "cu_endpoint": (cu_endpoint or os.getenv("AZURE_CONTENT_UNDERSTANDING_ENDPOINT") or "").strip() or None,
        "cu_analyzer_id": (cu_analyzer_id or "").strip() or None,
        "cu_file_types": parse_cu_file_types(cu_file_types),
    }


def normalize_extension(value: str | None) -> str | None:
    value = (value or "").strip().lower()
    if not value:
        return None
    return value if value.startswith(".") else f".{value}"


def normalize_mime_type(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    if value.count("/") != 1:
        raise HTTPException(status_code=400, detail="El MIME type debe tener formato tipo/subtipo, por ejemplo text/html.")
    return value


def normalize_charset(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return codecs.lookup(value).name
    except LookupError as exc:
        raise HTTPException(status_code=400, detail=f"Charset no valido: {value}") from exc


def parse_docintel_file_types(value: str | None) -> list[Any] | None:
    names = split_csv(value)
    if not names:
        return None
    from markitdown.converters import DocumentIntelligenceFileType

    return parse_enum_values(names, DocumentIntelligenceFileType, "Document Intelligence")


def parse_cu_file_types(value: str | None) -> list[Any] | None:
    names = split_csv(value)
    if not names:
        return None
    from markitdown.converters import ContentUnderstandingFileType

    return parse_enum_values(names, ContentUnderstandingFileType, "Content Understanding")


def split_csv(value: str | None) -> list[str]:
    return [item.strip().lower() for item in (value or "").split(",") if item.strip()]


def parse_enum_values(names: list[str], enum_type: Any, label: str) -> list[Any]:
    values = []
    for name in names:
        try:
            values.append(enum_type(name))
        except ValueError as exc:
            valid = ", ".join(item.value for item in enum_type)
            raise HTTPException(status_code=400, detail=f"Tipo no valido para {label}: {name}. Valores: {valid}") from exc
    return values


def stream_info_from_options(
    options: dict[str, Any],
    *,
    filename: str | None = None,
    local_path: str | None = None,
    url: str | None = None,
) -> Any:
    if StreamInfo is None:
        return None
    return StreamInfo(
        mimetype=options.get("mime_type_hint"),
        extension=options.get("extension_hint"),
        charset=options.get("charset_hint"),
        filename=filename,
        local_path=local_path,
        url=url,
    )


def conversion_kwargs(options: dict[str, Any]) -> dict[str, Any]:
    return {
        "keep_data_uris": options.get("keep_data_uris", False),
        "strict": options.get("strict_html", False),
    }


def assert_public_http_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Introduce una URL HTTP o HTTPS valida.")

    host = parsed.hostname
    if host.lower() in {"localhost"}:
        raise HTTPException(status_code=400, detail="No se permiten destinos locales.")

    try:
        candidates = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise HTTPException(status_code=400, detail=f"No se pudo resolver el host: {host}") from exc

    for candidate in candidates:
        address = candidate[4][0]
        try:
            ip = ipaddress.ip_address(address)
        except ValueError:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise HTTPException(status_code=400, detail="No se permiten URLs hacia redes privadas o locales.")

    return url.strip()


def assert_allowed_uri(uri: str, *, allow_file_uri: bool) -> str:
    uri = uri.strip()
    parsed = urlparse(uri)
    if parsed.scheme in {"http", "https"}:
        return assert_public_http_url(uri)
    if parsed.scheme == "data":
        return uri
    if parsed.scheme == "file":
        if not allow_file_uri:
            raise HTTPException(status_code=400, detail="Activa 'Permitir file://' para convertir rutas locales por URI.")
        return uri
    raise HTTPException(status_code=400, detail="Usa una URI http, https, data o file.")


def safe_archive_name(source_name: str, used_names: set[str]) -> str:
    stem = "".join(
        ch if ch.isalnum() or ch in ("-", "_") else "-"
        for ch in Path(source_name).stem
    ).strip("-") or "conversion"
    candidate = f"{stem}.md"
    counter = 2
    while candidate in used_names:
        candidate = f"{stem}-{counter}.md"
        counter += 1
    used_names.add(candidate)
    return candidate


@app.on_event("startup")
def startup() -> None:
    ensure_dirs()


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict[str, Any]:
    try:
        markitdown_version = version("markitdown")
    except PackageNotFoundError:
        markitdown_version = None
    return {
        "ok": MarkItDown is not None,
        "markitdown_available": MarkItDown is not None,
        "markitdown_import_error": MARKITDOWN_IMPORT_ERROR,
        "markitdown_version": markitdown_version,
        "instance_id": os.getenv("MARKITDOWN_INSTANCE_ID"),
        "openai_key_available": bool(os.getenv("OPENAI_API_KEY")),
        "azure_api_key_available": bool(os.getenv("AZURE_API_KEY")),
        "azure_docintel_endpoint_available": bool(os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")),
        "azure_cu_endpoint_available": bool(os.getenv("AZURE_CONTENT_UNDERSTANDING_ENDPOINT")),
        "exiftool_available": bool(os.getenv("EXIFTOOL_PATH")),
        "ffmpeg_available": bool(FFMPEG_PATH),
        "output_dir": str(OUTPUT_DIR),
    }


@app.post("/api/shutdown", include_in_schema=False)
def shutdown(x_shutdown_token: str | None = Header(None)) -> dict[str, bool]:
    expected_token = os.getenv("MARKITDOWN_SHUTDOWN_TOKEN")
    if not expected_token or not x_shutdown_token or not secrets.compare_digest(expected_token, x_shutdown_token):
        raise HTTPException(status_code=404, detail="No disponible.")

    threading.Timer(0.35, os._exit, args=(0,)).start()
    return {"ok": True}


@app.get("/api/formats")
def formats() -> dict[str, Any]:
    return {"groups": SUPPORTED_GROUPS}


@app.get("/api/plugins")
def plugins() -> dict[str, Any]:
    plugin_entry_points = list(entry_points(group="markitdown.plugin"))
    return {
        "plugins": [
            {"name": entry_point.name, "value": entry_point.value}
            for entry_point in plugin_entry_points
        ]
    }


@app.get("/api/jobs")
def list_jobs() -> dict[str, Any]:
    ordered = sorted(jobs.values(), key=lambda item: item.created_at, reverse=True)
    return {"jobs": [asdict(job) for job in ordered]}


@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str) -> FileResponse:
    job = jobs.get(job_id)
    if not job or not job.output_path:
        raise HTTPException(status_code=404, detail="No se encontro el resultado.")
    output_path = Path(job.output_path)
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="El archivo de salida ya no existe.")
    return FileResponse(output_path, media_type="text/markdown", filename=output_path.name)


@app.get("/api/jobs/{job_id}/pdf")
def download_pdf(job_id: str) -> FileResponse:
    job = jobs.get(job_id)
    if not job or not job.output_path:
        raise HTTPException(status_code=404, detail="No se encontro el resultado.")
    output_path = Path(job.output_path)
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="El archivo de salida ya no existe.")
    
    pdf_path = output_path.with_suffix(".pdf")
    if not pdf_path.exists():
        try:
            from markdown_pdf import MarkdownPdf, Section
        except ImportError:
            raise HTTPException(status_code=503, detail="Libreria markdown-pdf no instalada. Instala con: pip install markdown-pdf")
        
        try:
            pdf = MarkdownPdf(toc_level=2)
            content = output_path.read_text(encoding="utf-8")
            pdf.add_section(Section(content))
            pdf.save(str(pdf_path))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error al generar el PDF: {e}")

    return FileResponse(pdf_path, media_type="application/pdf", filename=pdf_path.name)


@app.get("/api/batches/{batch_id}/download")
def download_batch(batch_id: str) -> FileResponse:
    batch_jobs = [
        job
        for job in jobs.values()
        if job.batch_id == batch_id and job.status == "completed" and job.output_path
    ]
    if not batch_jobs:
        raise HTTPException(status_code=404, detail="No hay resultados completados para este lote.")

    ensure_dirs()
    archive_path = BATCH_DIR / f"markitdown-lote-{batch_id}.zip"
    used_names: set[str] = set()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for job in batch_jobs:
            output_path = Path(job.output_path or "")
            if output_path.exists():
                archive.write(output_path, arcname=safe_archive_name(job.source_name, used_names))

    if not archive_path.exists():
        raise HTTPException(status_code=404, detail="No se pudo crear el ZIP del lote.")
    return FileResponse(archive_path, media_type="application/zip", filename=archive_path.name)


@app.get("/api/jobs/{job_id}/raw", response_class=PlainTextResponse)
def raw_job(job_id: str) -> str:
    job = jobs.get(job_id)
    if not job or not job.output_path:
        raise HTTPException(status_code=404, detail="No se encontro el resultado.")
    output_path = Path(job.output_path)
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="El archivo de salida ya no existe.")
    return output_path.read_text(encoding="utf-8")


@app.post("/api/convert/files")
async def convert_files(
    files: list[UploadFile] = File(...),
    enable_builtins: str | None = Form(None),
    enable_plugins: str | None = Form(None),
    strict_html: str | None = Form(None),
    keep_data_uris: str | None = Form(None),
    use_llm: str | None = Form(None),
    openai_api_key: str | None = Form(None),
    openai_base_url: str | None = Form(None),
    llm_model: str | None = Form(None),
    llm_prompt: str | None = Form(None),
    extension_hint: str | None = Form(None),
    mime_type_hint: str | None = Form(None),
    charset_hint: str | None = Form(None),
    exiftool_path: str | None = Form(None),
    style_map: str | None = Form(None),
    azure_api_key: str | None = Form(None),
    docintel_endpoint: str | None = Form(None),
    docintel_api_version: str | None = Form(None),
    docintel_file_types: str | None = Form(None),
    cu_endpoint: str | None = Form(None),
    cu_analyzer_id: str | None = Form(None),
    cu_file_types: str | None = Form(None),
) -> JSONResponse:
    if not files:
        raise HTTPException(status_code=400, detail="Selecciona al menos un archivo.")

    ensure_dirs()
    options = form_options(
        enable_builtins,
        enable_plugins,
        strict_html,
        keep_data_uris,
        use_llm,
        openai_api_key,
        openai_base_url,
        llm_model,
        llm_prompt,
        extension_hint,
        mime_type_hint,
        charset_hint,
        exiftool_path,
        style_map,
        azure_api_key,
        docintel_endpoint,
        docintel_api_version,
        docintel_file_types,
        cu_endpoint,
        cu_analyzer_id,
        cu_file_types,
    )
    converted: list[dict[str, Any]] = []
    latest_markdown = ""
    batch_id = uuid.uuid4().hex[:12]

    with tempfile.TemporaryDirectory(dir=UPLOAD_DIR) as temp_dir:
        temp_root = Path(temp_dir)
        for upload in files:
            filename = Path(upload.filename or "upload").name
            local_path = temp_root / f"{uuid.uuid4().hex}-{filename}"
            content = await upload.read()
            local_path.write_bytes(content)
            job, markdown = convert_local_file(local_path, filename, options, batch_id=batch_id)
            latest_markdown = markdown or latest_markdown
            converted.append(asdict(job))

    completed_count = sum(1 for job in converted if job["status"] == "completed")
    return JSONResponse(
        {
            "batch_id": batch_id,
            "batch_download_url": f"/api/batches/{batch_id}/download" if completed_count else None,
            "completed_count": completed_count,
            "jobs": converted,
            "markdown": latest_markdown,
        }
    )


@app.post("/api/convert/url")
async def convert_url(
    url: str = Form(...),
    enable_builtins: str | None = Form(None),
    enable_plugins: str | None = Form(None),
    strict_html: str | None = Form(None),
    keep_data_uris: str | None = Form(None),
    use_llm: str | None = Form(None),
    openai_api_key: str | None = Form(None),
    openai_base_url: str | None = Form(None),
    llm_model: str | None = Form(None),
    llm_prompt: str | None = Form(None),
    extension_hint: str | None = Form(None),
    mime_type_hint: str | None = Form(None),
    charset_hint: str | None = Form(None),
    exiftool_path: str | None = Form(None),
    style_map: str | None = Form(None),
    azure_api_key: str | None = Form(None),
    docintel_endpoint: str | None = Form(None),
    docintel_api_version: str | None = Form(None),
    docintel_file_types: str | None = Form(None),
    cu_endpoint: str | None = Form(None),
    cu_analyzer_id: str | None = Form(None),
    cu_file_types: str | None = Form(None),
) -> JSONResponse:
    options = form_options(
        enable_builtins,
        enable_plugins,
        strict_html,
        keep_data_uris,
        use_llm,
        openai_api_key,
        openai_base_url,
        llm_model,
        llm_prompt,
        extension_hint,
        mime_type_hint,
        charset_hint,
        exiftool_path,
        style_map,
        azure_api_key,
        docintel_endpoint,
        docintel_api_version,
        docintel_file_types,
        cu_endpoint,
        cu_analyzer_id,
        cu_file_types,
    )
    safe_url = assert_public_http_url(url)
    started_at = time.perf_counter()

    try:
        converter = build_converter(**options)
        stream_info = stream_info_from_options(options, url=safe_url)
        result = converter.convert_uri(safe_url, stream_info=stream_info, **conversion_kwargs(options))
        markdown = result_text(result)
        output_path = save_markdown(urlparse(safe_url).hostname or "url", markdown)
        job = create_job(
            source_name=safe_url,
            source_type="url",
            status="completed",
            started_at=started_at,
            output_path=output_path,
            markdown=markdown,
            options=safe_options(options),
        )
        return JSONResponse({"job": asdict(job), "markdown": markdown})
    except HTTPException:
        raise
    except Exception as exc:
        job = create_job(
            source_name=safe_url,
            source_type="url",
            status="failed",
            started_at=started_at,
            error=str(exc),
            options=safe_options(options),
        )
        return JSONResponse({"job": asdict(job), "markdown": ""}, status_code=500)


@app.post("/api/convert/uri")
async def convert_uri(
    uri: str = Form(...),
    allow_file_uri: str | None = Form(None),
    enable_builtins: str | None = Form(None),
    enable_plugins: str | None = Form(None),
    strict_html: str | None = Form(None),
    keep_data_uris: str | None = Form(None),
    use_llm: str | None = Form(None),
    openai_api_key: str | None = Form(None),
    openai_base_url: str | None = Form(None),
    llm_model: str | None = Form(None),
    llm_prompt: str | None = Form(None),
    extension_hint: str | None = Form(None),
    mime_type_hint: str | None = Form(None),
    charset_hint: str | None = Form(None),
    exiftool_path: str | None = Form(None),
    style_map: str | None = Form(None),
    azure_api_key: str | None = Form(None),
    docintel_endpoint: str | None = Form(None),
    docintel_api_version: str | None = Form(None),
    docintel_file_types: str | None = Form(None),
    cu_endpoint: str | None = Form(None),
    cu_analyzer_id: str | None = Form(None),
    cu_file_types: str | None = Form(None),
) -> JSONResponse:
    options = form_options(
        enable_builtins,
        enable_plugins,
        strict_html,
        keep_data_uris,
        use_llm,
        openai_api_key,
        openai_base_url,
        llm_model,
        llm_prompt,
        extension_hint,
        mime_type_hint,
        charset_hint,
        exiftool_path,
        style_map,
        azure_api_key,
        docintel_endpoint,
        docintel_api_version,
        docintel_file_types,
        cu_endpoint,
        cu_analyzer_id,
        cu_file_types,
    )
    safe_uri = assert_allowed_uri(uri, allow_file_uri=parse_bool(allow_file_uri))
    started_at = time.perf_counter()

    try:
        converter = build_converter(**options)
        stream_info = stream_info_from_options(options, url=safe_uri)
        result = converter.convert_uri(safe_uri, stream_info=stream_info, **conversion_kwargs(options))
        markdown = result_text(result)
        output_path = save_markdown(urlparse(safe_uri).hostname or urlparse(safe_uri).scheme or "uri", markdown)
        job = create_job(
            source_name=safe_uri[:180],
            source_type="uri",
            status="completed",
            started_at=started_at,
            output_path=output_path,
            markdown=markdown,
            options=safe_options(options),
        )
        return JSONResponse({"job": asdict(job), "markdown": markdown})
    except HTTPException:
        raise
    except Exception as exc:
        job = create_job(
            source_name=safe_uri[:180],
            source_type="uri",
            status="failed",
            started_at=started_at,
            error=str(exc),
            options=safe_options(options),
        )
        return JSONResponse({"job": asdict(job), "markdown": ""}, status_code=500)


@app.post("/api/convert/text")
async def convert_text(
    content: str = Form(...),
    filename_hint: str | None = Form(None),
    enable_builtins: str | None = Form(None),
    enable_plugins: str | None = Form(None),
    strict_html: str | None = Form(None),
    keep_data_uris: str | None = Form(None),
    use_llm: str | None = Form(None),
    openai_api_key: str | None = Form(None),
    openai_base_url: str | None = Form(None),
    llm_model: str | None = Form(None),
    llm_prompt: str | None = Form(None),
    extension_hint: str | None = Form(None),
    mime_type_hint: str | None = Form(None),
    charset_hint: str | None = Form(None),
    exiftool_path: str | None = Form(None),
    style_map: str | None = Form(None),
    azure_api_key: str | None = Form(None),
    docintel_endpoint: str | None = Form(None),
    docintel_api_version: str | None = Form(None),
    docintel_file_types: str | None = Form(None),
    cu_endpoint: str | None = Form(None),
    cu_analyzer_id: str | None = Form(None),
    cu_file_types: str | None = Form(None),
) -> JSONResponse:
    display_name = (filename_hint or "texto-pegado.txt").strip() or "texto-pegado.txt"
    inferred_extension = Path(display_name).suffix or ".txt"
    inferred_mime_type = mimetypes.guess_type(display_name)[0] or "text/plain"
    options = form_options(
        enable_builtins,
        enable_plugins,
        strict_html,
        keep_data_uris,
        use_llm,
        openai_api_key,
        openai_base_url,
        llm_model,
        llm_prompt,
        extension_hint or inferred_extension,
        mime_type_hint or inferred_mime_type,
        charset_hint or "utf-8",
        exiftool_path,
        style_map,
        azure_api_key,
        docintel_endpoint,
        docintel_api_version,
        docintel_file_types,
        cu_endpoint,
        cu_analyzer_id,
        cu_file_types,
    )
    started_at = time.perf_counter()

    try:
        converter = build_converter(**options)
        charset = options.get("charset_hint") or "utf-8"
        stream = BytesIO(content.encode(charset, errors="replace"))
        stream_info = stream_info_from_options(options, filename=display_name)
        result = converter.convert_stream(stream, stream_info=stream_info, **conversion_kwargs(options))
        markdown = result_text(result)
        output_path = save_markdown(display_name, markdown)
        job = create_job(
            source_name=display_name,
            source_type="stream",
            status="completed",
            started_at=started_at,
            output_path=output_path,
            markdown=markdown,
            options=safe_options(options),
        )
        return JSONResponse({"job": asdict(job), "markdown": markdown})
    except HTTPException:
        raise
    except Exception as exc:
        job = create_job(
            source_name=display_name,
            source_type="stream",
            status="failed",
            started_at=started_at,
            error=str(exc),
            options=safe_options(options),
        )
        return JSONResponse({"job": asdict(job), "markdown": ""}, status_code=500)
