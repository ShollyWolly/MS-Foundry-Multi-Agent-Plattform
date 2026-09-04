"""Per-department visual identity registry. Each report module declares which department it
"belongs to" (DEPARTMENT constant) — render_pdf() looks up that department's theme here to pick
the structural layout template and color/font tokens, so reports from the same real-world
department share a look and every other department looks genuinely different.
"""
from __future__ import annotations

DEPARTMENTS = {
    "sales": {
        "display_name": "Sales",
        "layout_template": "layouts/banner_kpi.html.jinja",
        "primary_color": "#a3291f",
        "accent_color": "#e8735f",
        "heading_font": "'Trebuchet MS', 'Helvetica Neue', sans-serif",
        "body_font": "'Helvetica Neue', Arial, sans-serif",
        "letter_spacing": "0.02em",
    },
    "marketing": {
        "display_name": "Marketing",
        "layout_template": "layouts/banner_kpi.html.jinja",
        "primary_color": "#6a2c91",
        "accent_color": "#e857a8",
        "heading_font": "'Verdana', 'Helvetica Neue', sans-serif",
        "body_font": "'Helvetica Neue', Arial, sans-serif",
        "letter_spacing": "0.08em",
    },
    "finance": {
        "display_name": "Finance",
        "layout_template": "layouts/formal_classic.html.jinja",
        "primary_color": "#152a4e",
        "accent_color": "#8a97ab",
        "heading_font": "Georgia, 'Times New Roman', serif",
        "body_font": "Georgia, 'Times New Roman', serif",
        "letter_spacing": "0",
    },
    "operations": {
        "display_name": "Operations",
        "layout_template": "layouts/dense_technical.html.jinja",
        "primary_color": "#8a5a00",
        "accent_color": "#f0a500",
        "heading_font": "'Courier New', monospace",
        "body_font": "'Helvetica Neue', Arial, sans-serif",
        "badge_shape": "0",
    },
    "hr": {
        "display_name": "Human Resources",
        "layout_template": "layouts/dense_technical.html.jinja",
        "primary_color": "#0f6e5c",
        "accent_color": "#5fcbb0",
        "heading_font": "'Trebuchet MS', 'Helvetica Neue', sans-serif",
        "body_font": "'Helvetica Neue', Arial, sans-serif",
        "badge_shape": "10px",
    },
    "customer_success": {
        "display_name": "Customer Success",
        "layout_template": "layouts/card_dashboard.html.jinja",
        "primary_color": "#1a7a4c",
        "accent_color": "#63c690",
        "heading_font": "'Helvetica Neue', Arial, sans-serif",
        "body_font": "'Helvetica Neue', Arial, sans-serif",
        "card_bg": "#eefaf3",
    },
    "product": {
        "display_name": "Product",
        "layout_template": "layouts/card_dashboard.html.jinja",
        "primary_color": "#38358f",
        "accent_color": "#8a86e0",
        "heading_font": "'Helvetica Neue', Arial, sans-serif",
        "body_font": "'Helvetica Neue', Arial, sans-serif",
        "card_bg": "#eeeefb",
    },
    "executive": {
        "display_name": "Executive & Strategy",
        "layout_template": "layouts/card_dashboard.html.jinja",
        "primary_color": "#1c1c1c",
        "accent_color": "#b8962e",
        "heading_font": "Georgia, 'Times New Roman', serif",
        "body_font": "'Helvetica Neue', Arial, sans-serif",
        "card_bg": "#f4f1e8",
    },
    "admin": {
        "display_name": "Corporate Administration",
        "layout_template": "layouts/ledger.html.jinja",
        "primary_color": "#3d3d3d",
        "accent_color": "#7a9b7a",
        "heading_font": "'Courier New', monospace",
        "body_font": "'Courier New', monospace",
        "letter_spacing": "0",
    },
}


def get_department(department_id: str) -> dict:
    return {"id": department_id, **DEPARTMENTS[department_id]}
