"""Modelos SQLAlchemy derivados de `diccionario_datos.md`.

Responsabilidad
---------------
Traducir el modelo lógico aprobado a tablas SQLAlchemy 2.x. Cada clase conserva
el nombre de tabla, los campos y las restricciones documentadas; **ninguna tabla
se agrega aquí sin estar antes en el diccionario**.

Convenciones:
- Claves primarias ``String(32)`` con UUID hexadecimal (portable a PostgreSQL).
- Dinero en ``Numeric(14, 2)`` y porcentajes en ``Numeric(5, 2)``.
- Enumeraciones como texto con `CHECK`, para no depender del tipo nativo de un
  motor concreto.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.base_datos import Base


def nuevo_id() -> str:
    """Genera un identificador único hexadecimal de 32 caracteres.

    Returns:
        UUID v4 sin guiones, apto para una columna `VARCHAR(32)`.
    """
    return uuid.uuid4().hex


class Usuario(Base):
    """Cuenta de acceso y datos base del usuario (§1)."""

    __tablename__ = "usuarios"

    id_usuario: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    correo: Mapped[str] = mapped_column(String(150), unique=True, index=True, nullable=False)
    hash_contrasena: Mapped[str] = mapped_column(String(255), nullable=False)
    alias: Mapped[str] = mapped_column(String(60), nullable=False)
    rol: Mapped[str] = mapped_column(String(20), nullable=False, index=True, default="USER_FINANZAS")
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PerfilFinanciero(Base):
    """Configuración salarial del usuario, uno a uno (§2)."""

    __tablename__ = "perfiles_financieros"
    __table_args__ = (
        UniqueConstraint("id_usuario", name="uq_perfil_usuario"),
        CheckConstraint("sueldo_basico >= 0", name="ck_perfil_sueldo"),
        CheckConstraint(
            "porcentaje_quincena_1 IS NULL OR porcentaje_quincena_1 > 0",
            name="ck_perfil_pct_quincena_1",
        ),
        CheckConstraint(
            "porcentaje_quincena_2 IS NULL OR porcentaje_quincena_2 > 0",
            name="ck_perfil_pct_quincena_2",
        ),
        CheckConstraint(
            "quincena_deducciones IS NULL OR quincena_deducciones IN (1, 2)",
            name="ck_perfil_quincena_deducciones",
        ),
    )

    id_perfil: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    id_usuario: Mapped[str] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="CASCADE"), nullable=False
    )
    sueldo_basico: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    modalidad_pago: Mapped[str] = mapped_column(String(20), nullable=False, default="MENSUAL")
    # Porcentajes independientes por quincena: el usuario puede recibir montos
    # distintos en la Q1 y la Q2, y las deducciones de ley se aplican solo a la
    # quincena marcada en `quincena_deducciones`.
    porcentaje_quincena_1: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    porcentaje_quincena_2: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    quincena_deducciones: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    auxilio_transporte_habilitado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class PeriodoNomina(Base):
    """Encabezado de una liquidación de nómina (§3)."""

    __tablename__ = "periodos_nomina"
    __table_args__ = (
        UniqueConstraint("id_usuario", "anio", "mes", "quincena", name="uq_periodo_usuario"),
        CheckConstraint("mes BETWEEN 1 AND 12", name="ck_periodo_mes"),
        CheckConstraint("quincena BETWEEN 0 AND 2", name="ck_periodo_quincena"),
    )

    id_periodo: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    id_usuario: Mapped[str] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="CASCADE"), nullable=False, index=True
    )
    anio: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    mes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    quincena: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    sueldo_basico_periodo: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    valor_hora_ordinaria: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    total_horas_extra: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0)
    total_recargos: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    deduccion_salud: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    deduccion_pension: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    auxilio_transporte: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    deduccion_incapacidad: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total_gastos: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    total_devengado: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_deducciones: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    saldo_bolsillo: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="BORRADOR")
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fecha_actualizacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class RegistroHorasExtra(Base):
    """Detalle de horas extras y recargos de un periodo (§4)."""

    __tablename__ = "registros_horas_extra"
    __table_args__ = (CheckConstraint("cantidad_horas >= 0", name="ck_horas_cantidad"),)

    id_registro: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    id_periodo: Mapped[str] = mapped_column(
        ForeignKey("periodos_nomina.id_periodo", ondelete="CASCADE"), nullable=False, index=True
    )
    tipo_hora: Mapped[str] = mapped_column(String(40), nullable=False)
    cantidad_horas: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    factor_aplicado: Mapped[Decimal] = mapped_column(Numeric(4, 2), nullable=False)
    valor_hora_base: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    valor_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class Incapacidad(Base):
    """Incapacidad registrada por rango de fechas (§5)."""

    __tablename__ = "incapacidades"
    __table_args__ = (
        CheckConstraint("fecha_fin >= fecha_inicio", name="ck_incapacidad_fechas"),
    )

    id_incapacidad: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    id_usuario: Mapped[str] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="CASCADE"), nullable=False, index=True
    )
    numero_incapacidad: Mapped[str | None] = mapped_column(String(40), nullable=True)
    origen: Mapped[str] = mapped_column(String(20), nullable=False, default="COMUN")
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    dias_totales: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    dias_mes_actual: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    dias_arrastrados: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    porcentaje_pago: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    valor_descontado: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="REGISTRADA")
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SaldoIncapacidad(Base):
    """Saldo de incapacidad pendiente de aplicar (§6)."""

    __tablename__ = "saldos_incapacidad"
    __table_args__ = (
        UniqueConstraint("id_incapacidad_origen", "anio", "mes", name="uq_saldo_origen_mes"),
        CheckConstraint("dias_pendientes >= 0", name="ck_saldo_dias"),
    )

    id_saldo: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    id_usuario: Mapped[str] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="CASCADE"), nullable=False, index=True
    )
    id_incapacidad_origen: Mapped[str] = mapped_column(
        ForeignKey("incapacidades.id_incapacidad", ondelete="CASCADE"), nullable=False
    )
    anio: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    mes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    dias_pendientes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    valor_pendiente: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    aplicado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    id_periodo_aplicado: Mapped[str | None] = mapped_column(
        ForeignKey("periodos_nomina.id_periodo", ondelete="SET NULL"), nullable=True
    )


class Gasto(Base):
    """Gasto fijo o variable del usuario (§7).

    `quincena` indica a qué pago pertenece el gasto fijo: `None` (mes completo),
    `1` (día 15) o `2` (día 30). Es la base del saldo libre por quincena del
    layout de "Mis Finanzas" (SRS v1.2, bloque 3).
    """

    __tablename__ = "gastos"
    __table_args__ = (
        CheckConstraint("valor >= 0", name="ck_gasto_valor"),
        CheckConstraint(
            "quincena IS NULL OR quincena IN (1, 2)", name="ck_gasto_quincena"
        ),
    )

    id_gasto: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    id_usuario: Mapped[str] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="CASCADE"), nullable=False, index=True
    )
    id_periodo: Mapped[str | None] = mapped_column(
        ForeignKey("periodos_nomina.id_periodo", ondelete="SET NULL"), nullable=True
    )
    categoria: Mapped[str] = mapped_column(String(60), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(150), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    es_fijo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    quincena: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)


class Deuda(Base):
    """Pasivo del usuario (§8)."""

    __tablename__ = "deudas"

    id_deuda: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    id_usuario: Mapped[str] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="CASCADE"), nullable=False, index=True
    )
    acreedor: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(150), nullable=True)
    saldo_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cuota_mensual: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    tasa_interes: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    fecha_limite: Mapped[date | None] = mapped_column(Date, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVA")


class Chancuco(Base):
    """Atajo de pago rápido (§9).

    La SRS v1.3 reduce el registro a tres datos visibles: descripción, número de
    referencia y enlace de pago. Los antiguos `entidad` y `tipo_servicio` se
    fusionaron en `descripcion`; la migración de `core/base_datos.py` reconstruye
    la tabla y elimina la columna `tipo_servicio`.
    """

    __tablename__ = "chancucos"

    id_chancuco: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    id_usuario: Mapped[str] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="CASCADE"), nullable=False, index=True
    )
    descripcion: Mapped[str] = mapped_column(String(120), nullable=False)
    numero_referencia: Mapped[str] = mapped_column(String(60), nullable=False)
    url_pago: Mapped[str | None] = mapped_column(String(300), nullable=True)
    favorito: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class ProyeccionAhorro(Base):
    """Meta de ahorro o gasto programado (§9.1, SRS v1.3).

    La cuota se descuenta de la quincena elegida. `tipo_duracion` distingue un
    gasto fijo indefinido (`FIJO`) de una meta con número de cuotas
    (`LIMITADO`), caso en el que `meses` define el total acumulado proyectado.
    """

    __tablename__ = "proyecciones_ahorro"
    __table_args__ = (
        CheckConstraint("valor_mensual >= 0", name="ck_proyeccion_valor"),
        CheckConstraint("quincena IN (1, 2)", name="ck_proyeccion_quincena"),
        CheckConstraint(
            "tipo_duracion IN ('FIJO', 'LIMITADO')", name="ck_proyeccion_duracion"
        ),
    )

    id_proyeccion: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=nuevo_id
    )
    id_usuario: Mapped[str] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="CASCADE"), nullable=False, index=True
    )
    categoria: Mapped[str] = mapped_column(String(60), nullable=False)
    descripcion: Mapped[str] = mapped_column(String(150), nullable=False)
    valor_mensual: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    tipo_duracion: Mapped[str] = mapped_column(String(20), nullable=False, default="FIJO")
    meses: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    quincena: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AbonoProyeccion(Base):
    """Cuota mensual abonada a una meta de ahorro (§9.2).

    Solo se admite un abono por meta y mes; registrar de nuevo el mismo mes
    actualiza el monto en lugar de crear otra fila.
    """

    __tablename__ = "abonos_proyeccion"
    __table_args__ = (
        UniqueConstraint("id_proyeccion", "anio", "mes", name="uq_abono_proyeccion_mes"),
        CheckConstraint("valor >= 0", name="ck_abono_proyeccion_valor"),
    )

    id_abono: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    id_proyeccion: Mapped[str] = mapped_column(
        ForeignKey("proyecciones_ahorro.id_proyeccion", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    anio: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    mes: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DeduccionFija(Base):
    """Descuento fijo que la empresa aplica por nómina (§9.3, SRS v1.4).

    Se resta de la quincena indicada antes de calcular el saldo libre del
    usuario. No altera el cálculo de salud y pensión.
    """

    __tablename__ = "deducciones_fijas"
    __table_args__ = (
        CheckConstraint("valor >= 0", name="ck_deduccion_fija_valor"),
        CheckConstraint("quincena IN (1, 2)", name="ck_deduccion_fija_quincena"),
    )

    id_deduccion: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    id_usuario: Mapped[str] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="CASCADE"), nullable=False, index=True
    )
    descripcion: Mapped[str] = mapped_column(String(150), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    quincena: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    fecha_creacion: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Cliente(Base):
    """Cliente de OLB_BYTE (§10.1)."""

    __tablename__ = "clientes"

    id_cliente: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    telefono_whatsapp: Mapped[str | None] = mapped_column(String(20), nullable=True)
    correo: Mapped[str | None] = mapped_column(String(150), nullable=True)
    direccion: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fecha_registro: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Producto(Base):
    """Producto del inventario de OLB_BYTE (§10.2)."""

    __tablename__ = "productos"
    __table_args__ = (
        UniqueConstraint("sku", name="uq_producto_sku"),
        CheckConstraint("stock >= 0", name="ck_producto_stock"),
    )

    id_producto: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    sku: Mapped[str] = mapped_column(String(40), nullable=False)
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    costo: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    precio_venta: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    garantia_meses: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)


class Venta(Base):
    """Venta de OLB_BYTE (§10.3)."""

    __tablename__ = "ventas"

    id_venta: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    id_cliente: Mapped[str] = mapped_column(
        ForeignKey("clientes.id_cliente", ondelete="RESTRICT"), nullable=False, index=True
    )
    fecha_venta: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    saldo_pendiente: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDIENTE")


class VentaDetalle(Base):
    """Línea de detalle de una venta (§10.4)."""

    __tablename__ = "venta_detalle"
    __table_args__ = (CheckConstraint("cantidad > 0", name="ck_detalle_cantidad"),)

    id_detalle: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    id_venta: Mapped[str] = mapped_column(
        ForeignKey("ventas.id_venta", ondelete="CASCADE"), nullable=False, index=True
    )
    id_producto: Mapped[str] = mapped_column(
        ForeignKey("productos.id_producto", ondelete="RESTRICT"), nullable=False
    )
    cantidad: Mapped[int] = mapped_column(Integer, nullable=False)
    precio_unitario: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class Abono(Base):
    """Abono a una venta (§10.5)."""

    __tablename__ = "abonos"
    __table_args__ = (CheckConstraint("monto > 0", name="ck_abono_monto"),)

    id_abono: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    id_venta: Mapped[str] = mapped_column(
        ForeignKey("ventas.id_venta", ondelete="CASCADE"), nullable=False, index=True
    )
    monto: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    metodo_pago: Mapped[str] = mapped_column(String(30), nullable=False, default="EFECTIVO")
    fecha_abono: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TrabajoExtra(Base):
    """Ingreso independiente registrado por el usuario (§12)."""

    __tablename__ = "trabajos_extras"
    __table_args__ = (CheckConstraint("valor >= 0", name="ck_trabajo_valor"),)

    id_trabajo: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    id_usuario: Mapped[str] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="CASCADE"), nullable=False, index=True
    )
    descripcion: Mapped[str] = mapped_column(String(150), nullable=False)
    cliente: Mapped[str | None] = mapped_column(String(100), nullable=True)
    valor: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDIENTE")


class Auditoria(Base):
    """Registro de acciones sensibles para trazabilidad (§13)."""

    __tablename__ = "auditoria"

    id_evento: Mapped[str] = mapped_column(String(32), primary_key=True, default=nuevo_id)
    id_usuario: Mapped[str | None] = mapped_column(
        ForeignKey("usuarios.id_usuario", ondelete="SET NULL"), nullable=True, index=True
    )
    accion: Mapped[str] = mapped_column(String(40), nullable=False)
    entidad: Mapped[str | None] = mapped_column(String(40), nullable=True)
    detalle: Mapped[str | None] = mapped_column(String(300), nullable=True)
    fecha: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
