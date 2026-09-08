"""Tests for parsing.docling_parser — DoclingParser.

R14: `_ensure_converter` only configured `format_options` for
`InputFormat.PDF`. Both `PDF` and `IMAGE` use the Pdf pipeline
(`do_ocr`/`do_table_structure` live on `PdfPipelineOptions`), so images
routed through this parser (`.png`/`.jpg`/`.jpeg`/`.tiff`, see
`router.py::DOCLING_EXTENSIONS`) silently used Docling's *default* image
pipeline options — ignoring the caller's `ocr=False`/`table_structure=False`.
DOCX/PPTX/HTML/XLSX use `SimplePipeline` with a base `PipelineOptions` that
has no such fields, so Pdf options must not be attached there.
"""

from __future__ import annotations

from indexed.parsing.docling_parser import DoclingParser


class TestDoclingParserFormatOptions:
    def test_image_format_gets_caller_ocr_option(self):
        """An image path with ocr=False must have that option applied —
        not silently fall back to Docling's default (do_ocr=True) image
        pipeline options.
        """
        from docling.datamodel.base_models import InputFormat

        parser = DoclingParser(ocr=False, table_structure=False)
        parser._ensure_converter()
        assert parser._converter is not None

        image_options = parser._converter.format_to_options[InputFormat.IMAGE]
        assert image_options.pipeline_options.do_ocr is False
        assert image_options.pipeline_options.do_table_structure is False

    def test_pdf_format_still_gets_caller_ocr_option(self):
        """Regression guard: the PDF wiring that already worked must keep
        working after adding the IMAGE entry.
        """
        from docling.datamodel.base_models import InputFormat

        parser = DoclingParser(ocr=False, table_structure=False)
        parser._ensure_converter()
        assert parser._converter is not None

        pdf_options = parser._converter.format_to_options[InputFormat.PDF]
        assert pdf_options.pipeline_options.do_ocr is False
        assert pdf_options.pipeline_options.do_table_structure is False

    def test_simple_pipeline_formats_not_given_pdf_options(self):
        """DOCX (and other SimplePipeline formats) must not be handed Pdf
        pipeline options — `PipelineOptions` (the SimplePipeline base) has
        no `do_ocr`/`do_table_structure` fields, so blanket-applying Pdf
        options there would be a type mismatch / crash risk.
        """
        from docling.datamodel.base_models import InputFormat

        parser = DoclingParser(ocr=False, table_structure=False)
        parser._ensure_converter()
        assert parser._converter is not None

        docx_options = parser._converter.format_to_options[InputFormat.DOCX]
        assert not hasattr(docx_options.pipeline_options, "do_ocr")
        assert not hasattr(docx_options.pipeline_options, "do_table_structure")

    def test_image_ocr_true_default_applied(self):
        """Symmetric check: ocr=True (the default) is also honored for
        images, not just the ocr=False case.
        """
        from docling.datamodel.base_models import InputFormat

        parser = DoclingParser(ocr=True, table_structure=True)
        parser._ensure_converter()
        assert parser._converter is not None

        image_options = parser._converter.format_to_options[InputFormat.IMAGE]
        assert image_options.pipeline_options.do_ocr is True
        assert image_options.pipeline_options.do_table_structure is True
