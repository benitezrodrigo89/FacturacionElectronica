"""
Script de prueba para verificar la instalacion y conexion con SIFEN
Ejecutar desde la carpeta raiz del proyecto:
    python test_conexion.py
"""
import sys
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, 'sifen_py')

CERT_PATH = 'certificado_sifen.pfx'
CERT_PASSWORD = 'ferreteria2026.'
RUC = '5722781-0'

# Datos especificos para ambiente de PRUEBAS (Guia de Pruebas e-kuatia, seccion 2)
# El timbrado de test es el RUC sin DV con un 0 al inicio
# El CSC de test es el generico provisto por la DNIT (NO el de produccion)
CSC_TEST_ID = '0001'
CSC = 'ABCD00000000000000000000000000000'
TIMBRADO = '05722781'

print("=" * 55)
print("  TEST DE CONEXION SIFEN PARAGUAY")
print("=" * 55)

# 1. Imports
print("\n[1] Verificando dependencias...")
try:
    from sifen_py.core.config import SifenConfig
    from sifen_py.services.signer import XMLSigner
    from sifen_py.services.soap_client import SifenSOAPClient
    print("    OK - Todos los modulos cargados")
except ImportError as e:
    print(f"    ERROR - Falta instalar dependencias: {e}")
    print("    Ejecuta: pip install -r sifen_py/requirements.txt")
    sys.exit(1)

# 2. Certificado
print("\n[2] Verificando certificado...")
try:
    config = SifenConfig(
        ambiente='test',
        ruc=RUC,
        razon_social='AMARILLA ORTIZ OSVALDO MATHIAS ANTONIO',
        certificado_path=CERT_PATH,
        certificado_password=CERT_PASSWORD,
        csc=CSC,
        timbrado_numero=TIMBRADO,
    )
    print(f"    CSC test:    {CSC}")
    print(f"    Timbrado test: {TIMBRADO}")
    signer = XMLSigner(config)
    info = signer.get_certificate_info()
    print(f"    OK - Titular: {info['subject'].get('commonName')}")
    print(f"    OK - Valido hasta: {info['not_valid_after'].strftime('%d/%m/%Y')}")
except FileNotFoundError:
    print(f"    ERROR - No se encontro el certificado en: {CERT_PATH}")
    print(f"    Coloca el archivo certificado_sifen.pfx en: {__file__[:__file__.rfind(chr(92))+1] or './'}")
    sys.exit(1)
except Exception as e:
    print(f"    ERROR - {e}")
    sys.exit(1)

# 3. Conexion SIFEN
print("\n[3] Probando conexion con SIFEN test...")
try:
    import requests_pkcs12
    r = requests_pkcs12.get(
        'https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl',
        pkcs12_filename=CERT_PATH,
        pkcs12_password=CERT_PASSWORD,
        verify=False,
        timeout=15,
    )
    print(f"    HTTP Status: {r.status_code}")
    print(f"    Bytes recibidos: {len(r.content)}")
    print(f"    Headers: {dict(r.headers)}")
    if r.status_code == 200 and len(r.content) > 0:
        print(f"    OK - Servidor responde ({len(r.content)} bytes)")
        print(f"    Primeros 200 chars: {r.text[:200]}")
    elif r.status_code == 200 and len(r.content) == 0:
        print(f"    ADVERTENCIA - Servidor responde pero cuerpo vacio")
        print(f"    Esto puede indicar IP bloqueada o certificado rechazado")
    else:
        print(f"    ERROR - HTTP {r.status_code}")
        print(f"    Respuesta: {r.text[:300]}")
except Exception as e:
    print(f"    ERROR - No se pudo conectar: {type(e).__name__}: {e}")

# 3b. Prueba sin certificado (solo para comparar)
print("\n[3b] Probando sin certificado (solo conectividad)...")
try:
    import requests
    r2 = requests.get(
        'https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl',
        verify=False,
        timeout=15,
    )
    print(f"    HTTP Status sin cert: {r2.status_code} — {len(r2.content)} bytes")
except Exception as e:
    print(f"    ERROR sin cert: {type(e).__name__}: {e}")

# 4. Detalle del certificado
print("\n[4] Detalle del certificado...")
try:
    from cryptography.hazmat.primitives.serialization import pkcs12
    from cryptography.hazmat.backends import default_backend
    with open(CERT_PATH, 'rb') as f:
        pfx_data = f.read()
    _, cert, _ = pkcs12.load_key_and_certificates(pfx_data, CERT_PASSWORD.encode(), default_backend())
    print("    Subject (titular):")
    for attr in cert.subject:
        print(f"      {attr.oid._name}: {attr.value}")
    print("    Issuer (quien lo emitio):")
    for attr in cert.issuer:
        print(f"      {attr.oid._name}: {attr.value}")
    print(f"    Valido desde: {cert.not_valid_before_utc}")
    print(f"    Valido hasta: {cert.not_valid_after_utc}")
except Exception as e:
    print(f"    ERROR - {type(e).__name__}: {e}")

print("\n" + "=" * 55)
print("  Prueba completada")
print("=" * 55)
print(f"\nDatos configurados:")
print(f"  RUC:      {RUC}")
print(f"  Timbrado: {TIMBRADO}  (RUC sin DV con 0 al inicio)")
print(f"  CSC:      {CSC}  (generico DNIT para test)")
print(f"  Ambiente: TEST")
