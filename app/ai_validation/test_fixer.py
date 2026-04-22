from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from app.ai_validation.test_validator import ValidationIssue


@dataclass
class FixResult:
    content: str
    applied_fixes: list[str]


class TestFixer:
    async def apply_fixes(
        self,
        content: str,
        issues: list[ValidationIssue],
        groq_client=None,
        prompt: str | None = None,
        context: str | None = None,
    ) -> FixResult:
        lines = content.splitlines()
        applied_fixes: list[str] = []

        # Replace locators first to preserve line mapping for wait insertion.
        for issue in issues:
            if issue.line_number <= 0 or issue.line_number > len(lines):
                continue
            if not issue.suggested_locator:
                continue
            if issue.issue_type not in {"generic_xpath", "strict_mode_violation"}:
                continue

            current = lines[issue.line_number - 1]
            updated = self._replace_locator(current, issue.suggested_locator)
            if updated != current:
                lines[issue.line_number - 1] = updated
                applied_fixes.append(
                    f"L{issue.line_number}: locator refinado ({issue.issue_type})"
                )

        # Insert waits after replacements.
        inserted = 0
        for issue in sorted(
            (i for i in issues if i.issue_type == "missing_wait"),
            key=lambda item: item.line_number,
        ):
            target_index = issue.line_number - 1 + inserted
            if target_index < 0 or target_index >= len(lines):
                continue
            wait_line = self._build_wait_line(lines[target_index])
            if wait_line and not self._line_is_wait(
                lines[target_index - 1] if target_index > 0 else ""
            ):
                lines.insert(target_index, wait_line)
                inserted += 1
                applied_fixes.append(f"L{issue.line_number}: wait automático inserido")

        # Last resort: ask LLM to regenerate only failing step.
        for issue in issues:
            if issue.issue_type != "element_not_found":
                continue
            if groq_client is None or not prompt:
                continue
            line_idx = issue.line_number - 1
            if line_idx < 0 or line_idx >= len(lines):
                continue

            regenerated = await asyncio.to_thread(
                groq_client.regenerate_robot_step,
                prompt,
                lines[line_idx],
                issue.message,
                context,
            )
            if regenerated:
                lines[line_idx] = regenerated
                applied_fixes.append(f"L{issue.line_number}: step regenerado por IA")

        return FixResult(
            content="\n".join(lines).rstrip() + "\n", applied_fixes=applied_fixes
        )

    def _replace_locator(self, line: str, new_locator: str) -> str:
        stripped = line.strip()
        parts = re.split(r"\s{2,}", stripped)
        if len(parts) < 2:
            return line
        parts[1] = new_locator
        indent = line[: len(line) - len(line.lstrip())]
        return f"{indent}{'    '.join(parts)}"

    def _build_wait_line(self, action_line: str) -> str | None:
        stripped = action_line.strip()
        parts = re.split(r"\s{2,}", stripped)
        if len(parts) < 2:
            return None
        locator = parts[1]
        indent = action_line[: len(action_line) - len(action_line.lstrip())]
        return f"{indent}Wait For Elements State    {locator}    visible    timeout=10s"

    def _line_is_wait(self, line: str) -> bool:
        stripped = line.strip()
        return stripped.startswith("Wait For Elements State") or stripped.startswith(
            "Wait For Selector"
        )
