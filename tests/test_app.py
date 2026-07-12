from __future__ import annotations

import io
import unittest
import zipfile

from fastapi.testclient import TestClient
from markitdown.converters import ContentUnderstandingFileType, DocumentIntelligenceFileType

from app.main import app, build_converter, jobs


class DashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        jobs.clear()
        self.client = TestClient(app)

    def test_health_reports_markitdown(self) -> None:
        payload = self.client.get("/api/health").json()
        self.assertTrue(payload["markitdown_available"])
        self.assertIsNotNone(payload["markitdown_version"])
        self.assertTrue(payload["ffmpeg_available"])

    def test_shutdown_is_unavailable_without_launcher_token(self) -> None:
        response = self.client.post("/api/shutdown")
        self.assertEqual(response.status_code, 404)

    def test_format_catalog_covers_all_azure_types(self) -> None:
        groups = self.client.get("/api/formats").json()["groups"]
        catalog = {extension.lstrip(".") for group in groups for extension in group["extensions"]}
        self.assertTrue({item.value for item in DocumentIntelligenceFileType}.issubset(catalog))
        self.assertTrue({item.value for item in ContentUnderstandingFileType}.issubset(catalog))

    def test_every_builtin_converter_is_registered(self) -> None:
        converter = build_converter(
            enable_builtins=True,
            enable_plugins=False,
            strict_html=False,
            use_llm=False,
            openai_api_key=None,
            openai_base_url=None,
            llm_model=None,
            llm_prompt=None,
            exiftool_path=None,
            style_map=None,
            azure_api_key=None,
            docintel_endpoint=None,
            docintel_api_version=None,
            docintel_file_types=None,
            cu_endpoint=None,
            cu_analyzer_id=None,
            cu_file_types=None,
        )
        registered = {type(item.converter).__name__ for item in converter._converters}
        expected = {
            "AudioConverter",
            "BingSerpConverter",
            "CsvConverter",
            "DocxConverter",
            "EpubConverter",
            "HtmlConverter",
            "ImageConverter",
            "IpynbConverter",
            "OutlookMsgConverter",
            "PdfConverter",
            "PlainTextConverter",
            "PptxConverter",
            "RssConverter",
            "WikipediaConverter",
            "XlsConverter",
            "XlsxConverter",
            "YouTubeConverter",
            "ZipConverter",
        }
        self.assertEqual(registered, expected)

    def test_text_conversion_and_download(self) -> None:
        response = self.client.post(
            "/api/convert/text",
            data={"content": "# Titulo\n\nContenido", "filename_hint": "apuntes.md"},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("Titulo", payload["markdown"])
        download = self.client.get(f"/api/jobs/{payload['job']['id']}/download")
        self.assertEqual(download.status_code, 200)
        self.assertIn("Titulo", download.text)

    def test_text_mode_uses_the_filename_to_choose_converter(self) -> None:
        html = self.client.post(
            "/api/convert/text",
            data={"content": "<h1>Titulo HTML</h1><p>Contenido</p>", "filename_hint": "pagina.html"},
        ).json()
        self.assertIn("# Titulo HTML", html["markdown"])
        self.assertNotIn("<h1>", html["markdown"])

        csv = self.client.post(
            "/api/convert/text",
            data={"content": "nombre,nota\nAna,9", "filename_hint": "notas.csv"},
        ).json()
        self.assertIn("| nombre", csv["markdown"])

    def test_file_batch_download_contains_every_result(self) -> None:
        uploaded_files = [
            ("files", (f"documento-{index:02}.txt", f"Contenido {index}".encode(), "text/plain"))
            for index in range(1, 21)
        ]
        response = self.client.post(
            "/api/convert/files",
            files=uploaded_files,
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["completed_count"], 20)
        self.assertEqual(len(payload["jobs"]), 20)

        archive = self.client.get(payload["batch_download_url"])
        self.assertEqual(archive.status_code, 200)
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zip_file:
            self.assertEqual(len(zip_file.namelist()), 20)
            self.assertEqual(
                set(zip_file.namelist()),
                {f"documento-{index:02}.md" for index in range(1, 21)},
            )

    def test_secrets_are_not_returned_in_job_options(self) -> None:
        response = self.client.post(
            "/api/convert/text",
            data={
                "content": "contenido",
                "openai_api_key": "clave-openai",
                "azure_api_key": "clave-azure",
            },
        )
        options = response.json()["job"]["options"]
        self.assertNotIn("clave-openai", str(options))
        self.assertNotIn("clave-azure", str(options))
        self.assertTrue(options["has_openai_api_key"])
        self.assertTrue(options["has_azure_api_key"])


if __name__ == "__main__":
    unittest.main()
