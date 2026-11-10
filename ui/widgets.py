"""Piezas visuales reutilizadas por todas las secciones."""
import flet as ft

MUTED = ft.Colors.ON_SURFACE_VARIANT
RADIUS = 16


def app_logo(size=48):
    """Icono de la app (assets/icon.png)."""
    return ft.Image(src="icon.png", width=size, height=size, fit=ft.BoxFit.CONTAIN)


def page_header(title, subtitle=None):
    controls = [ft.Text(title, size=26, weight=ft.FontWeight.W_600)]
    if subtitle:
        controls.append(ft.Text(subtitle, size=14, color=MUTED))
    return ft.Column(controls, spacing=4)


def card(content, expand=None, padding=16):
    return ft.Container(
        content=content,
        bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
        border_radius=RADIUS,
        padding=padding,
        expand=expand,
    )


def section(title, controls, icon=None):
    head = [ft.Text(title, size=15, weight=ft.FontWeight.W_600)]
    if icon:
        head.insert(0, ft.Icon(icon, size=20, color=ft.Colors.PRIMARY))
    return card(ft.Column([ft.Row(head, spacing=8), *controls], spacing=14))


def empty_state(icon, text):
    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(icon, size=48, color=ft.Colors.OUTLINE),
                ft.Text(text, text_align=ft.TextAlign.CENTER, color=MUTED),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=12,
        ),
        expand=True,
        padding=24,
        alignment=ft.Alignment.CENTER,
    )


def list_header(title, count=None, actions=None):
    label = ft.Text(title, size=15, weight=ft.FontWeight.W_600)
    row = [label]
    if count is not None:
        row.append(ft.Container(
            content=ft.Text(str(count), size=12, color=ft.Colors.ON_PRIMARY_CONTAINER),
            bgcolor=ft.Colors.PRIMARY_CONTAINER,
            border_radius=10,
            padding=ft.Padding(8, 2, 8, 2),
        ))
    row.append(ft.Container(expand=True))
    row.extend(actions or [])
    return ft.Row(row, spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def leading_icon(icon):
    return ft.Container(
        content=ft.Icon(icon, size=20, color=ft.Colors.ON_SECONDARY_CONTAINER),
        bgcolor=ft.Colors.SECONDARY_CONTAINER,
        width=40, height=40, border_radius=20,
        alignment=ft.Alignment.CENTER,
    )


def item_tile(title, subtitle=None, icon=ft.Icons.MUSIC_NOTE, trailing=None):
    return ft.ListTile(
        leading=leading_icon(icon),
        title=ft.Text(title, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
        subtitle=ft.Text(subtitle, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, color=MUTED, size=12)
        if subtitle else None,
        trailing=trailing,
        dense=True,
        shape=ft.RoundedRectangleBorder(radius=12),
    )


def setting_switch(title, subtitle, value, on_change):
    texts = [ft.Text(title)]
    if subtitle:
        texts.append(ft.Text(subtitle, size=12, color=MUTED))
    return ft.Row(
        [ft.Column(texts, spacing=2, expand=True), ft.Switch(value=bool(value), on_change=on_change)],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def dropdown(label, value, options, on_select, width=None, disabled=False, col=None):
    """options: lista de (clave, texto)."""
    return ft.Dropdown(
        label=label,
        value=value,
        options=[ft.DropdownOption(key=k, text=t) for k, t in options],
        on_select=on_select,
        width=width,
        disabled=disabled,
        col=col or {"xs": 12, "md": 6},
        expand=True,
    )


def fmt_duration(seconds):
    try:
        seconds = int(float(seconds))
    except (TypeError, ValueError):
        return ""
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
