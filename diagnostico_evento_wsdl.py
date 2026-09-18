"""
Diagnóstico del WSDL de eventos SIFEN.
Ejecutar desde la PC Paraguay (donde la IP está habilitada en SIFEN).

Uso:
    python diagnostico_evento_wsdl.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from sifen_py.core.config import SifenConfig
from sifen_py.core.constants import URLS

import json

def main():
    # Cargar config
    config_path = Path(__file__).parent / 'config.json'
    with open(config_path) as f:
        cfg = json.load(f)

    config = SifenConfig(
        ambiente=cfg['ambiente'],
        ruc=cfg['ruc'],
        razon_social=cfg['razon_social'],
        certificado_path=cfg['certificado_path'],
        certificado_password=cfg['certificado_password'],
        csc=cfg['csc'],
    )

    url_evento = URLS[config.ambiente]['recibe_evento']
    print(f"\n=== URL del servicio de eventos ===")
    print(f"  {url_evento}\n")

    # ── 1. Intentar cargar WSDL con zeep ─────────────────────────────────────
    try:
        import requests
        import requests_pkcs12
        from zeep import Client
        from zeep.transports import Transport

        session = requests.Session()
        adapter = requests_pkcs12.Pkcs12Adapter(
            pkcs12_filename=cfg['certificado_path'],
            pkcs12_password=cfg['certificado_password'],
        )
        session.mount('https://', adapter)
        transport = Transport(session=session, timeout=30)
        client = Client(url_evento, transport=transport)

        print("=== Operaciones disponibles en el WSDL de eventos ===")
        for svc in client.wsdl.services.values():
            for port in svc.ports.values():
                print(f"  Servicio: {svc.name} | Puerto: {port.name}")
                for op_name, op in port.binding._operations.items():
                    print(f"  Operación: {op_name}")
                    try:
                        body = op.input.body
                        print(f"    Body element: {body.name} | namespace: {body.type.name if hasattr(body, 'type') else 'N/A'}")
                        # Intentar listar los campos
                        if hasattr(body, 'type') and hasattr(body.type, 'elements'):
                            for elem_name, elem in body.type.elements:
                                print(f"      Campo: {elem_name} | tipo: {elem.type.name if hasattr(elem, 'type') else '?'}")
                    except Exception as e:
                        print(f"    (No se pudo inspeccionar: {e})")

    except Exception as e:
        print(f"[ERROR] No se pudo cargar el WSDL: {e}")
        return

    # ── 2. Intentar llamar al servicio con zeep para ver qué params acepta ──
    print("\n=== Intentando llamar rRecepcionEvento con dato de prueba ===")
    try:
        result = client.service.rRecepcionEvento(xEvento='<test/>')
        print(f"Respuesta: {result}")
    except Exception as e:
        print(f"Error con xEvento: {e}")

    try:
        result = client.service.rRecepcionEvento(dId='1', xEvento='<test/>')
        print(f"Respuesta dId+xEvento: {result}")
    except Exception as e:
        print(f"Error con dId+xEvento: {e}")

    # ── 3. Imprimir los tipos del servicio ────────────────────────────────────
    print("\n=== Tipos definidos en el WSDL ===")
    try:
        for ns, types in client.wsdl.types.items():
            if 'ekuatia' in str(ns):
                print(f"Namespace: {ns}")
                for t in list(types)[:20]:
                    print(f"  {t}")
    except Exception as e:
        print(f"(Error listando tipos: {e})")


if __name__ == '__main__':
    main()
