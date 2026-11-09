"""
Script de pruebas de lotes para habilitación DNIT (Guía de Pruebas).

Envía N documentos del tipo indicado como un único lote asíncrono,
espera el procesamiento y consulta el resultado.

Uso:
    cd FacturacionElectronica
    python prueba_lotes_dnit.py                   # 5 FE correctas
    python prueba_lotes_dnit.py --tipo 5          # 5 NCE correctas
    python prueba_lotes_dnit.py --tipo 1 --n 3    # 3 FE correctas
    python prueba_lotes_dnit.py --incorrecto       # 5 FE incorrectas (CDC duplicado)

Tipos: 1=FE, 4=AFE, 5=NCE, 6=NDE, 7=NRE
"""
import sys
import json
import random
import time
import argparse
import warnings
from datetime import datetime
warnings.filterwarnings('ignore')

sys.path.insert(0, '.')

from sifen_py.core.config import SifenConfig
from sifen_py.services.xml_wrapper import XMLGeneratorWrapper
from sifen_py.services.signer import XMLSigner
from sifen_py.services.soap_client import SifenSOAPClient

# ── Argumentos ────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument('--tipo',       type=int, default=1,    help='Tipo de documento (1=FE, 5=NCE, 6=NDE, 7=NRE)')
parser.add_argument('--n',          type=int, default=5,    help='Cantidad de documentos en el lote')
parser.add_argument('--incorrecto', action='store_true',    help='Generar lote con documentos inválidos (CDC duplicado)')
parser.add_argument('--protocolo',  type=str, default=None, help='Solo consultar resultado de un protocolo existente')
args = parser.parse_args()

TIPOS_NOMBRE = {1: 'Factura Electrónica', 4: 'Autofactura', 5: 'Nota de Crédito',
                6: 'Nota de Débito', 7: 'Nota de Remisión'}

# ── Config ────────────────────────────────────────────────────────────────────
with open('config.json') as f:
    cfg = json.load(f)

config = SifenConfig(
    ambiente=cfg['ambiente'],
    ruc=cfg['ruc'],
    razon_social=cfg['razon_social'],
    certificado_path=cfg['certificado_path'],
    certificado_password=cfg['certificado_password'],
    csc=cfg['csc'],
    csc_id=cfg.get('csc_id', '0001'),
    timbrado_numero=cfg['timbrado_numero'],
    timbrado_fecha=cfg['timbrado_fecha'],
    establecimiento=cfg.get('establecimiento', '001'),
    punto_expedicion=cfg.get('punto_expedicion', '001'),
    departamento=cfg.get('departamento', 1),
    distrito=cfg.get('distrito', 1),
    ciudad=cfg.get('ciudad', 1),
    actividad_economica=cfg.get('actividad_economica', ''),
    telefono=cfg.get('telefono', ''),
    email=cfg.get('email', ''),
)


def _data_fe(numero: int, incorrecto: bool = False) -> dict:
    """Datos de una Factura Electrónica de prueba."""
    codigo_seg = str(random.randint(100_000_000, 999_999_999))
    # Para incorrecto: usar número muy bajo que probablemente ya exista
    num = 1 if incorrecto else numero
    return {
        'tipoDocumento': 1,
        'establecimiento': cfg.get('establecimiento', '001'),
        'punto': cfg.get('punto_expedicion', '001'),
        'numero': num,
        'codigoSeguridadAleatorio': codigo_seg,
        'descripcion': 'DOCUMENTO ELECTRONICO SIN VALOR COMERCIAL NI FISCAL - PRUEBA LOTE DNIT',
        'fecha': datetime.now().strftime('%Y-%m-%dT%H:%M:%S'),
        'tipoEmision': 1,
        'tipoTransaccion': 1,
        'tipoImpuesto': 1,
        'moneda': 'PYG',
        'timbrado': cfg['timbrado_numero'],
        'factura': {'presencia': 1},
        'cliente': {
            'contribuyente': True,
            'ruc': cfg['ruc'],
            'razonSocial': 'CLIENTE PRUEBA LOTE DNIT',
            'tipoOperacion': 1,
            'direccion': 'Asuncion',
            'numeroCasa': '0',
            'departamento': cfg.get('departamento', 1),
            'departamentoDescripcion': 'ASUNCION',
            'distrito': cfg.get('distrito', 1),
            'distritoDescripcion': 'ASUNCION (DISTRITO)',
            'ciudad': cfg.get('ciudad', 1),
            'ciudadDescripcion': 'ASUNCION (DISTRITO)',
            'pais': 'PRY',
            'paisDescripcion': 'Paraguay',
            'tipoContribuyente': 1,
            'documentoTipo': 1,
            'documentoNumero': cfg['ruc'].split('-')[0],
            'telefono': cfg.get('telefono', ''),
            'email': cfg.get('email', ''),
        },
        'usuario': {
            'documentoTipo': 1,
            'documentoNumero': cfg['ruc'].split('-')[0],
            'nombre': cfg.get('razon_social', ''),
            'cargo': 'Sistema',
        },
        'condicion': {
            'tipo': 1,
            'entregas': [{'tipo': 1, 'monto': '110000', 'moneda': 'PYG', 'cambio': 0}],
        },
        'items': [{
            'codigo': '001',
            'descripcion': f'PRODUCTO PRUEBA LOTE {numero}',
            'cantidad': 1,
            'precioUnitario': 100000,
            'ivaTipo': 1,
            'ivaBase': 100,
            'iva': 10,
            'unidadMedida': 77,
        }],
    }


