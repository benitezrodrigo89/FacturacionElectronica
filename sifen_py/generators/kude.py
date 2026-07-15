"""
Generador de KuDE (Kuatia De'a Electrónica) — Representación impresa del DE.
Manual Técnico SIFEN v150 — Sección 10.

Soporta todos los tipos de documento:
  1 = Factura Electrónica (FE)
  4 = Autofactura Electrónica (AFE)
  5 = Nota de Crédito Electrónica (NCE)
  6 = Nota de Débito Electrónica (NDE)
  7 = Nota de Remisión Electrónica (NRE)
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Optional
from loguru import logger

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.units import mm, cm
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph,
        Spacer, HRFlowable, KeepTogether,
    )
    from reportlab.platypus.flowables import Image as RLImage
    import qrcode
    from qrcode.image.pil import PilImage
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

from sifen_py.core.config import SifenConfig
from sifen_py.core.constants import URLS, AMBIENTE_TEST
from sifen_py.core.exceptions import KuDEException

# ─────────────────────────────────────────────────────────────
# CONSTANTES DE DISEÑO
# ─────────────────────────────────────────────────────────────
COLOR_HEADER    = colors.HexColor('#1a3a5c')
COLOR_SUBHEADER = colors.HexColor('#2e6da4')
COLOR_ROW_ALT   = colors.HexColor('#f0f4f8')
COLOR_BORDER    = colors.HexColor('#aac4e0')
COLOR_TEXT      = colors.HexColor('#222222')
COLOR_GRAY      = colors.HexColor('#666666')
COLOR_RED       = colors.HexColor('#c0392b')

TIPO_DOC_LABELS = {
    1: 'FACTURA ELECTRÓNICA',
    4: 'AUTOFACTURA ELECTRÓNICA',
    5: 'NOTA DE CRÉDITO ELECTRÓNICA',
    6: 'NOTA DE DÉBITO ELECTRÓNICA',
    7: 'NOTA DE REMISIÓN ELECTRÓNICA',
}

TIPO_DOC_PREFIJOS = {1: 'FE', 4: 'AFE', 5: 'NCE', 6: 'NDE', 7: 'NRE'}

ESTADO_LABELS = {
    'A': 'APROBADO',
    'R': 'RECHAZADO',
    'P': 'PENDIENTE',
}


def _fmt_gs(monto) -> str:
    """Formatea un número como guaraníes con separador de miles."""
    try:
        return f"₲ {int(float(monto)):,}".replace(',', '.')
    except (ValueError, TypeError):
        return str(monto)


def _fmt_date(fecha_str: str) -> str:
    """Convierte ISO datetime a formato legible."""
    try:
        dt = datetime.fromisoformat(fecha_str.replace('Z', ''))
        return dt.strftime('%d/%m/%Y %H:%M')
    except Exception:
        return fecha_str


# ─────────────────────────────────────────────────────────────
# GENERADOR PRINCIPAL
# ─────────────────────────────────────────────────────────────
class KuDEGenerator:
    """
    Genera el KuDE (representación impresa) en PDF para cualquier
    tipo de Documento Electrónico SIFEN.

    Ejemplo::

        gen = KuDEGenerator(config)
        pdf_bytes = gen.generar(factura_data, cdc='...', estado='A')
        with open('kude.pdf', 'wb') as f:
            f.write(pdf_bytes)
    """

    PAGE_SIZE = A4
    MARGIN    = 12 * mm

    def __init__(self, config: SifenConfig):
        if not REPORTLAB_OK:
            raise KuDEException(
                "reportlab y qrcode son requeridos. "
                "Instala con: pip install reportlab qrcode pillow"
            )
        self.config = config
        self._estilos = self._build_styles()

    # ─────────────────────────────────────────────────────────
    # API PÚBLICA
    # ─────────────────────────────────────────────────────────
    def generar(
        self,
        data: dict,
        cdc: str,
        estado: str = 'A',
        numero_protocolo: Optional[str] = None,
        fecha_procesamiento: Optional[str] = None,
        logo_path: Optional[str] = None,
    ) -> bytes:
        """
        Genera el KuDE como bytes PDF.

        Args:
            data:                 Diccionario con los datos del documento
            cdc:                  CDC de 44 dígitos
            estado:               'A'=Aprobado, 'R'=Rechazado, 'P'=Pendiente
            numero_protocolo:     Número de protocolo SIFEN (si fue aprobado)
            fecha_procesamiento:  Fecha/hora de aprobación por SIFEN
            logo_path:            Ruta opcional al logo del emisor (PNG/JPG)

        Returns:
            bytes con el contenido del PDF
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=self.PAGE_SIZE,
            leftMargin=self.MARGIN,
            rightMargin=self.MARGIN,
            topMargin=self.MARGIN,
            bottomMargin=self.MARGIN,
            title=f"KuDE - {cdc}",
        )

        tipo = int(data.get('tipoDocumento', 1))
        story = []

        # Cabecera emisor + título
        story.extend(self._seccion_cabecera(data, tipo, logo_path))
        story.append(Spacer(1, 3 * mm))

        # Datos del documento
        story.extend(self._seccion_documento(data, cdc, estado, numero_protocolo, fecha_procesamiento))
        story.append(Spacer(1, 3 * mm))

        # Datos del receptor
        story.extend(self._seccion_receptor(data, tipo))
        story.append(Spacer(1, 3 * mm))

        # Items (solo para FE, AFE, NDE, NCE)
        if tipo in (1, 4, 5, 6):
            story.extend(self._seccion_items(data))
            story.append(Spacer(1, 3 * mm))
            story.extend(self._seccion_totales(data))
            story.append(Spacer(1, 3 * mm))
            story.extend(self._seccion_condicion_pago(data))
        elif tipo == 7:
            story.extend(self._seccion_remision(data))

        story.append(Spacer(1, 5 * mm))

        # QR + pie
        story.extend(self._seccion_qr_pie(cdc, estado))

        doc.build(story)
        buffer.seek(0)
        logger.info(f"KuDE generado para CDC: {cdc}")
        return buffer.read()

    def guardar(self, data: dict, cdc: str, ruta_salida: str, **kwargs) -> str:
        """
        Genera y guarda el KuDE en disco.

        Returns:
            Ruta del archivo guardado
        """
        pdf = self.generar(data, cdc, **kwargs)
        with open(ruta_salida, 'wb') as f:
            f.write(pdf)
        logger.success(f"KuDE guardado en: {ruta_salida}")
        return ruta_salida

    # ─────────────────────────────────────────────────────────
    # SECCIONES
    # ─────────────────────────────────────────────────────────
    def _seccion_cabecera(self, data: dict, tipo: int, logo_path: Optional[str]) -> list:
        cfg = self.config
        label_tipo = TIPO_DOC_LABELS.get(tipo, 'DOCUMENTO ELECTRÓNICO')
        prefijo    = TIPO_DOC_PREFIJOS.get(tipo, 'DE')

        # Columna izquierda: logo + datos emisor
        emisor_lines = [
            Paragraph(cfg.razon_social.upper(), self._estilos['emisor_nombre']),
            Paragraph(f"RUC: {cfg.ruc}", self._estilos['emisor_dato']),
        ]
        if cfg.actividad_economica:
            emisor_lines.append(Paragraph(f"Actividad Económica: {cfg.actividad_economica}", self._estilos['emisor_dato']))
        if cfg.direccion:
            emisor_lines.append(Paragraph(f"Dirección: {cfg.direccion}", self._estilos['emisor_dato']))
        if cfg.telefono:
            emisor_lines.append(Paragraph(f"Tel: {cfg.telefono}", self._estilos['emisor_dato']))
        if cfg.email:
            emisor_lines.append(Paragraph(f"Email: {cfg.email}", self._estilos['emisor_dato']))

        if cfg.es_test():
            emisor_lines.insert(0, Paragraph("⚠ AMBIENTE DE PRUEBA — NO VÁLIDO COMO COMPROBANTE", self._estilos['test_banner']))

        col_emisor = emisor_lines

        # Logo
        logo_content = []
        if logo_path:
            try:
                img = RLImage(logo_path, width=40*mm, height=20*mm, kind='proportional')
                logo_content.append(img)
            except Exception:
                pass
        logo_content.append(Spacer(1, 1*mm))

        # Columna derecha: tipo de documento + número
        estab   = data.get('establecimiento', '001')
        punto   = data.get('punto', '001')
        numero  = data.get('numero', '0000001')
        nro_str = f"{estab}-{punto}-{numero}"

        col_doc = [
            Paragraph(label_tipo, self._estilos['tipo_doc']),
            Paragraph(nro_str, self._estilos['nro_doc']),
            Paragraph(f"Timbrado: {data.get('timbrado', '—')}", self._estilos['timbrado']),
        ]

        tabla = Table(
            [[logo_content, col_emisor, col_doc]],
            colWidths=[35*mm, 95*mm, 60*mm],
        )
        tabla.setStyle(TableStyle([
            ('VALIGN',      (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING',  (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING',   (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 2),
            ('BOX',         (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ('BACKGROUND',  (0, 0), (-1, -1), colors.white),
        ]))
        return [tabla]

    def _seccion_documento(self, data: dict, cdc: str, estado: str,
                           numero_protocolo: Optional[str],
                           fecha_procesamiento: Optional[str]) -> list:
        estado_label = ESTADO_LABELS.get(estado, estado)
        estado_color = COLOR_SUBHEADER if estado == 'A' else COLOR_RED

        rows = [
            ['CDC:', Paragraph(cdc, self._estilos['cdc'])],
            ['Fecha emisión:', _fmt_date(data.get('fecha', '—'))],
            ['Estado:', Paragraph(f'<font color="{estado_color.hexval()}">{estado_label}</font>', self._estilos['normal'])],
        ]
        if numero_protocolo:
            rows.append(['Protocolo:', numero_protocolo])
        if fecha_procesamiento:
            rows.append(['Fecha aprobación:', _fmt_date(fecha_procesamiento)])
        if data.get('tipoEmision') == 2:
            rows.append(['Tipo emisión:', Paragraph('<font color="red">CONTINGENCIA</font>', self._estilos['normal'])])

        tabla = Table(rows, colWidths=[38*mm, None])
        tabla.setStyle(self._estilo_tabla_datos())
        return [
            Paragraph('DATOS DEL DOCUMENTO', self._estilos['seccion_titulo']),
            tabla,
        ]

    def _seccion_receptor(self, data: dict, tipo: int) -> list:
        c = data.get('cliente', {})
        label = 'DATOS DEL RECEPTOR' if tipo != 4 else 'DATOS DEL PROVEEDOR'
        rows = [
            ['Razón Social:', c.get('razonSocial', '—')],
            ['RUC / CI:', c.get('ruc') or c.get('documentoNumero', '—')],
            ['Dirección:', c.get('direccion', '—')],
        ]
        if c.get('telefono'):
            rows.append(['Teléfono:', c.get('telefono')])
        if c.get('email'):
            rows.append(['Email:', c.get('email')])

        tabla = Table(rows, colWidths=[38*mm, None])
        tabla.setStyle(self._estilo_tabla_datos())
        return [
            Paragraph(label, self._estilos['seccion_titulo']),
            tabla,
        ]

    def _seccion_items(self, data: dict) -> list:
        items = data.get('items', [])
        encabezado = [
            Paragraph('Cód.', self._estilos['th']),
            Paragraph('Descripción', self._estilos['th']),
            Paragraph('Cant.', self._estilos['th']),
            Paragraph('P. Unit.', self._estilos['th']),
            Paragraph('Desc.', self._estilos['th']),
            Paragraph('IVA %', self._estilos['th']),
            Paragraph('Total', self._estilos['th']),
        ]
        filas = [encabezado]
        for i, item in enumerate(items):
            bg = COLOR_ROW_ALT if i % 2 == 0 else colors.white
            desc = item.get('descripcion', '')
            if item.get('obs'):
                desc += f"\n{item['obs']}"
            fila = [
                item.get('codigo', ''),
                Paragraph(desc, self._estilos['td_desc']),
                str(item.get('cantidad', '')),
                _fmt_gs(item.get('precioUnitario', 0)),
                _fmt_gs(item.get('descuento', 0)) if item.get('descuento') else '—',
                f"{item.get('iva', 0)}%",
                _fmt_gs(float(item.get('cantidad', 0)) * float(item.get('precioUnitario', 0))),
            ]
            filas.append(fila)

        col_widths = [20*mm, None, 18*mm, 28*mm, 22*mm, 16*mm, 28*mm]
        tabla = Table(filas, colWidths=col_widths, repeatRows=1)
        tabla.setStyle(TableStyle([
            # Encabezado
            ('BACKGROUND',   (0, 0), (-1, 0), COLOR_HEADER),
            ('TEXTCOLOR',    (0, 0), (-1, 0), colors.white),
            ('FONTNAME',     (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE',     (0, 0), (-1, 0), 7),
            ('ALIGN',        (0, 0), (-1, 0), 'CENTER'),
            # Datos
            ('FONTSIZE',     (0, 1), (-1, -1), 7),
            ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN',        (2, 1), (-1, -1), 'RIGHT'),   # numéricos alineados derecha
            ('ALIGN',        (0, 1), (1, -1), 'LEFT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, COLOR_ROW_ALT]),
            ('GRID',         (0, 0), (-1, -1), 0.3, COLOR_BORDER),
            ('TOPPADDING',   (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 2),
            ('LEFTPADDING',  (0, 0), (-1, -1), 3),
            ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ]))
        return [
            Paragraph('DETALLE DE ITEMS', self._estilos['seccion_titulo']),
            tabla,
        ]

    def _seccion_totales(self, data: dict) -> list:
        items    = data.get('items', [])
        subtotal = sum(float(i.get('cantidad', 0)) * float(i.get('precioUnitario', 0)) for i in items)
        desc_gl  = float(data.get('descuentoGlobal', 0))
        subtotal_neto = subtotal - desc_gl

        # Calcular IVA por tasa
        iva_10 = sum(
            float(i.get('cantidad', 0)) * float(i.get('precioUnitario', 0)) / 11
            for i in items if int(i.get('iva', 0)) == 10
        )
        iva_5 = sum(
            float(i.get('cantidad', 0)) * float(i.get('precioUnitario', 0)) / 21
            for i in items if int(i.get('iva', 0)) == 5
        )
        exentas = sum(
            float(i.get('cantidad', 0)) * float(i.get('precioUnitario', 0))
            for i in items if int(i.get('iva', 0)) == 0
        )

        rows = []
        if desc_gl:
            rows.append(['Subtotal:', _fmt_gs(subtotal)])
            rows.append(['Descuento global:', f'- {_fmt_gs(desc_gl)}'])
        rows.extend([
            ['Exentas:', _fmt_gs(exentas)],
            ['Gravadas 5%:', _fmt_gs(sum(float(i.get('cantidad',0))*float(i.get('precioUnitario',0)) for i in items if int(i.get('iva',0))==5))],
            ['Gravadas 10%:', _fmt_gs(sum(float(i.get('cantidad',0))*float(i.get('precioUnitario',0)) for i in items if int(i.get('iva',0))==10))],
            ['IVA 5%:', _fmt_gs(iva_5)],
            ['IVA 10%:', _fmt_gs(iva_10)],
            [Paragraph('<b>TOTAL A PAGAR:</b>', self._estilos['normal']),
             Paragraph(f'<b>{_fmt_gs(subtotal_neto)}</b>', self._estilos['total'])],
        ])

        tabla = Table(rows, colWidths=[None, 45*mm], hAlign='RIGHT')
        tabla.setStyle(TableStyle([
            ('FONTSIZE',     (0, 0), (-1, -1), 8),
            ('ALIGN',        (1, 0), (1, -1), 'RIGHT'),
            ('ALIGN',        (0, 0), (0, -1), 'RIGHT'),
            ('LINEABOVE',    (0, -1), (-1, -1), 1, COLOR_HEADER),
            ('TOPPADDING',   (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 2),
        ]))
        return [tabla]

    def _seccion_condicion_pago(self, data: dict) -> list:
        cond = data.get('condicion', {})
        tipo = int(cond.get('tipo', 1))
        tipo_str = 'Contado' if tipo == 1 else 'Crédito'
        rows = [['Condición de pago:', tipo_str]]

        entregas = cond.get('entregas', [])
        FORMAS_PAGO = {1:'Efectivo',2:'Cheque',3:'Tarjeta de crédito',4:'Tarjeta de débito',
                       5:'Transferencia',6:'Giro',7:'Billetera electrónica',9:'Vale',99:'Otros'}
        for e in entregas:
            forma = FORMAS_PAGO.get(int(e.get('tipo', 99)), 'Otro')
            rows.append([f'  {forma}:', _fmt_gs(e.get('monto', 0))])

        if tipo == 2:
            cuotas = cond.get('credito', {}).get('cuotas', [])
            for i, c in enumerate(cuotas, 1):
                rows.append([f'  Cuota {i} ({c.get("vencimiento","")}):', _fmt_gs(c.get('monto', 0))])

        tabla = Table(rows, colWidths=[50*mm, None])
        tabla.setStyle(self._estilo_tabla_datos())
        return [
            Paragraph('CONDICIÓN DE PAGO', self._estilos['seccion_titulo']),
            tabla,
        ]

    def _seccion_remision(self, data: dict) -> list:
        rows = [
            ['Motivo remisión:', data.get('motivoRemision', '—')],
            ['Origen:', data.get('origen', '—')],
            ['Destino:', data.get('destino', '—')],
        ]
        if data.get('transportista'):
            t = data['transportista']
            rows.append(['Transportista:', t.get('nombre', '—')])
            rows.append(['Matrícula:', t.get('matricula', '—')])
        tabla = Table(rows, colWidths=[40*mm, None])
        tabla.setStyle(self._estilo_tabla_datos())
        return [
            Paragraph('DATOS DE REMISIÓN', self._estilos['seccion_titulo']),
            tabla,
        ]

    def _seccion_qr_pie(self, cdc: str, estado: str) -> list:
        # Generar URL del QR
        base_qr = URLS[self.config.ambiente]['qr']
        qr_url  = f"{base_qr}?nVersion=150&Id={cdc}"

        # Imagen QR
        qr_img = qrcode.make(qr_url, image_factory=PilImage)
        qr_buf = io.BytesIO()
        qr_img.save(qr_buf, format='PNG')
        qr_buf.seek(0)
        qr_rl = RLImage(qr_buf, width=28*mm, height=28*mm)

        nota_qr = [
            Paragraph('Escanee el código QR para verificar este documento en el portal de la SET.',
                       self._estilos['pie_nota']),
            Paragraph(f'URL: {qr_url}', self._estilos['pie_url']),
        ]

        tabla = Table([[qr_rl, nota_qr]], colWidths=[32*mm, None])
        tabla.setStyle(TableStyle([
            ('VALIGN',  (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING',   (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING',(0, 0), (-1, -1), 3),
        ]))

        pie = Paragraph(
            f'Documento generado por el Sistema SIFEN Paraguay • Manual Técnico v150 • '
            f'{"AMBIENTE DE PRUEBA" if self.config.es_test() else "AMBIENTE DE PRODUCCIÓN"}',
            self._estilos['pie_sistema'],
        )
        return [
            HRFlowable(width='100%', thickness=0.5, color=COLOR_BORDER),
            Spacer(1, 2*mm),
            tabla,
            Spacer(1, 2*mm),
            pie,
        ]

    # ─────────────────────────────────────────────────────────
    # ESTILOS
    # ─────────────────────────────────────────────────────────
    def _build_styles(self) -> dict:
        base = getSampleStyleSheet()
        def ps(name, **kw) -> ParagraphStyle:
            return ParagraphStyle(name, parent=base['Normal'], **kw)

        return {
            'test_banner': ps('test_banner',
                fontSize=8, textColor=colors.white,
                backColor=COLOR_RED, alignment=TA_CENTER,
                spaceAfter=2, borderPadding=3),
            'emisor_nombre': ps('emisor_nombre',
                fontSize=10, fontName='Helvetica-Bold',
                textColor=COLOR_HEADER, spaceAfter=2),
            'emisor_dato': ps('emisor_dato',
                fontSize=7, textColor=COLOR_TEXT, leading=10),
            'tipo_doc': ps('tipo_doc',
                fontSize=9, fontName='Helvetica-Bold',
                textColor=COLOR_SUBHEADER, alignment=TA_CENTER, spaceAfter=3),
            'nro_doc': ps('nro_doc',
                fontSize=14, fontName='Helvetica-Bold',
                textColor=COLOR_HEADER, alignment=TA_CENTER, spaceAfter=2),
            'timbrado': ps('timbrado',
                fontSize=7, textColor=COLOR_GRAY, alignment=TA_CENTER),
            'seccion_titulo': ps('seccion_titulo',
                fontSize=8, fontName='Helvetica-Bold',
                textColor=colors.white, backColor=COLOR_SUBHEADER,
                spaceAfter=1, borderPadding=(3, 5, 3, 5)),
            'cdc': ps('cdc',
                fontSize=6.5, fontName='Courier',
                textColor=COLOR_TEXT, leading=9),
            'normal': ps('normal', fontSize=8, textColor=COLOR_TEXT),
            'total': ps('total',
                fontSize=10, fontName='Helvetica-Bold',
                textColor=COLOR_HEADER, alignment=TA_RIGHT),
            'th': ps('th',
                fontSize=7, fontName='Helvetica-Bold',
                textColor=colors.white, alignment=TA_CENTER),
            'td_desc': ps('td_desc', fontSize=7, leading=9),
            'pie_nota': ps('pie_nota', fontSize=7, textColor=COLOR_GRAY, leading=10),
            'pie_url':  ps('pie_url',  fontSize=6, textColor=COLOR_SUBHEADER,
                fontName='Courier', leading=8),
            'pie_sistema': ps('pie_sistema',
                fontSize=6, textColor=COLOR_GRAY, alignment=TA_CENTER),
        }

    def _estilo_tabla_datos(self) -> TableStyle:
        return TableStyle([
            ('FONTSIZE',      (0, 0), (-1, -1), 8),
            ('FONTNAME',      (0, 0), (0, -1), 'Helvetica-Bold'),
            ('TEXTCOLOR',     (0, 0), (0, -1), COLOR_GRAY),
            ('VALIGN',        (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING',    (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING',   (0, 0), (-1, -1), 4),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 4),
            ('ROWBACKGROUNDS',(0, 0), (-1, -1), [colors.white, COLOR_ROW_ALT]),
            ('BOX',           (0, 0), (-1, -1), 0.3, COLOR_BORDER),
        ])
