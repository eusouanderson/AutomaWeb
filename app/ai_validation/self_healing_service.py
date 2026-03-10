from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.ai_validation.metrics import AIMetricsRegistry
from app.ai_validation.test_fixer import TestFixer
from app.ai_validation.test_validator import TestValidator, ValidationIssue
from app.core.config import settings


@dataclass
class HealedTestResult:
    original_content: str
    final_content: str
    issues_found: list[ValidationIssue]
    fixes_applied: list[str]

    @property
    def was_fixed(self) -> bool:
        return bool(self.fixes_applied) and self.final_content != self.original_content


class AITestSelfHealingService:
    def __init__(
        self,
        validator: TestValidator | None = None,
        fixer: TestFixer | None = None,
        metrics: AIMetricsRegistry | None = None,
    ) -> None:
        self._validator = validator or TestValidator()
        self._fixer = fixer or TestFixer()
        self._metrics = metrics or AIMetricsRegistry.instance()

    async def heal_test(
        self,
        content: str,
        page_url: str | None = None,
        prompt: str | None = None,
        context: str | None = None,
        groq_client=None,
        ai_debug: bool = False,
    ) -> HealedTestResult:
        self._metrics.inc_generated()

        first_report = await self._validator.validate(content=content, page_url=page_url)
        fixed_content = content
        applied_fixes: list[str] = []

        if first_report.issues:
            fix_result = await self._fixer.apply_fixes(
                content=content,
                issues=first_report.issues,
                groq_client=groq_client,
                prompt=prompt,
                context=context,
            )
            fixed_content = fix_result.content
            applied_fixes = fix_result.applied_fixes

        second_report = await self._validator.validate(content=fixed_content, page_url=page_url)

        if not second_report.has_errors and applied_fixes:
            self._metrics.inc_fixed()
        elif second_report.has_errors:
            self._metrics.inc_failed()

        result = HealedTestResult(
            original_content=content,
            final_content=fixed_content,
            issues_found=first_report.issues,
            fixes_applied=applied_fixes,
        )

        if settings.AI_DEBUG or ai_debug:
            self._write_debug_log(result, second_report.issues, prompt=prompt, context=context)

        return result

    def metrics(self) -> dict[str, float | int]:
        return self._metrics.as_dict()

    def _write_debug_log(
        self,
        result: HealedTestResult,
        remaining_issues: list[ValidationIssue],
        prompt: str | None = None,
        context: str | None = None,
    ) -> None:
        log_path = Path(settings.AI_DEBUG_LOG_PATH)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "prompt": prompt,
            "context": context,
            "original_test": result.original_content,
            "issues_detected": [issue.__dict__ for issue in result.issues_found],
            "fixes_applied": result.fixes_applied,
            "remaining_issues": [issue.__dict__ for issue in remaining_issues],
            "final_test": result.final_content,
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
