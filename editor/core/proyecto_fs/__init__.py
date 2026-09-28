"""Sincronización del modelo con el disco (nivel N3).

Uso típico:

    apertura = escaner.abrir_proyecto(ruta)          # bloqueo + diario + carga perezosa
    capitulo = apertura.proyecto.capitulo(1)         # se lee del disco al pedirlo
    resultado = reconciliador.guardar(apertura.proyecto, apertura.estado)
    apertura.cerrar()                                # libera el bloqueo
"""
