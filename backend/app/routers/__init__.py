"""Routers de la aplicación.

Cada módulo expone un `APIRouter` independiente para mantener el principio de
responsabilidad única:

- `vistas`: páginas HTML (login, dashboard, Mis Finanzas).
- (Fase 1) `auth`: autenticación y sesión.
- (Fase 2) `finanzas`: endpoints HTMX del motor de nómina.
- (Fase 4) `chancucos`: panel privado de referencias de pago.
"""
