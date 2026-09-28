from decimal import Decimal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class Product(BaseModel):
    """Produto do catálogo. O CSV da API usa cabeçalhos em português."""

    model_config = ConfigDict(populate_by_name=True)

    reference: str = Field(validation_alias=AliasChoices("reference", "referencia"))
    description: str = Field(validation_alias=AliasChoices("description", "descricao"))
    family: str = Field(validation_alias=AliasChoices("family", "familia"))
    unit: str = Field(validation_alias=AliasChoices("unit", "unidade"))
    price_eur: Decimal = Field(validation_alias=AliasChoices("price_eur", "preco_eur"))