def _data_nce(numero: int, incorrecto: bool = False) -> dict:
    d = _data_fe(numero, incorrecto)
    d['tipoDocumento'] = 5
    d['notaCreditoDebito'] = {'motivo': 8}
    del d['factura']
    return d


def _data_nde(numero: int, incorrecto: bool = False) -> dict:
    d = _data_fe(numero, incorrecto)
    d['tipoDocumento'] = 6
    d['notaCreditoDebito'] = {'motivo': 8}
    del d['factura']
    return d


def _data_nre(numero: int, incorrecto: bool = False) -> dict:
    d = _data_fe(numero, incorrecto)
    d['tipoDocumento'] = 7
    d['tipoImpuesto'] = 4
    d['remision'] = {'motivo': 9}
    del d['factura']
    del d['condicion']
    return d


DATA_BUILDERS = {1: _data_fe, 5: _data_nce, 6: _data_nde, 7: _data_nre}


def consultar_protocolo(protocolo: str):
    print(f'\n{"="*60}')
    print(f'  CONSULTANDO LOTE: {protocolo}')
    print(f'{"="*60}')
    client = SifenSOAPClient(config)
    resp = client.consultar_lote_directo(protocolo)
    print(f'\n  Código:      {resp.codigo}')
    print(f'  Descripción: {resp.descripcion}')
    if resp.codigo == '0362':
        print(f'\n  {"─"*56}')
        print(f'  Resultado por documento:')
        aprobados = rechazados = 0
        for item in resp.raw.get('detalle_des', []):
            estado  = item.get('estado', '?')
            codigo  = item.get('codigo', '?')
            mensaje = item.get('mensaje', '')
            cdc     = item.get('cdc', '')
            icono   = '✓' if estado == 'Aprobado' else '✗'
            print(f'  {icono} {cdc[:20]}… | {codigo} — {mensaje}')
            if estado == 'Aprobado':
                aprobados += 1
            else:
                rechazados += 1
        print(f'\n  Aprobados: {aprobados}  |  Rechazados: {rechazados}')
    elif resp.codigo == '0361':
        print('\n  Lote aún en procesamiento. Esperá ≥10 minutos y volvé a ejecutar:')
        print(f'  python prueba_lotes_dnit.py --protocolo {protocolo}')
    elif resp.codigo == '0364':
        print('\n  Consulta extemporánea (pasaron más de 48 hs).')
    else:
        print(f'\n  raw: {resp.raw}')


def main():
    # ── Modo solo consulta ────────────────────────────────────────────────────
    if args.protocolo:
        consultar_protocolo(args.protocolo)
        return

    tipo   = args.tipo
    n      = min(args.n, 50)
    nombre = TIPOS_NOMBRE.get(tipo, f'Tipo {tipo}')
    modo   = 'INCORRECTO' if args.incorrecto else 'CORRECTO'

    if tipo not in DATA_BUILDERS:
        print(f'Tipo {tipo} no soportado en este script (soportados: 1, 5, 6, 7).')
        sys.exit(1)

    print(f'\n{"="*60}')
    print(f'  PRUEBA DE LOTE DNIT — {nombre} ({modo})')
    print(f'  Ambiente: {cfg["ambiente"]}  |  Documentos: {n}')
    print(f'{"="*60}')

    wrapper = XMLGeneratorWrapper(config)
    signer  = XMLSigner(config)
    xmls_firmados = []
    numero_base = random.randint(8000, 8900)

    for i in range(n):
        numero = numero_base + i
        print(f'\n  [Doc {i+1}/{n}] número: {numero}')
        try:
            data        = DATA_BUILDERS[tipo](numero, args.incorrecto)
            xml         = wrapper.generar_xml_de(data)
            xml_firmado = signer.firmar_xml(xml)
            xmls_firmados.append(xml_firmado)
            print(f'    ✓ XML generado y firmado ({len(xml_firmado)} chars)')
        except Exception as e:
            print(f'    ✗ Error: {e}')

    if not xmls_firmados:
        print('\nNo se pudo generar ningún XML. Verificá la configuración.')
        sys.exit(1)

    print(f'\n{"─"*60}')
    print(f'  Enviando lote con {len(xmls_firmados)} documentos...')
    client = SifenSOAPClient(config)
    try:
        resp = client.enviar_lote_directo(xmls_firmados)
    except Exception as e:
        print(f'  Error al enviar lote: {e}')
        sys.exit(1)

    print(f'  Código:    {resp.codigo}')
    print(f'  Desc:      {resp.descripcion}')
    protocolo = resp.raw.get('protocolo_lote', '')
    print(f'  Protocolo: {protocolo}')

    if resp.codigo == '0300':
        print(f'\n  *** LOTE ACEPTADO — código 0300 ***')
        print(f'\n  Esperá ≥10 minutos y consultá el resultado:')
        print(f'  python prueba_lotes_dnit.py --protocolo {protocolo}')
        # Guardar protocolo en archivo para no perderlo
        with open('ultimo_protocolo_lote.txt', 'w') as f:
            f.write(f'{protocolo}\n')
        print(f'\n  (Protocolo también guardado en ultimo_protocolo_lote.txt)')
    else:
        print(f'\n  Lote NO aceptado — raw: {resp.raw}')

    print(f'\n{"="*60}\n')


if __name__ == '__main__':
    main()
