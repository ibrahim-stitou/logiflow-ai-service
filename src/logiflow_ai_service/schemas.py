"""Base commune des schémas Pydantic : champs Python en snake_case, JSON en camelCase.

Le contrat d'API (voir docs/integration-ia.md côté backend) est défini en camelCase pour
correspondre aux DTO Java du module `ai` de logiflow-backend. `CamelModel` fait cette conversion
automatiquement, dans les deux sens.
"""

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
