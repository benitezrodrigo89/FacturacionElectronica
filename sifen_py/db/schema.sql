-- Esquema de base de datos para SIFEN Paraguay
-- Ejecutar una sola vez: psql -U postgres -d sifen_py -f schema.sql

CREATE TABLE IF NOT EXISTS documentos_electronicos (
    id                      SERIAL PRIMARY KEY,
    cdc                     VARCHAR(44) UNIQUE NOT NULL,
    numero_doc              INTEGER NOT NULL,
    establecimiento         VARCHAR(3) NOT NULL DEFAULT '001',
    punto_expedicion        VARCHAR(3) NOT NULL DEFAULT '001',
    tipo_documento          INTEGER NOT NULL DEFAULT 1,  -- 1=Factura
    fecha_emision           TIMESTAMPTZ,
    ruc_receptor            VARCHAR(20),
    razon_social_receptor   VARCHAR(255),
    monto_total             BIGINT,                      -- en guaraníes

    -- Documento
    xml_firmado             TEXT NOT NULL,               -- rDE firmado completo
    soap_envelope           TEXT,                        -- envelope enviado a SIFEN
    data_json               TEXT,                        -- datos originales del documento (JSON)

    -- Estado SIFEN
    estado                  VARCHAR(20) NOT NULL DEFAULT 'pendiente',
    -- 'pendiente' | 'aprobado' | 'rechazado' | 'duplicado' | 'error'
    codigo_sifen            VARCHAR(10),                 -- ej: 0260, 1001, 0160
    descripcion_sifen       TEXT,                        -- mensaje de SIFEN
    protocolo_autorizacion  VARCHAR(50),                 -- dProtAut (solo si aprobado)
    respuesta_xml           TEXT,                        -- XML completo de respuesta

    -- Control
    intentos                INTEGER NOT NULL DEFAULT 1,
    fecha_envio             TIMESTAMPTZ,
    fecha_respuesta         TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índices útiles para consultas frecuentes
CREATE INDEX IF NOT EXISTS idx_de_estado     ON documentos_electronicos (estado);
CREATE INDEX IF NOT EXISTS idx_de_numero_doc ON documentos_electronicos (numero_doc);
CREATE INDEX IF NOT EXISTS idx_de_fecha      ON documentos_electronicos (fecha_emision);
CREATE INDEX IF NOT EXISTS idx_de_ruc_rec    ON documentos_electronicos (ruc_receptor);

-- Trigger para actualizar updated_at automáticamente
CREATE OR REPLACE FUNCTION actualizar_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trig_de_updated_at ON documentos_electronicos;
CREATE TRIGGER trig_de_updated_at
    BEFORE UPDATE ON documentos_electronicos
    FOR EACH ROW EXECUTE FUNCTION actualizar_updated_at();

-- ─────────────────────────────────────────────────────────────
-- Clientes frecuentes (solo para uso de la webapp)
-- La API no valida contra esta tabla.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clientes (
    id              SERIAL PRIMARY KEY,
    ruc             VARCHAR(20) NOT NULL,
    razon_social    VARCHAR(255) NOT NULL,
    direccion       VARCHAR(255),
    telefono        VARCHAR(50),
    email           VARCHAR(100),
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_clientes_ruc ON clientes (ruc) WHERE activo = TRUE;
CREATE INDEX IF NOT EXISTS idx_clientes_razon ON clientes (razon_social);

DROP TRIGGER IF EXISTS trig_clientes_updated_at ON clientes;
CREATE TRIGGER trig_clientes_updated_at
    BEFORE UPDATE ON clientes
    FOR EACH ROW EXECUTE FUNCTION actualizar_updated_at();

-- ─────────────────────────────────────────────────────────────
-- Productos / Servicios frecuentes (solo para uso de la webapp)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS productos (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(50),
    descripcion     VARCHAR(255) NOT NULL,
    precio_unitario INTEGER NOT NULL DEFAULT 0,  -- en guaraníes
    unidad_medida   INTEGER NOT NULL DEFAULT 77, -- código SIFEN (77=Unidad)
    iva             INTEGER NOT NULL DEFAULT 10  CHECK (iva IN (0, 5, 10)),
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_productos_descripcion ON productos (descripcion);
CREATE INDEX IF NOT EXISTS idx_productos_codigo      ON productos (codigo);

DROP TRIGGER IF EXISTS trig_productos_updated_at ON productos;
CREATE TRIGGER trig_productos_updated_at
    BEFORE UPDATE ON productos
    FOR EACH ROW EXECUTE FUNCTION actualizar_updated_at();
