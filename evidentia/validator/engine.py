"""Validation Engine — orchestrates all validation checks on step results."""

from __future__ import annotations

from typing import Any

from evidentia.core.logging import get_logger
from evidentia.core.models import StepResult, StepStatus

logger = get_logger(__name__)


class ValidationEngine:
    """Runs all registered validators against step results.

    Validators are pluggable — register new ones via add_validator().
    """

    def __init__(self) -> None:
        self._validators: list[BaseValidator] = []

    def add_validator(self, validator: BaseValidator) -> None:
        self._validators.append(validator)

    async def validate_results(self, results: list[StepResult]) -> bool:
        """Run all validators against the step results.

        Returns True if all validations pass, False otherwise.
        """
        all_passed = True

        for result in results:
            if result.status != StepStatus.SUCCESS:
                continue

            for validator in self._validators:
                try:
                    passed = await validator.validate(result)
                    if not passed:
                        logger.warning(
                            "validation_failed",
                            validator=validator.name,
                            step_id=result.step_id,
                        )
                        all_passed = False
                except Exception as exc:
                    logger.error(
                        "validator_error",
                        validator=validator.name,
                        step_id=result.step_id,
                        error=str(exc),
                    )
                    all_passed = False

        return all_passed


class BaseValidator:
    """Base class for all validators."""

    name: str = "base"

    async def validate(self, result: StepResult) -> bool:
        raise NotImplementedError
