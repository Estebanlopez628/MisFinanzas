"""Reportes de soporte del módulo «Ayuda y comentarios» (SRS v2.0, Fase A).

Responsabilidad
---------------
- Registrar los reportes enviados por los usuarios con el tipo, el módulo, la
  descripción y el dispositivo detectado automáticamente.
- Exponer el conteo de pendientes, el listado completo y el cambio de estado
  para el panel administrativo.
- Mantener el catálogo cerrado de módulos **públicos**: OLB_BYTE y la facturación
  nunca aparecen en las guías ni en los selectores dirigidos al usuario estándar
  (regla de separación estricta por rol de la SRS v2.0).

La tabla `feedback_usuarios` está documentada en `diccionario_datos.md` §14.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.dependencias import UsuarioSesion
from app.modelos import FeedbackUsuario
from app.servicios import auditoria

ESTADO_PENDIENTE = "Pendiente"
ESTADOS = (ESTADO_PENDIENTE, "En revisión", "Resuelto")

# Claves internas y etiquetas literales del selector de «Envía comentarios».
TIPOS_REPORTE: tuple[tuple[str, str], ...] = (
    ("ERROR", "Reportar un error o falla técnica"),
    ("SUGERENCIA", "Sugerencia de nueva función"),
    ("CALCULO", "Problema con mis cálculos o datos"),
)

# Catálogo cerrado de módulos visibles para el usuario estándar. Se excluye
# OLB_BYTE y cualquier referencia a facturación (SRS v2.0, regla 2).
MODULOS: tuple[str, ...] = (
    "Finanzas",
    "Gastos y presupuestos",
    "Registro y Detalles de deudas",
    "Trabajos Extras",
    "Atajos de pago",
    "Otro",
)

_DISPOSITIVO_MOVIL = "Móvil"
_DISPOSITIVO_ESCRITORIO = "Escritorio"
_MARCAS_MOVILES = ("android", "iphone", "ipad", "ipod", "mobile", "windows phone")


def detectar_dispositivo(user_agent: str) -> str:
    """Deduce si la petición viene de un celular o de un escritorio.

    Se usa el ``User-Agent`` de la petición para no depender de JavaScript: el
    modal funciona igual con o sin mejora progresiva.

    Args:
        user_agent: Cabecera ``User-Agent`` del navegador; puede venir vacía.

    Returns:
        ``'Móvil'`` si el agente parece un celular o tableta; si no,
        ``'Escritorio'``.
    """
    texto = (user_agent or "").lower()
    if any(marca in texto for marca in _MARCAS_MOVILES):
        return _DISPOSITIVO_MOVIL
    return _DISPOSITIVO_ESCRITORIO


def tipos_reporte_para_ui() -> list[dict[str, str]]:
    """Entrega las opciones del selector de tipo de reporte.

    Returns:
        Lista de diccionarios con ``clave`` y ``etiqueta`` en el orden de la SRS.
    """
    return [{"clave": clave, "etiqueta": etiqueta} for clave, etiqueta in TIPOS_REPORTE]


def crear_reporte(
    bd: Session,
    usuario: UsuarioSesion,
    tipo_reporte: str,
    descripcion: str,
    modulo: str = "Otro",
    dispositivo: str = _DISPOSITIVO_ESCRITORIO,
) -> FeedbackUsuario:
    """Guarda un reporte de soporte con estado inicial «Pendiente».

    El alias y el correo se copian en el momento del envío para que el
    administrador pueda identificar al reportante aunque la cuenta cambie.

    Args:
        bd: Sesión de base de datos.
        usuario: Usuario autenticado que envía el reporte.
        tipo_reporte: Una de las claves de `TIPOS_REPORTE`.
        descripcion: Texto libre del reporte.
        modulo: Módulo público seleccionado; vacío se normaliza a «Otro».
        dispositivo: ``'Móvil'`` o ``'Escritorio'``.

    Returns:
        El reporte persistido.

    Raises:
        ValueError: Si el tipo no pertenece al catálogo, el módulo no es uno de
            los permitidos, la descripción está vacía o el dispositivo es inválido.
    """
    clave = (tipo_reporte or "").strip().upper()
    if clave not in {item[0] for item in TIPOS_REPORTE}:
        raise ValueError("Selecciona un tipo de reporte válido.")

    modulo_limpio = (modulo or "").strip() or "Otro"
    if modulo_limpio not in MODULOS:
        raise ValueError("Selecciona un módulo válido.")

    texto = (descripcion or "").strip()
    if not texto:
        raise ValueError("Escribe una descripción para enviar el reporte.")

    if dispositivo not in (_DISPOSITIVO_MOVIL, _DISPOSITIVO_ESCRITORIO):
        raise ValueError("El dispositivo no es válido.")

    reporte = FeedbackUsuario(
        id_usuario=usuario.id_usuario,
        usuario_nombre=usuario.alias[:60],
        usuario_correo=usuario.correo[:150],
        tipo_reporte=clave,
        modulo=modulo_limpio,
        descripcion=texto[:2000],
        dispositivo=dispositivo,
        estado=ESTADO_PENDIENTE,
    )
    bd.add(reporte)
    bd.commit()
    bd.refresh(reporte)
    auditoria.registrar(
        bd,
        usuario.id_usuario,
        "FEEDBACK_ENVIADO",
        "feedback_usuarios",
        f"{clave} · {modulo_limpio}",
    )
    return reporte


def contar_pendientes(bd: Session) -> int:
    """Cuenta los reportes que todavía no han sido revisados.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Número de reportes con estado «Pendiente».
    """
    return int(
        bd.scalar(
            select(func.count())
            .select_from(FeedbackUsuario)
            .where(FeedbackUsuario.estado == ESTADO_PENDIENTE)
        )
        or 0
    )


def listar_reportes(bd: Session) -> list[FeedbackUsuario]:
    """Lista todos los reportes, los más recientes primero.

    Args:
        bd: Sesión de base de datos.

    Returns:
        Lista ordenada por fecha de creación descendente.
    """
    consulta = select(FeedbackUsuario).order_by(FeedbackUsuario.fecha_creacion.desc())
    return list(bd.scalars(consulta))


def cambiar_estado(
    bd: Session, id_feedback: str, estado: str
) -> FeedbackUsuario | None:
    """Actualiza el estado de un reporte del panel administrativo.

    Args:
        bd: Sesión de base de datos.
        id_feedback: Identificador del reporte.
        estado: Uno de los valores de `ESTADOS`.

    Returns:
        El reporte actualizado, o `None` si no existe o el estado es inválido.
    """
    normal = (estado or "").strip()
    if normal not in ESTADOS:
        return None
    reporte = bd.get(FeedbackUsuario, id_feedback)
    if reporte is None:
        return None
    reporte.estado = normal
    # Solo los estados revisados llevan fecha; volver a «Pendiente» la limpia.
    reporte.fecha_resolucion = None if normal == ESTADO_PENDIENTE else datetime.now(timezone.utc)
    bd.commit()
    bd.refresh(reporte)
    return reporte


def listar_del_usuario(bd: Session, id_usuario: str) -> list[FeedbackUsuario]:
    """Lista los reportes enviados por un usuario, los más recientes primero.

    Args:
        bd: Sesión de base de datos.
        id_usuario: Dueño de los reportes.

    Returns:
        Lista ordenada por fecha de creación descendente.
    """
    consulta = (
        select(FeedbackUsuario)
        .where(FeedbackUsuario.id_usuario == id_usuario)
        .order_by(FeedbackUsuario.fecha_creacion.desc())
    )
    return list(bd.scalars(consulta))


def serialize(reporte: FeedbackUsuario) -> dict[str, object]:
    """Convierte un reporte a un diccionario seguro para la API/plantillas.

    Args:
        reporte: Reporte a serializar.

    Returns:
        Diccionario con los campos visibles y la fecha en formato ISO.
    """
    return {
        "id": reporte.id_feedback,
        "usuario": reporte.usuario_nombre,
        "correo": reporte.usuario_correo,
        "tipo_reporte": reporte.tipo_reporte,
        "modulo": reporte.modulo,
        "descripcion": reporte.descripcion,
        "dispositivo": reporte.dispositivo,
        "estado": reporte.estado,
        "fecha_creacion": reporte.fecha_creacion.isoformat(),
        "fecha_resolucion": (
            reporte.fecha_resolucion.isoformat() if reporte.fecha_resolucion else None
        ),
    }
