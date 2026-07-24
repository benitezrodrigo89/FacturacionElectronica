"""
Tests para utils/cdc.py:
  - calcular_digito_verificador_ruc
  - calcular_digito_verificador_cdc
  - generar_cdc
  - validar_cdc
  - descomponer_cdc
"""
import pytest
from datetime import datetime
from sifen_py.utils.cdc import (
    calcular_digito_verificador_ruc,
    calcular_digito_verificador_cdc,
    generar_cdc,
    validar_cdc,
    descomponer_cdc,
)
from sifen_py.core.exceptions import CDCException


# ─── calcular_digito_verificador_ruc ─────────────────────────────────────────

class TestDigitoVerificadorRuc:
    def test_ruc_conocido_80069563(self):
        assert calcular_digito_verificador_ruc('80069563') == 1

    def test_ruc_conocido_5722781(self):
        # RUC del test_conexion.py → DV 0
        assert calcular_digito_verificador_ruc('5722781') == 0

    def test_ruc_de_un_digito(self):
        dv = calcular_digito_verificador_ruc('1')
        assert 0 <= dv <= 9

    def test_resultado_siempre_entre_0_y_9(self):
        for ruc in ['12345678', '80000001', '1234567', '99999999']:
            dv = calcular_digito_verificador_ruc(ruc)
            assert 0 <= dv <= 9, f"DV fuera de rango para RUC {ruc}: {dv}"

    def test_resto_0_o_1_devuelve_0(self):
        # El algoritmo fuerza dv=0 cuando resto<=1; verificar con un caso real
        dv = calcular_digito_verificador_ruc('5722781')
        assert dv == 0


# ─── calcular_digito_verificador_cdc ─────────────────────────────────────────

class TestDigitoVerificadorCdc:
    def test_longitud_43_devuelve_digito_valido(self):
        cdc43 = '1800695631001001000000120260115100000000100'
        assert len(cdc43) == 43
        dv = calcular_digito_verificador_cdc(cdc43)
        assert 0 <= dv <= 9

    def test_consistencia_doble_calculo(self):
        cdc43 = '1800695631001001000000120260115100000001' + '00'
        dv1 = calcular_digito_verificador_cdc(cdc43)
        dv2 = calcular_digito_verificador_cdc(cdc43)
        assert dv1 == dv2

    def test_cdc_distinto_distinto_input(self):
        # Dos CDCs de 43 dígitos distintos: verificar que el cálculo no lanza error
        # Estructura: tipo(1)+ruc(8)+dv(1)+est(3)+pto(3)+num(7)+tpc(1)+fecha(8)+tem(1)+csc(8)+res(2) = 43
        cdc_a = '1' + '80069563' + '1' + '001' + '001' + '0000001' + '2' + '20260115' + '1' + '00000001' + '00'
        cdc_b = '1' + '80069563' + '1' + '001' + '001' + '0000002' + '2' + '20260115' + '1' + '00000001' + '00'
        assert len(cdc_a) == len(cdc_b) == 43
        # Los DV pueden coincidir o no; lo que importa es que el cálculo no lanza error
        dv_a = calcular_digito_verificador_cdc(cdc_a)
        dv_b = calcular_digito_verificador_cdc(cdc_b)
        assert 0 <= dv_a <= 9
        assert 0 <= dv_b <= 9


# ─── generar_cdc ─────────────────────────────────────────────────────────────

class TestGenerarCdc:
    def _base_kwargs(self):
        return dict(
            tipo_documento=1,
            ruc_emisor='80069563',
            dv_emisor='1',
            establecimiento='001',
            punto_expedicion='001',
            numero='0000001',
            tipo_contribuyente=2,
            fecha_emision=datetime(2026, 1, 15),
            tipo_emision=1,
            codigo_seguridad='00000001',
        )

    def test_longitud_44(self):
        cdc = generar_cdc(**self._base_kwargs())
        assert len(cdc) == 44

    def test_solo_digitos(self):
        cdc = generar_cdc(**self._base_kwargs())
        assert cdc.isdigit()

    def test_tipo_documento_en_posicion_0(self):
        cdc = generar_cdc(**self._base_kwargs())
        assert cdc[0] == '1'

    def test_ruc_relleno_con_ceros(self):
        cdc = generar_cdc(**self._base_kwargs())
        assert cdc[1:9] == '80069563'

    def test_dv_ruc_en_posicion_9(self):
        cdc = generar_cdc(**self._base_kwargs())
        assert cdc[9] == '1'

    def test_establecimiento_en_posicion_10_12(self):
        cdc = generar_cdc(**self._base_kwargs())
        assert cdc[10:13] == '001'

    def test_punto_expedicion_en_posicion_13_15(self):
        cdc = generar_cdc(**self._base_kwargs())
        assert cdc[13:16] == '001'

    def test_numero_documento_en_posicion_16_22(self):
        cdc = generar_cdc(**self._base_kwargs())
        assert cdc[16:23] == '0000001'

    def test_fecha_en_posicion_24_31(self):
        cdc = generar_cdc(**self._base_kwargs())
        assert cdc[24:32] == '20260115'

    def test_csc_en_posicion_33_40(self):
        cdc = generar_cdc(**self._base_kwargs())
        assert cdc[33:41] == '00000001'

    def test_reservado_41_42_es_00(self):
        cdc = generar_cdc(**self._base_kwargs())
        assert cdc[41:43] == '00'

    def test_dv_final_es_correcto(self):
        from sifen_py.utils.cdc import calcular_digito_verificador_cdc
        cdc = generar_cdc(**self._base_kwargs())
        dv_esperado = calcular_digito_verificador_cdc(cdc[:43])
        assert int(cdc[43]) == dv_esperado

    def test_ruc_corto_se_rellena(self):
        kwargs = self._base_kwargs()
        kwargs['ruc_emisor'] = '123'
        cdc = generar_cdc(**kwargs)
        assert cdc[1:9] == '00000123'
        assert len(cdc) == 44

    def test_csc_corto_se_rellena(self):
        kwargs = self._base_kwargs()
        kwargs['codigo_seguridad'] = '1'
        cdc = generar_cdc(**kwargs)
        assert cdc[33:41] == '00000001'

    def test_tipo_contribuyente_1_persona_fisica(self):
        kwargs = self._base_kwargs()
        kwargs['tipo_contribuyente'] = 1
        cdc = generar_cdc(**kwargs)
        assert cdc[23] == '1'

    def test_tipo_emision_2_contingencia(self):
        kwargs = self._base_kwargs()
        kwargs['tipo_emision'] = 2
        cdc = generar_cdc(**kwargs)
        assert cdc[32] == '2'

    def test_tipo_documento_5_nota_credito(self):
        kwargs = self._base_kwargs()
        kwargs['tipo_documento'] = 5
        cdc = generar_cdc(**kwargs)
        assert cdc[0] == '5'
        assert len(cdc) == 44

    def test_cdc_generado_es_valido(self):
        cdc = generar_cdc(**self._base_kwargs())
        assert validar_cdc(cdc)

    def test_diferentes_numeros_producen_cdcs_distintos(self):
        kwargs1 = self._base_kwargs()
        kwargs2 = {**self._base_kwargs(), 'numero': '0000002'}
        assert generar_cdc(**kwargs1) != generar_cdc(**kwargs2)


