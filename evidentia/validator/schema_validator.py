"""Schema Validator — ensures tool outputs conform to declared JSON schemas."""

from __future__ import annotations

from typing import Any

from evidentia.core.logging import get_logger
from evidentia.core.models import StepResult
from evidentia.validator.engine import BaseValidator

logger = get_logger(__name__)


class SchemaValidator(BaseValidator):
    """Validates that tool outputs match their declared output schemas."""

    name = "schema"

    def __init__(self, tool_schemas: dict[str, dict[str, Any]]) -> None:
        self._schemas = tool_schemas  # tool_name -> output JSON schema

    async def validate(self, result: StepResult) -> bool:
        schema = self._schemas.get(result.tool_name)
        if schema is None:
            logger.warning("no_schema_registered", tool=result.tool_name)
            return True  # No schema = skip validation

        if result.output is None:
            logger.warning("null_output", step_id=result.step_id)
            return False

        # Basic type/key checks (full JSON Schema validation would use jsonschema lib)
        if isinstance(result.output, dict):
            required = schema.get("required", [])
            for field in required:
                if field not in result.output:
                    logger.warning(
                        "missing_required_field",
                        step_id=result.step_id,
                        field=field,
                    )
                    return False

        return True
