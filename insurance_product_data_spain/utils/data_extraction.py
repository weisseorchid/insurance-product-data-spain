import json
import re
from typing import Any

from bs4 import BeautifulSoup, Tag


def extract_label_value(soup: BeautifulSoup | Tag, label_text: str) -> str | None:
    """Extract value from a label-value pair in the HTML."""
    # Find label with the text (can be exact match or contains)
    labels = soup.find_all('label', class_='label-literal')
    for label in labels:
        if label_text.lower() in label.get_text().lower():
            # Look for the value label - could be next sibling or in same parent
            value_label = label.find_next_sibling('label', class_='label-value')
            if not value_label:
                # Try finding in parent's children
                parent = label.parent
                if parent:
                    value_label = parent.find('label', class_='label-value')
            if value_label:
                text = value_label.get_text(strip=True)
                return text if text else None
    return None


def extract_js_data(soup: BeautifulSoup, function_name: str) -> list[dict[str, Any]] | None:
    """Extract JSON data from JavaScript variables in script tags."""
    # Look for script tags containing the function call
    scripts = soup.find_all('script', type='text/javascript')
    for script in scripts:
        # Check if script is a Tag before accessing .string
        if isinstance(script, Tag):
            script_text = script.string
            if script_text and function_name in script_text:
                # Find the var data = [...] pattern
                match = re.search(r'var\s+data\s*=\s*(\[.*?\]);', script_text, re.DOTALL)
                if match:
                    try:
                        data_str = match.group(1)
                        parsed_data = json.loads(data_str)
                        # Type check and cast to expected return type
                        if isinstance(parsed_data, list):
                            return parsed_data
                    except (json.JSONDecodeError, TypeError):
                        continue
    return None
