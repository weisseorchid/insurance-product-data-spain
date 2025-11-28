import re


def text_to_snake_case(text: str) -> str:
    """
    Convert a string to snake_case.

    Args:
        text: The string to convert

    Returns:
        The string in snake_case format
    """

    text = text.lower()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s-]+', '_', text)
    text = re.sub(r'_+', '_', text)
    text = text.strip('_')

    return text
