"""Núcleo de la aplicación: parámetros de negocio y utilidades transversales.

Este paquete concentra las reglas parametrizables de la normativa laboral
colombiana (jornada de 210 horas, deducciones de ley, tope de auxilio de
transporte e incapacidades) y funciones auxiliares de presentación.

Regla de arquitectura (ADR-06): **ningún valor de negocio debe escribirse como
literal en los servicios o plantillas**. Todos provienen de aquí para permitir
auditoría y cambios futuros sin tocar la lógica.
"""
