from __future__ import annotations

import re
from typing import Any


class PlaywrightCodeGenerator:
    """Transforms captured visual-builder steps into Robot Framework code."""

    def _normalize_selector(self, selector: str) -> str:
        if selector.startswith("id:"):
            return f"css=#{selector[3:]}"
        if selector.startswith("css:"):
            return f"css={selector[4:]}"
        if selector.startswith("xpath:"):
            return f"xpath={selector[6:]}"
        if selector.startswith("css=") or selector.startswith("xpath="):
            return selector
        if selector.startswith("#") or selector.startswith("[") or selector.startswith("."):
            return f"css={selector}"
        if selector.startswith("/") or selector.startswith("("):
            return f"xpath={selector}"
        if re.match(r"^[a-zA-Z][\\w-]*(?:[\\[\\.:#].*)?$", selector):
            return f"css={selector}"
        return selector

    def _make_selector_unique(self, selector: str) -> str:
        if selector.endswith(" >> nth=0"):
            return selector
        if selector.startswith("css="):
            return f"{selector} >> nth=0"
        return selector

    def generate(
        self,
        steps: list[dict[str, Any]],
        start_url: str | None = None,
        prompt: str | None = None,
    ) -> str:
        lines: list[str] = [
            "*** Settings ***",
            "Library    Browser",
            "",
            "*** Variables ***",
            "${HEADLESS}    True",
            "",
            "*** Test Cases ***",
            "Visual Builder - Fluxo Capturado",
            "    New Browser    chromium    headless=${HEADLESS}",
            "    New Context",
            "    Set Browser Timeout    30s",
        ]

        prompt_text = (prompt or "").strip()
        if prompt_text:
            lines.append(f"    # Objetivo: {prompt_text}")

        if start_url:
            lines.append(f"    New Page    {start_url}")
        else:
            lines.append("    New Page    about:blank")

        if not steps:
            lines.append("    # Nenhuma acao visual capturada.")
            lines.append("    No Operation")
            lines.append("    Close Browser")
            return "\n".join(lines) + "\n"

        for step in steps:
            event_type = str(step.get("action") or step.get("type") or "").lower()
            selector = str(step.get("selector", "")).strip()
            description = str(step.get("description", "")).strip()

            if description:
                lines.append(f"    # {description}")

            if not selector:
                lines.append(
                    f"    # Step ignorado (sem seletor): {str(step)}"
                )
                continue

            normalized_selector = self._make_selector_unique(
                self._normalize_selector(selector)
            )

            if event_type == "click":
                lines.append(f"    Click    {normalized_selector}")
            elif event_type == "input":
                value = str(step.get("value", ""))
                lines.append(f"    Fill Text    {normalized_selector}    {value}")
            else:
                lines.append(
                    f"    # Step nao suportado: {str(step)}"
                )

        lines.append("    Close Browser")

        return "\n".join(lines) + "\n"
