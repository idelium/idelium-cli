"""Selector quality diagnostics for Selenium and Appium steps."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SelectorDiagnostic:
    """A stable selector-quality diagnostic that does not alter execution."""

    rule_id: str
    strategy: str
    selector: str
    guidance: str

    def format(self) -> str:
        return (
            f"{self.rule_id}: {self.strategy} selector may be brittle. "
            f"{self.guidance}"
        )


_DYNAMIC_VALUE_RE = re.compile(
    r"(?:[0-9a-f]{8,}|[A-Za-z]+[-_][0-9]{3,}|[0-9]{4,}|[a-f0-9]{8}-[a-f0-9-]{13,})",
    re.IGNORECASE,
)
_CSS_ID_RE = re.compile(r"#([A-Za-z_][A-Za-z0-9_-]*)")
_CSS_ATTR_RE = re.compile(r"\[([A-Za-z_:][-A-Za-z0-9_:.]*)[*^$|~]?=['\"]?([^'\"]+)['\"]?\]")
_XPATH_ATTR_RE = re.compile(r"@([A-Za-z_:][-A-Za-z0-9_:.]*)\s*=\s*['\"]([^'\"]+)['\"]")
_XPATH_POSITION_RE = re.compile(r"\[(?:\d+|last\(\))\]")


def analyze_selector(strategy: str, selector: str) -> list[SelectorDiagnostic]:
    """Return deterministic diagnostics for a selector without modifying it."""

    normalized_strategy = _normalize_strategy(strategy)
    if not selector or normalized_strategy not in {"css", "xpath"}:
        return []
    if normalized_strategy == "css":
        return _analyze_css(selector)
    return _analyze_xpath(selector)


def collect_step_selector_diagnostics(
    object_step: dict[str, Any],
) -> list[SelectorDiagnostic]:
    """Collect selector diagnostics from legacy and current step fields."""

    diagnostics: list[SelectorDiagnostic] = []
    if object_step.get("xpath"):
        diagnostics.append(
            SelectorDiagnostic(
                "IDELIUM_SELECTOR_LEGACY_XPATH_FIELD",
                "xpath",
                object_step["xpath"],
                "Prefer explicit findBy/target fields or DSL locator metadata for new steps.",
            )
        )
        diagnostics.extend(analyze_selector("xpath", object_step["xpath"]))
    if object_step.get("findBy") and object_step.get("target"):
        diagnostics.extend(analyze_selector(object_step["findBy"], object_step["target"]))
    if object_step.get("shadowFindBy") and object_step.get("shadowTarget"):
        diagnostics.extend(
            analyze_selector(object_step["shadowFindBy"], object_step["shadowTarget"])
        )
    for prefix in ("source", "target"):
        find_by = object_step.get(prefix + "FindBy")
        target = object_step.get(prefix + "Target")
        if find_by and target:
            diagnostics.extend(analyze_selector(find_by, target))
    for action in object_step.get("actions") or []:
        if isinstance(action, dict):
            diagnostics.extend(collect_step_selector_diagnostics(action))
    return _deduplicate(diagnostics)


def _analyze_css(selector: str) -> list[SelectorDiagnostic]:
    diagnostics = []
    if ":nth-child" in selector or ":nth-of-type" in selector:
        diagnostics.append(
            SelectorDiagnostic(
                "IDELIUM_SELECTOR_CSS_POSITIONAL",
                "css",
                selector,
                "Prefer a stable data-testid, role, name, or business attribute over positional CSS.",
            )
        )
    for css_id in _CSS_ID_RE.findall(selector):
        if _DYNAMIC_VALUE_RE.search(css_id):
            diagnostics.append(
                SelectorDiagnostic(
                    "IDELIUM_SELECTOR_CSS_DYNAMIC_ID",
                    "css",
                    selector,
                    "The id value looks generated; prefer a stable test attribute or semantic locator.",
                )
            )
            break
    for attribute, value in _CSS_ATTR_RE.findall(selector):
        if attribute.lower() in {"id", "class"} and _DYNAMIC_VALUE_RE.search(value):
            diagnostics.append(
                SelectorDiagnostic(
                    "IDELIUM_SELECTOR_CSS_DYNAMIC_ATTRIBUTE",
                    "css",
                    selector,
                    "The attribute value looks generated; prefer stable automation metadata.",
                )
            )
            break
    return diagnostics


def _analyze_xpath(selector: str) -> list[SelectorDiagnostic]:
    diagnostics = []
    stripped = selector.strip()
    if stripped.startswith("/") and not stripped.startswith("//"):
        diagnostics.append(
            SelectorDiagnostic(
                "IDELIUM_SELECTOR_XPATH_ABSOLUTE",
                "xpath",
                selector,
                "Prefer relative XPath rooted in stable attributes over absolute DOM paths.",
            )
        )
    if _XPATH_POSITION_RE.search(selector):
        diagnostics.append(
            SelectorDiagnostic(
                "IDELIUM_SELECTOR_XPATH_POSITIONAL",
                "xpath",
                selector,
                "Prefer stable attributes over numeric XPath positions.",
            )
        )
    for attribute, value in _XPATH_ATTR_RE.findall(selector):
        if attribute.lower() in {"id", "class"} and _DYNAMIC_VALUE_RE.search(value):
            diagnostics.append(
                SelectorDiagnostic(
                    "IDELIUM_SELECTOR_XPATH_DYNAMIC_ATTRIBUTE",
                    "xpath",
                    selector,
                    "The attribute value looks generated; prefer stable automation metadata.",
                )
            )
            break
    return diagnostics


def _normalize_strategy(strategy: str) -> str:
    value = str(strategy or "").strip().lower().replace("_", " ")
    if value in {"css", "css selector", "css_selector"}:
        return "css"
    if value in {"xpath", "x path"}:
        return "xpath"
    return value


def _deduplicate(
    diagnostics: list[SelectorDiagnostic],
) -> list[SelectorDiagnostic]:
    seen = set()
    unique = []
    for diagnostic in diagnostics:
        key = (diagnostic.rule_id, diagnostic.strategy, diagnostic.selector)
        if key not in seen:
            seen.add(key)
            unique.append(diagnostic)
    return unique
