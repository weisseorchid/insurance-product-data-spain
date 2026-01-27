"""Gemini AI client for analyzing insurance policy documents.

This module provides a client for using Google's Gemini AI to extract
structured information from insurance policy markdown documents.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from insurance_product_data_spain.schemas import ProductAnalysis

load_dotenv()

GEMINI_MODEL = "gemini-3-flash-preview"

# System prompt for insurance document analysis
SYSTEM_PROMPT = """You are an expert insurance policy analyst specializing in Spanish insurance products.
Your task is to extract structured information from insurance policy documents (PIDs, general conditions,
brochures, usage guides, etc.) and populate a comprehensive analysis schema.

Guidelines:
1. Extract information accurately from the provided documents
2. Use Spanish for all description fields (description_es) as the source material is in Spanish
3. Optionally provide English translations where the schema allows
4. For coverages, distinguish between:
   - "basic": Mandatory/included coverages (Coberturas Básicas)
   - "optional": Add-on coverages (Coberturas Opcionales/Adicionales)
   - "included_service": Non-insurance services (Servicios incluidos)
5. For document types, classify as:
   - "pid": Product Information Documents (IPID, Documento de información)
   - "general_conditions": General conditions (Condiciones Generales)
   - "limiting_conditions": Limiting conditions (Condiciones Limitativas)
   - "brochure": Brochures/marketing materials (Folleto)
   - "usage_guide": Usage guides (Guía de Uso)
   - "other": Other document types
6. Extract waiting periods (carencias) in days when mentioned
7. Extract all monetary limits in their original format (e.g., "100.000€")
8. List all exclusions found across all documents
9. Be thorough but accurate - only include information that is explicitly stated in the documents
10. Set extraction_confidence based on how clearly the information was stated (1.0 = very clear, 0.5 = inferred, 0.0 = uncertain)
"""


class GeminiClient:
    """Client for analyzing insurance documents using Google Gemini AI."""

    def __init__(self, model: str | None = None):
        """Initialize the Gemini client.

        Args:
            model: Optional model name override. Defaults to GEMINI_MODEL.
        """
        self.client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        self.model = model or GEMINI_MODEL

    def analyze_product_documents(
        self,
        markdown_paths: list[str],
        product_context: dict | None = None,
    ) -> ProductAnalysis:
        """Analyze multiple documents for a single insurance product.

        This method combines content from multiple source documents (PIDs,
        general conditions, brochures, etc.) to create a comprehensive
        product analysis.

        Args:
            markdown_paths: List of paths to markdown files to analyze.
            product_context: Optional context about the product (name, branch, etc.)
                            to help guide the analysis.

        Returns:
            ProductAnalysis object with aggregated information from all documents.
        """
        # Collect all document contents
        documents_content = []
        for path in markdown_paths:
            with open(path, encoding="utf-8") as file:
                content = file.read()
                filename = Path(path).name
                documents_content.append(f"### Document: {filename}\n\n{content}")

        combined_content = "\n\n---\n\n".join(documents_content)

        # Build context string if provided
        context_str = ""
        if product_context:
            context_str = f"""
Product context:
- Product name: {product_context.get('product_name', 'Unknown')}
- Product branch: {product_context.get('product_branch', 'Unknown')}
- Company: {product_context.get('company', 'Unknown')}
"""

        user_prompt = f"""Analyze the following insurance policy documents and extract comprehensive information about the insurance product.
Multiple documents are provided - combine information from all of them to create a complete analysis.
{context_str}
The following documents are provided:

{combined_content}

---

Extract and combine information from ALL documents into a single comprehensive analysis.
For each source document, classify its type and include it in the source_documents list.
Aggregate coverages, exclusions, and limits from all documents, avoiding duplicates."""

        response = self.client.models.generate_content(
            model=self.model,
            contents=[user_prompt],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=ProductAnalysis,
            ),
        )

        # Parse the JSON response into ProductAnalysis
        if response.text is None:
            raise ValueError("Gemini API returned None response text")
        return ProductAnalysis.model_validate_json(response.text)

    def analyze_product_documents_raw(
        self,
        markdown_paths: list[str],
        product_context: dict | None = None,
    ) -> dict:
        """Analyze multiple documents and return raw JSON response.

        Same as analyze_product_documents but returns the raw dictionary
        instead of a validated Pydantic model. Useful for debugging or
        when you need to inspect the raw AI output.

        Args:
            markdown_paths: List of paths to markdown files to analyze.
            product_context: Optional context about the product.

        Returns:
            Dictionary with the raw extracted data.
        """
        analysis = self.analyze_product_documents(markdown_paths, product_context)
        return analysis.model_dump()
