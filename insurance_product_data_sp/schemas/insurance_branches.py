"""Insurance branches (ramos) schema for Spanish insurance market.

This module provides the Pydantic model for insurance branches as defined
by the Spanish insurance regulatory framework (DGSFP - Dirección General de
Seguros y Fondos de Pensiones).

The branches are categorized into:
- Life insurance (Vida): Code 0
- Non-life insurance (No Vida): Codes 1-19
"""

from typing import Literal

from pydantic import BaseModel, Field


class InsuranceBranch(BaseModel):
    """Insurance branch (ramo) model.

    Represents an insurance branch/line of business as defined by DGSFP.
    """

    code: str = Field(..., description="Branch code (e.g., '00', '01')")
    name_es: str = Field(..., description="Branch name in Spanish")
    name_en: str = Field(..., description="Branch name in English")
    category: Literal["life", "non_life"] = Field(..., description="Branch category")

    @property
    def is_life(self) -> bool:
        """Check if this is a life insurance branch."""
        return self.category == "life"

    @property
    def is_non_life(self) -> bool:
        """Check if this is a non-life insurance branch."""
        return self.category == "non_life"

    def get_name(self, language: str = "es") -> str:
        """Get branch name in specified language.

        Args:
            language: Language code ("es" for Spanish, "en" for English)

        Returns:
            Branch name in the specified language, falls back to Spanish.
        """
        if language == "en":
            return self.name_en
        return self.name_es
