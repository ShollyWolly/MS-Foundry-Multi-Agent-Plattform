"""Jinja2 + WeasyPrint rendering shared by every report generator."""
from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from .departments import get_department

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "jinja"]),
)


def render_pdf(department: str, context: dict, output_path: Path) -> None:
    """Renders `context` through the structural layout template + visual theme belonging to
    `department` (see lib/departments.py) — this is what gives each report its own department's
    look, rather than every report sharing one generic template."""
    dept = get_department(department)
    template = _env.get_template(dept["layout_template"])
    html_str = template.render(department=dept, **context)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html_str, base_url=str(TEMPLATES_DIR)).write_pdf(str(output_path))
