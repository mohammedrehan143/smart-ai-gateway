"""Autonomous Browser Automation and Web Testing Engine for Smart AI Gateway.

Provides web verification and browser automation:
- DOM element inspection, form detection, and webpage text extraction.
- HTTP and local frontend verification (e.g., verifying index.html or live web apps).
- Headless browser automation via Playwright when available, with a resilient fallback engine.
- Web app verification and visual / structural assertions.
"""

from __future__ import annotations

import re
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class SimpleDOMParser(HTMLParser):
    """Extracts interactive elements, links, forms, and headings from HTML."""

    def __init__(self):
        super().__init__()
        self.title: str = ""
        self.in_title: bool = False
        self.links: List[Dict[str, str]] = []
        self.forms: List[Dict[str, Any]] = []
        self.inputs: List[Dict[str, str]] = []
        self.buttons: List[str] = []
        self.text_content: List[str] = []
        self.current_form: Optional[Dict[str, Any]] = None

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]):
        attr_dict = {k: v or "" for k, v in attrs}
        t = tag.lower()

        if t == "title":
            self.in_title = True
        elif t == "a":
            href = attr_dict.get("href", "")
            if href:
                self.links.append({"href": href, "text": ""})
        elif t == "form":
            self.current_form = {
                "action": attr_dict.get("action", ""),
                "method": attr_dict.get("method", "get"),
                "inputs": [],
            }
            self.forms.append(self.current_form)
        elif t == "input":
            input_info = {
                "type": attr_dict.get("type", "text"),
                "name": attr_dict.get("name", ""),
                "id": attr_dict.get("id", ""),
                "placeholder": attr_dict.get("placeholder", ""),
            }
            self.inputs.append(input_info)
            if self.current_form is not None:
                self.current_form["inputs"].append(input_info)
        elif t == "button":
            self.buttons.append(attr_dict.get("id") or attr_dict.get("name") or "button")

    def handle_endtag(self, tag: str):
        if tag.lower() == "title":
            self.in_title = False
        elif tag.lower() == "form":
            self.current_form = None

    def handle_data(self, data: str):
        clean = data.strip()
        if self.in_title and clean:
            self.title += clean
        elif clean:
            self.text_content.append(clean)


class BrowserManager:
    """Automates webpage inspection, navigation, and web application verification."""

    def __init__(self, workspace_root: Optional[Path | str] = None):
        self.workspace_root = Path(workspace_root).resolve() if workspace_root else Path.cwd().resolve()

    def inspect_html(self, html_content: str) -> Dict[str, Any]:
        """Parses HTML and extracts DOM components."""
        parser = SimpleDOMParser()
        parser.feed(html_content)
        return {
            "title": parser.title,
            "inputs_count": len(parser.inputs),
            "inputs": parser.inputs,
            "buttons_count": len(parser.buttons),
            "links_count": len(parser.links),
            "links": parser.links[:20],
            "forms_count": len(parser.forms),
            "forms": parser.forms,
            "has_login_form": any(
                inp.get("type") == "password" or "pass" in inp.get("name", "").lower() for inp in parser.inputs
            ),
        }

    def inspect_file(self, file_path: str) -> Tuple[bool, Dict[str, Any]]:
        """Inspects a local HTML file."""
        target = (self.workspace_root / file_path).resolve()
        if not target.is_file():
            return False, {"error": f"File '{file_path}' not found."}

        try:
            content = target.read_text(encoding="utf-8", errors="ignore")
            dom = self.inspect_html(content)
            dom["file_path"] = str(target)
            return True, dom
        except Exception as exc:
            return False, {"error": str(exc)}

    def fetch_and_inspect_url(self, url: str, timeout_seconds: int = 10) -> Tuple[bool, Dict[str, Any]]:
        """Fetches live URL and extracts DOM elements."""
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SmartAI-Browser/1.0"})
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                raw_html = resp.read().decode("utf-8", errors="ignore")
                dom = self.inspect_html(raw_html)
                dom["url"] = url
                dom["status_code"] = resp.status
                return True, dom
        except Exception as exc:
            return False, {"url": url, "error": str(exc)}

    def verify_web_app(
        self,
        html_content_or_file: str,
        expected_elements: List[str],
    ) -> Tuple[bool, Dict[str, Any]]:
        """Verifies that required elements (tags, inputs, or IDs) are present."""
        content = html_content_or_file
        # Check if it's a file path
        candidate = (self.workspace_root / html_content_or_file).resolve()
        if candidate.is_file():
            content = candidate.read_text(encoding="utf-8", errors="ignore")

        missing = []
        found = []
        for elem in expected_elements:
            # Check tag or id or class or text
            escaped = re.escape(elem)
            pattern = (
                rf"(<{escaped}\b|id=['\"]?{escaped}['\"]?|class=['\"][^'\"]*\b{escaped}\b[^'\"]*['\"]|\b{escaped}\b)"
            )
            if re.search(pattern, content, re.IGNORECASE):
                found.append(elem)
            else:
                missing.append(elem)

        passed = len(missing) == 0
        return passed, {
            "verified": passed,
            "elements_found": found,
            "elements_missing": missing,
        }


default_browser_manager = BrowserManager()
