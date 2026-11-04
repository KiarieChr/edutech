"""
WeasyPrint Document PDF Rendering Engine (Phase 2 & Phase 2D).
Provides high-fidelity paged PDF generation with:
- Professional institutional typography and harmonious hierarchy
- First-page prominent masthead vs compact continuation running headers
- Dynamic CSS pagination counters (counter(page) of counter(pages))
- Pillow-based semi-transparent watermark rasterization with typography refinement
- Print-grade table styles, callout blocks, and signature endorsements
"""
import io
import os
import re
import base64
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import weasyprint
from django.conf import settings
from django.utils.html import escape
from core.models import InstitutionProfile


def get_default_context(institution=None):
    """
    Constructs default branding context from InstitutionProfile.
    """
    if institution is None:
        try:
            institution = InstitutionProfile.get_instance()
        except Exception:
            institution = None

    logo_path = None
    if institution and getattr(institution, 'logo', None) and hasattr(institution.logo, 'path'):
        if os.path.exists(institution.logo.path):
            logo_path = institution.logo.path

    secondary_logo_path = None
    if institution and getattr(institution, 'secondary_logo', None) and hasattr(institution.secondary_logo, 'path'):
        if os.path.exists(institution.secondary_logo.path):
            secondary_logo_path = institution.secondary_logo.path

    logo_data_uri = None
    if logo_path:
        try:
            with open(logo_path, 'rb') as f:
                b64 = base64.b64encode(f.read()).decode('utf-8')
                ext = os.path.splitext(logo_path)[1].lstrip('.').lower() or 'png'
                logo_data_uri = f"data:image/{ext};base64,{b64}"
        except Exception:
            logo_data_uri = None

    name = getattr(institution, 'name', '') or "Fahari Academy"
    display_name = getattr(institution, 'display_name', '') or name
    motto = getattr(institution, 'motto', '') or "Strive for Excellence and Integrity"
    postal = getattr(institution, 'postal_address', '') or getattr(institution, 'address', '') or "P.O. Box 40100 - Nairobi, Kenya"
    phone = getattr(institution, 'phone', '') or "+254 700 000 000"
    email = getattr(institution, 'email', '') or "info@fahariacademy.ac.ke"
    website = getattr(institution, 'website', '') or "www.fahariacademy.ac.ke"

    return {
        "institution": {
            "name": name,
            "display_name": display_name,
            "registered_name": getattr(institution, 'registered_name', '') or "",
            "motto": motto,
            "address": postal,
            "phone": phone,
            "phone_alt": getattr(institution, 'phone_alt', '') or "",
            "email": email,
            "website": website,
            "registration_number": getattr(institution, 'registration_number', '') or "",
            "logo_path": logo_path,
            "secondary_logo_path": secondary_logo_path,
            "logo_url": logo_data_uri or "",
        },
        "brand": {
            "primary": getattr(institution, 'primary_color', '') or "#17365D",
            "secondary": getattr(institution, 'secondary_color', '') or "#1F6B4F",
            "accent": getattr(institution, 'accent_color', '') or "#D4A72C",
            "text": getattr(institution, 'text_color', '') or "#243042",
            "background": getattr(institution, 'background_color', '') or "#FFFFFF",
            "font_family": getattr(institution, 'font_family', '') or "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
            "font_size_body": getattr(institution, 'font_size_body', 10) or 10,
            "font_size_heading": getattr(institution, 'font_size_heading', 18) or 18,
        },
        "current_date": datetime.now().strftime("%d %B %Y"),
        "current_year": datetime.now().strftime("%Y"),
    }


