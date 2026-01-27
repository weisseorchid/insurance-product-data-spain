"""PDF processing utilities using MarkItDown."""

from pathlib import Path
from typing import NamedTuple

from markitdown import MarkItDown

from insurance_product_data_spain.core.logging import logger


class PDFConversionResult(NamedTuple):
    """Result of a PDF to markdown conversion."""

    source_path: Path
    markdown_content: str
    success: bool
    error: str | None = None


def convert_pdf_to_markdown(file_path: Path | str) -> PDFConversionResult:
    """
    Convert a PDF file to markdown using MarkItDown.

    Args:
        file_path: Path to the PDF file

    Returns:
        PDFConversionResult with the markdown content or error
    """
    path = Path(file_path)

    if not path.exists():
        logger.error(f"PDF file not found: {path}")
        return PDFConversionResult(
            source_path=path,
            markdown_content="",
            success=False,
            error=f"File not found: {path}",
        )

    if not path.suffix.lower() == ".pdf":
        logger.warning(f"File is not a PDF: {path}")
        return PDFConversionResult(
            source_path=path,
            markdown_content="",
            success=False,
            error=f"Not a PDF file: {path}",
        )

    try:
        converter = MarkItDown()
        result = converter.convert(str(path))
        markdown_content = result.text_content if result.text_content else ""

        logger.info(f"Successfully converted PDF to markdown: {path.name}")
        return PDFConversionResult(
            source_path=path,
            markdown_content=markdown_content,
            success=True,
        )

    except Exception as e:
        logger.error(f"Failed to convert PDF {path}: {e}")
        return PDFConversionResult(
            source_path=path,
            markdown_content="",
            success=False,
            error=str(e),
        )


def convert_all_pdfs_in_directory(directory: Path | str) -> list[PDFConversionResult]:
    """
    Convert all PDF files in a directory to markdown.

    Args:
        directory: Path to the directory containing PDF files

    Returns:
        List of PDFConversionResult for each PDF found
    """
    dir_path = Path(directory)

    if not dir_path.exists():
        logger.error(f"Directory not found: {dir_path}")
        return []

    if not dir_path.is_dir():
        logger.error(f"Path is not a directory: {dir_path}")
        return []

    pdf_files = list(dir_path.glob("*.pdf"))
    logger.info(f"Found {len(pdf_files)} PDF files in {dir_path}")

    results = []
    for pdf_file in pdf_files:
        result = convert_pdf_to_markdown(pdf_file)
        results.append(result)

    return results