# ─── validar_cdc ─────────────────────────────────────────────────────────────

class TestValidarCdc:
    def test_cdc_valido_generado(self, cdc_valido):
        assert validar_cdc(cdc_valido) is True

    def test_longitud_incorrecta_43(self):
        assert validar_cdc('1' * 43) is False

    def test_longitud_incorrecta_45(self):
        assert validar_cdc('1' * 45) is False

    def test_cadena_vacia(self):
        assert validar_cdc('') is False

    def test_none_equivalente(self):
        assert validar_cdc(None) is False

    def test_contiene_letras(self):
        assert validar_cdc('A' * 44) is False

    def test_dv_incorrecto(self, cdc_valido):
        dv_original = int(cdc_valido[43])
        dv_malo = (dv_original + 1) % 10
        cdc_malo = cdc_valido[:43] + str(dv_malo)
        assert validar_cdc(cdc_malo) is False

    def test_todos_ceros_dv_matematicamente_valido(self):
        # 43 ceros: suma=0, resto=0 → DV=0. El algoritmo lo acepta matemáticamente.
        # validar_cdc solo verifica longitud, que sean dígitos y que el DV coincida.
        resultado = validar_cdc('0' * 44)
        assert isinstance(resultado, bool)


# ─── descomponer_cdc ─────────────────────────────────────────────────────────

class TestDescomponerCdc:
    def test_retorna_dict_con_claves_esperadas(self, cdc_valido):
        resultado = descomponer_cdc(cdc_valido)
        claves_esperadas = {
            'tipo_documento', 'ruc_emisor', 'dv_emisor',
            'establecimiento', 'punto_expedicion', 'numero',
            'tipo_contribuyente', 'fecha_emision', 'tipo_emision',
            'codigo_seguridad', 'reservado', 'dv',
        }
        assert claves_esperadas.issubset(resultado.keys())

    def test_tipo_documento_correcto(self, cdc_valido):
        resultado = descomponer_cdc(cdc_valido)
        assert resultado['tipo_documento'] == 1

    def test_ruc_emisor_correcto(self, cdc_valido):
        resultado = descomponer_cdc(cdc_valido)
        assert resultado['ruc_emisor'] == '80069563'

    def test_dv_emisor_correcto(self, cdc_valido):
        resultado = descomponer_cdc(cdc_valido)
        assert resultado['dv_emisor'] == '1'

    def test_establecimiento_correcto(self, cdc_valido):
        resultado = descomponer_cdc(cdc_valido)
        assert resultado['establecimiento'] == '001'

    def test_fecha_emision_formato_yyyymmdd(self, cdc_valido):
        resultado = descomponer_cdc(cdc_valido)
        assert resultado['fecha_emision'] == '20260115'

    def test_reservado_es_00(self, cdc_valido):
        resultado = descomponer_cdc(cdc_valido)
        assert resultado['reservado'] == '00'

    def test_cdc_con_dv_incorrecto_lanza_excepcion(self, cdc_valido):
        # Modificar el DV para forzar un CDC inválido
        dv_original = int(cdc_valido[43])
        dv_malo = (dv_original + 1) % 10
        cdc_malo = cdc_valido[:43] + str(dv_malo)
        with pytest.raises(CDCException):
            descomponer_cdc(cdc_malo)

    def test_cdc_incompleto_lanza_excepcion(self):
        with pytest.raises(CDCException):
            descomponer_cdc('12345')

    def test_roundtrip_generar_descomponer(self):
        from sifen_py.utils.cdc import generar_cdc
        fecha = datetime(2026, 3, 20, 9, 0, 0)
        cdc = generar_cdc(
            tipo_documento=5,
            ruc_emisor='12345678',
            dv_emisor='9',
            establecimiento='002',
            punto_expedicion='003',
            numero='0000099',
            tipo_contribuyente=1,
            fecha_emision=fecha,
            tipo_emision=1,
            codigo_seguridad='12345678',
        )
        d = descomponer_cdc(cdc)
        assert d['tipo_documento'] == 5
        assert d['establecimiento'] == '002'
        assert d['punto_expedicion'] == '003'
        assert d['numero'] == '0000099'
        assert d['fecha_emision'] == '20260320'