def generate_transparent_watermark_data_uri(watermark_config, context):
    """
    Uses Pillow to pre-render the watermark into a semi-transparent PNG data URI.
    Supports logo images or high-clarity bold diagonal text.
    """
    if not watermark_config or not watermark_config.get("enabled", True):
        return None

    opacity = float(watermark_config.get("opacity", 0.05))
    opacity = max(0.01, min(0.25, opacity))  # Bound between 1% and 25% for readability
    rotation = float(watermark_config.get("rotation", -30))
    wm_type = watermark_config.get("type", "image")

    inst_data = context.get("institution", {})
    logo_path = inst_data.get("logo_path")
    if watermark_config.get("logo_type") == "secondary":
        logo_path = inst_data.get("secondary_logo_path") or logo_path

    try:
        if wm_type == "image" and logo_path and os.path.exists(logo_path):
            img = Image.open(logo_path).convert("RGBA")
            if img.width > 1200 or img.height > 1200:
                img.thumbnail((1200, 1200), Image.Resampling.LANCZOS)

            # Apply transparency to alpha channel
            r, g, b, a = img.split()
            a = a.point(lambda p: int(p * opacity))
            img.putalpha(a)

            if rotation != 0:
                img = img.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"data:image/png;base64,{b64}"

        else:
            # Text-based watermark with high-clarity tracking
            raw_text = watermark_config.get("text_content") or inst_data.get("name") or "OFFICIAL"
            # Add spaced out tracking for elegant watermark appearance
            tracked_text = "  ".join(raw_text.strip().upper())
            width, height = 1200, 1200
            txt_img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
            draw = ImageDraw.Draw(txt_img)

            # Load bold system font if available
            font = None
            for font_candidate in ["arialbd.ttf", "calibrib.ttf", "arial.ttf", "calibri.ttf"]:
                font_path = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", font_candidate)
                if os.path.exists(font_path):
                    try:
                        font = ImageFont.truetype(font_path, 64)
                        break
                    except Exception:
                        pass
            if not font:
                font = ImageFont.load_default()

            alpha_val = int(255 * opacity)
            color = (36, 48, 66, alpha_val)

            bbox = draw.textbbox((0, 0), tracked_text, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            draw.text(((width - text_w) / 2, (height - text_h) / 2), tracked_text, font=font, fill=color)

            if rotation != 0:
                txt_img = txt_img.rotate(rotation, expand=True, resample=Image.Resampling.BICUBIC)

            buf = io.BytesIO()
            txt_img.save(buf, format="PNG")
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            return f"data:image/png;base64,{b64}"
    except Exception:
        return None


def interpolate_variables(text, context):
    """
    Substitutes mustache-style {{variable}} placeholders with context values.
    """
    if not isinstance(text, str):
        return text

    def replacer(match):
        path = match.group(1).strip().split(".")
        val = context
        for key in path:
            if isinstance(val, dict):
                val = val.get(key, "")
            else:
                val = getattr(val, key, "")
            if val is None:
                val = ""
        return str(val)

    return re.sub(r"\{\{([^}]+)\}\}", replacer, text)


def render_column_elements(elements, context, is_footer=False):
    """
    Renders elements inside a header or footer column with calibrated typography.
    """
    html_parts = []
    for el in elements:
        el_type = el.get("type", "text")
        if el_type == "logo":
            logo_url = context.get("institution", {}).get("logo_url")
            width = el.get("width", 75)
            max_height = el.get("max_height", 65)
            if logo_url:
                html_parts.append(
                    f'<img src="{logo_url}" style="width: {width}px; max-height: {max_height}px; object-fit: contain; display: inline-block; vertical-align: middle;" alt="Logo" />'
                )
            else:
                # If no logo uploaded, render a dignified institutional crest placeholder or omit cleanly
                pass
        elif el_type == "text":
            content = interpolate_variables(el.get("content", ""), context)
            if not content:
                continue
            font_family = el.get("font_family")
            font_size = el.get("font_size", 10)
            font_weight = el.get("font_weight", "normal")
            font_style = el.get("font_style", "normal")
            color = interpolate_variables(el.get("color", "inherit"), context)
            margin_bottom = el.get("margin_bottom", 2)
            line_height = el.get("line_height", 1.25)
            letter_spacing = el.get("letter_spacing") or ("-0.2px" if font_weight in ("bold", "800", "900") and font_size >= 14 else "normal")
            text_transform = el.get("text_transform", "none")
            text_decoration = el.get("text_decoration", "none")
            text_align = el.get("text_align", "inherit")
            
            style_parts = [
                f"font-size: {font_size}pt",
                f"font-weight: {font_weight}",
                f"font-style: {font_style}",
                f"color: {color}",
                f"margin-bottom: {margin_bottom}px",
                f"line-height: {line_height}",
                f"letter-spacing: {letter_spacing}",
                f"text-transform: {text_transform}",
                f"text-decoration: {text_decoration}",
                f"text-align: {text_align}",
            ]
            if font_family:
                style_parts.append(f"font-family: {font_family}")
                
            style_str = "; ".join(style_parts) + ";"
            html_parts.append(
                f'<div style="{style_str}">{escape(content)}</div>'
            )
        elif el_type == "pagination":
            fmt = el.get("format", "Page {{page}} of {{pages}}")
            formatted_html = escape(fmt).replace(
                "{{page}}", '<span class="page-number"></span>'
            ).replace(
                "{{pages}}", '<span class="page-count"></span>'
            )
            font_size = el.get("font_size", 8)
            font_weight = el.get("font_weight", "bold")
            color = interpolate_variables(el.get("color", context.get("brand", {}).get("primary", "#17365D")), context)
            html_parts.append(
                f'<div style="font-size: {font_size}pt; font-weight: {font_weight}; color: {color}; letter-spacing: 0.2px;">{formatted_html}</div>'
            )
    return "".join(html_parts)


def build_masthead_html(header_config, context):
    """
    Renders the prominent first-page institutional masthead.
    Supports 3 modes:
      - 'institutional': Uses active institution's branding and shared header layout.
      - 'custom': Uses template-specific columns, falling back to brand defaults.
      - 'none': Suppresses header.
    """
    if not header_config:
        return ""

    mode = header_config.get("mode", "institutional")
    show_header = header_config.get("show_header", True) and mode != "none"
    if not show_header:
        return ""

    columns = header_config.get("columns", {})
    if mode == "institutional" and not columns:
        from documents.models import get_default_header_config
        columns = get_default_header_config().get("columns", {})

    left_col = columns.get("left", {})
    center_col = columns.get("center", {})
    right_col = columns.get("right", {})

    left_html = render_column_elements(left_col.get("elements", []), context)
    center_html = render_column_elements(center_col.get("elements", []), context)
    right_html = render_column_elements(right_col.get("elements", []), context)

    # Dynamic column widths: if left has no logo/content, collapse it so center has full room
    has_left = bool(left_html.strip())
    has_right = bool(right_html.strip())

    if has_left and has_right:
        left_w = left_col.get("width", "22%")
        center_w = center_col.get("width", "54%")
        right_w = right_col.get("width", "24%")
    elif has_left and not has_right:
        left_w = left_col.get("width", "22%")
        center_w = "78%"
        right_w = "0%"
    elif not has_left and has_right:
        left_w = "0%"
        center_w = "70%"
        right_w = right_col.get("width", "30%")
    else:
        left_w = "0%"
        center_w = "100%"
        right_w = "0%"

    left_align = left_col.get("alignment", "left")
    center_align = center_col.get("alignment", "center")
    right_align = right_col.get("alignment", "right")

    divider = header_config.get("divider", {})
    divider_html = ""
    if divider.get("enabled", True):
        primary_color = context.get("brand", {}).get("primary", "#17365D")
        accent_color = interpolate_variables(divider.get("color", context.get("brand", {}).get("accent", "#D4A72C")), context)
        d_width = divider.get("width", 2)
        d_margin = divider.get("margin_top", 8)
        # Signature dual-tone architectural divider bar: primary anchor line + fine accent hairline
        divider_html = f"""
        <div style="margin-top: {d_margin}px; margin-bottom: 20px;">
            <div style="height: {d_width}px; background-color: {primary_color}; width: 100%;"></div>
            <div style="height: 1.5px; background-color: {accent_color}; width: 100%; margin-top: 2px;"></div>
        </div>
        """

    left_td = f'<td style="width: {left_w}; text-align: {left_align}; vertical-align: middle;">{left_html}</td>' if has_left else ''
    right_td = f'<td style="width: {right_w}; text-align: {right_align}; vertical-align: middle;">{right_html}</td>' if has_right else ''

    return f"""
    <header class="document-masthead" style="margin-bottom: 8px;">
        <table class="grid-table" style="width: 100%; border-collapse: collapse;">
            <tr>
                {left_td}
                <td style="width: {center_w}; text-align: {center_align}; vertical-align: middle;">{center_html}</td>
                {right_td}
            </tr>
        </table>
        {divider_html}
    </header>
    """


def build_continuation_header_html(header_config, context, document_title=""):
    """
    Renders the compact running header for continuation pages (page 2+).
    Conserves vertical space while preserving clear institutional authority.
    Suppressed if mode is 'none' or show_header is False.
    """
    if not header_config:
        return ""

    mode = header_config.get("mode", "institutional")
    show_header = header_config.get("show_header", True) and mode != "none"
    if not show_header:
        return ""

    inst_name = context.get("institution", {}).get("display_name") or context.get("institution", {}).get("name", "Fahari Academy")
    primary_color = context.get("brand", {}).get("primary", "#17365D")
    doc_label = document_title or "Official Academic Document"

    return f"""
    <div class="running-continuation-header">
        <table class="grid-table" style="width: 100%; border-collapse: collapse;">
            <tr>
                <td style="text-align: left; vertical-align: middle; width: 60%;">
                    <span style="font-size: 8.5pt; font-weight: 800; color: {primary_color}; letter-spacing: -0.1px;">{escape(inst_name)}</span>
                </td>
                <td style="text-align: right; vertical-align: middle; width: 40%;">
                    <span style="font-size: 8pt; font-weight: 500; color: #64748b;">{escape(doc_label)}</span>
                </td>
            </tr>
        </table>
    </div>
    """


def build_running_footer_html(footer_config, context):
    """
    Renders the repeating footer with dynamic CSS page counters.
    """
    if not footer_config or not footer_config.get("show_footer", True):
        return ""

    columns = footer_config.get("columns", {})
    left_col = columns.get("left", {})
    center_col = columns.get("center", {})
    right_col = columns.get("right", {})

    left_html = render_column_elements(left_col.get("elements", []), context, is_footer=True)
    center_html = render_column_elements(center_col.get("elements", []), context, is_footer=True)
    right_html = render_column_elements(right_col.get("elements", []), context, is_footer=True)

    left_w = left_col.get("width", "38%")
    center_w = center_col.get("width", "28%")
    right_w = right_col.get("width", "34%")

    left_align = left_col.get("alignment", "left")
    center_align = center_col.get("alignment", "center")
    right_align = right_col.get("alignment", "right")

    divider = footer_config.get("divider", {})
    divider_css = ""
    if divider.get("enabled", True):
        d_color = interpolate_variables(divider.get("color", "#e2e8f0"), context)
        d_width = divider.get("width", 1)
        d_style = divider.get("style", "solid")
        d_margin = divider.get("margin_bottom", 6)
        divider_css = f'border-top: {d_width}px {d_style} {d_color}; padding-top: {d_margin}px;'

    return f"""
    <div class="running-footer" style="{divider_css}">
        <table class="grid-table" style="width: 100%; border-collapse: collapse;">
            <tr>
                <td style="width: {left_w}; text-align: {left_align}; vertical-align: middle; color: #64748b; font-size: 7.5pt;">{left_html}</td>
                <td style="width: {center_w}; text-align: {center_align}; vertical-align: middle; color: #94a3b8; font-size: 7.5pt;">{center_html}</td>
                <td style="width: {right_w}; text-align: {right_align}; vertical-align: middle;">{right_html}</td>
            </tr>
        </table>
    </div>
    """


def generate_document_html(template, context=None, html_body=None):
    """
    Generates complete HTML and CSS for WeasyPrint paged media.
    Enforces distinct first-page prominent masthead vs compact continuation page headers,
    balanced page geometry, Pillow watermark, and print-grade typography.
    """
    if context is None:
        context = get_default_context()

    page_config = getattr(template, "page_config", None) or {}
    header_config = getattr(template, "header_config", None) or {}
    footer_config = getattr(template, "footer_config", None) or {}
    watermark_config = getattr(template, "watermark_config", None) or {}

    size = page_config.get("size", "A4")
    orientation = page_config.get("orientation", "portrait")
    margin_top = page_config.get("margin_top", "24mm")
    margin_bottom = page_config.get("margin_bottom", "22mm")
    margin_left = page_config.get("margin_left", "18mm")
    margin_right = page_config.get("margin_right", "18mm")

    watermark_uri = generate_transparent_watermark_data_uri(watermark_config, context)
    watermark_css = ""
    if watermark_uri:
        scale = int(float(watermark_config.get("scale", 0.55)) * 100)
        watermark_css = f"""
            background-image: url('{watermark_uri}');
            background-repeat: no-repeat;
            background-position: center center;
            background-size: {scale}% auto;
        """

    header_mode = header_config.get("mode", "institutional")
    show_header = bool(header_config.get("show_header", True) and header_mode != "none")
    repeat_full_header = bool(header_config.get("repeat_full_header", False))
    doc_title = getattr(template, 'name', '') or "Official Document"

    running_footer_html = build_running_footer_html(footer_config, context)

    # First page masthead vs continuation header strategy
    if not show_header:
        running_header_html = ""
        masthead_in_flow = ""
        page_top_center_rule = "content: none;"
        first_page_rule = "@page:first { @top-center { content: none; } }"
    elif repeat_full_header:
        # Full header repeats on every page via CSS runningHeader
        running_header_html = f'<div class="running-header">{build_masthead_html(header_config, context)}</div>'
        masthead_in_flow = ""
        page_top_center_rule = "content: element(runningHeader); width: 100%;"
        first_page_rule = ""
    else:
        # Professional standard: First page has masthead in document flow.
        # Continuation pages have compact running header via element(continuationHeader).
        running_header_html = build_continuation_header_html(header_config, context, doc_title)
        masthead_in_flow = build_masthead_html(header_config, context)
        page_top_center_rule = "content: element(continuationHeader); width: 100%;"
        first_page_rule = """
            @page:first {
                margin-top: 16mm;
                @top-center {
                    content: none;
                }
            }
        """

    if not html_body:
        html_body = f"""
        <div class="report-header">
            <h1 class="doc-title">{escape(doc_title)}</h1>
            <p class="doc-meta">Academic Year: {context['current_year']} | Document Reference: FA-DOC-{datetime.now().strftime('%Y%m%d%H%M')}</p>
        </div>

        <div class="content-section" style="margin-top: 15px;">
            <h2 class="section-title">1. Institutional Summary</h2>
            <p style="font-size: 9.5pt; line-height: 1.55; color: #334155;">
                This document layout demonstrates the verified WeasyPrint paged media rendering pipeline in Fahari Academia.
                The document branding incorporates the institution's primary palette (<strong>{context['brand']['primary']}</strong>),
                secondary accent (<strong>{context['brand']['secondary']}</strong>), and official motto.
            </p>
            <table class="data-table">
                <thead>
                    <tr>
                        <th style="width: 35%;">Specification</th>
                        <th style="width: 45%;">Configuration Value</th>
                        <th style="width: 20%; text-align: center;">Status</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>Continuation Header</td>
                        <td>Compact running header on subsequent pages</td>
                        <td style="text-align: center; color: #166534; font-weight: bold;">Verified</td>
                    </tr>
                    <tr>
                        <td>Dynamic Page Counters</td>
                        <td>CSS counter(page) and counter(pages)</td>
                        <td style="text-align: center; color: #166534; font-weight: bold;">Verified</td>
                    </tr>
                    <tr>
                        <td>Watermark Pre-Rendering</td>
                        <td>Pillow RGBA Alpha Channel @ {watermark_config.get('opacity', 0.05)*100:.1f}% Opacity</td>
                        <td style="text-align: center; color: #166534; font-weight: bold;">Verified</td>
                    </tr>
                </tbody>
            </table>
        </div>

        <div style="page-break-before: always; margin-top: 10px;">
            <h2 class="section-title">2. Multi-Page Continuation Verification</h2>
            <p style="font-size: 9.5pt; line-height: 1.55; color: #334155;">
                This is Page 2 of the generated PDF document. Notice that:
            </p>
            <ul style="font-size: 9pt; line-height: 1.6; color: #334155; padding-left: 20px;">
                <li>The compact continuation header displays automatically at the top of subsequent pages.</li>
                <li>The footer displays the exact page counter for Page 2 without Python estimation.</li>
                <li>The semi-transparent watermark sits behind the document text without obscuring legibility.</li>
            </ul>
            <div style="margin-top: 30px; border: 1px dashed {context['brand']['accent']}; padding: 15px; border-radius: 6px; background-color: #fafafa;">
                <p style="margin: 0; font-size: 8.5pt; color: #64748b; font-style: italic;">
                    Certified by Fahari Academia Document Design Studio. Generated dynamically via WeasyPrint engine.
                </p>
            </div>
        </div>
        """

    primary_color = context.get("brand", {}).get("primary", "#17365D")
    secondary_color = context.get("brand", {}).get("secondary", "#1F6B4F")
    accent_color = context.get("brand", {}).get("accent", "#D4A72C")
    text_color = context.get("brand", {}).get("text", "#243042")
    font_family = context.get("brand", {}).get("font_family", "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif")

    # Table presentation configuration
    table_config = getattr(template, "table_config", None) or {}
    tbl_header_bg = interpolate_variables(table_config.get("header_bg", primary_color), context)
    tbl_header_text = interpolate_variables(table_config.get("header_text", "#ffffff"), context)
    tbl_header_font_size = table_config.get("header_font_size", 8.5)
    tbl_header_font_weight = table_config.get("header_font_weight", "bold")
    tbl_body_text = interpolate_variables(table_config.get("body_text", "#1e293b"), context)
    tbl_body_font_size = table_config.get("body_font_size", 8.5)
    tbl_alt_row_bg = interpolate_variables(table_config.get("alt_row_bg", "#f8fafc"), context)
    tbl_border_color = interpolate_variables(table_config.get("border_color", "#cbd5e1"), context)
    tbl_border_width = table_config.get("border_width", "0.5pt")
    tbl_cell_padding = table_config.get("cell_padding", "6px 10px")
    tbl_text_align = table_config.get("text_align", "left")
    tbl_repeat_header = table_config.get("repeat_header", True)
    tbl_display_thead = "table-header-group" if tbl_repeat_header else "table-row-group"

    full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{escape(doc_title)}</title>
    <style>
        @page {{
            size: {size} {orientation};
            margin-top: {margin_top};
            margin-bottom: {margin_bottom};
            margin-left: {margin_left};
            margin-right: {margin_right};
            {watermark_css}

            @top-center {{
                {page_top_center_rule}
            }}
            @bottom-center {{
                content: element(runningFooter);
                width: 100%;
            }}
        }}

        {first_page_rule}

        body {{
            font-family: {font_family};
            color: {text_color};
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            line-height: 1.5;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
        }}

        .running-header {{
            position: running(runningHeader);
            width: 100%;
        }}

        .running-continuation-header {{
            position: running(continuationHeader);
            width: 100%;
            border-bottom: 0.75pt solid #cbd5e1;
            padding-bottom: 5px;
        }}

        .running-footer {{
            position: running(runningFooter);
            width: 100%;
        }}

        .page-number::before {{
            content: counter(page);
        }}

        .page-count::before {{
            content: counter(pages);
        }}

        .grid-table {{
            width: 100%;
            border-collapse: collapse;
        }}

        .grid-table td {{
            padding: 0;
            vertical-align: middle;
        }}

        /* Document Typographic System */
        h1, h2, h3, h4 {{
            color: {primary_color};
            margin-top: 0;
            line-height: 1.25;
        }}

        .doc-title {{
            font-size: 15pt;
            font-weight: 800;
            letter-spacing: -0.2px;
            color: {primary_color};
            margin-bottom: 4px;
        }}

        .doc-meta {{
            font-size: 8.5pt;
            color: #64748b;
            margin-top: 0;
            margin-bottom: 16px;
        }}

        .section-title {{
            font-size: 11pt;
            font-weight: 700;
            color: {secondary_color};
            border-bottom: 1px solid #e2e8f0;
            padding-bottom: 4px;
            margin-top: 18px;
            margin-bottom: 10px;
        }}

        /* Data Tables with configurable styling */
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: {tbl_body_font_size}pt;
            margin-top: 10px;
            margin-bottom: 16px;
        }}

        .data-table thead {{
            display: {tbl_display_thead};
        }}

        .data-table thead tr {{
            background-color: {tbl_header_bg};
            color: {tbl_header_text};
            page-break-inside: avoid;
        }}

        .data-table thead th {{
            padding: {tbl_cell_padding};
            text-align: {tbl_text_align};
            font-size: {tbl_header_font_size}pt;
            font-weight: {tbl_header_font_weight};
            border: {tbl_border_width} solid {tbl_header_bg};
        }}

        .data-table tbody td {{
            padding: {tbl_cell_padding};
            border: {tbl_border_width} solid {tbl_border_color};
            color: {tbl_body_text};
            font-size: {tbl_body_font_size}pt;
            text-align: {tbl_text_align};
        }}

        .data-table tbody tr:nth-child(even) {{
            background-color: {tbl_alt_row_bg};
        }}

        .data-table tbody tr {{
            page-break-inside: avoid;
        }}

        /* Clean cards / summary panels */
        .info-card {{
            background-color: #f8fafc;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
            padding: 12px 16px;
            margin-bottom: 16px;
        }}
    </style>
</head>
<body>
    {running_header_html}
    {running_footer_html}

    <main class="document-content">
        {masthead_in_flow}
        {html_body}
    </main>
</body>
</html>
"""
    return full_html


def render_pdf_bytes(template, context=None, html_body=None):
    """
    Renders the document template and content to binary PDF data using WeasyPrint.
    """
    html_content = generate_document_html(template, context=context, html_body=html_body)
    wp_html = weasyprint.HTML(string=html_content)
    pdf_bytes = wp_html.write_pdf()
    return pdf_bytes
