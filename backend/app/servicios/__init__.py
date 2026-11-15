"""Servicios de dominio (reglas de negocio puras).

Los servicios no conocen FastAPI, la base de datos ni las plantillas: reciben
datos, aplican las reglas colombianas y devuelven resultados tipados. Esto los
hace testeables y reutilizables por la API, las vistas y el futuro módulo POS.

Contenido actual:
- `nomina`: valor de la hora ordinaria, deducciones de ley, matriz de recargos
  y liquidación completa de un periodo (Tarea 2).
- `auxilio`: evaluación del tope de 2 SMMLV para el auxilio de transporte (Tarea 3).
- `incapacidad`: cálculo por rangos de fecha, reparto por mes y saldo arrastrado
  para el periodo siguiente (Tarea 4).
"""
