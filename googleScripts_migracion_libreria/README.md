# Migracion de prueba a libreria Apps Script

Esta carpeta prepara una prueba completa de la arquitectura con libreria.

No reemplaza `googleScripts` ni modifica la planilla por si sola. Es material
para copiar/pegar en Apps Script.

## Carpetas

- `library_src/`: archivos `.gs` para pegar en el proyecto independiente
  `EtiquetadorZPL_Library`.
- `bridge_src/`: archivo minimo para dejar en el Apps Script vinculado a la
  planilla de prueba.

## Como probar

1. En el proyecto `EtiquetadorZPL_Library`, borrar el `Code.gs` de prueba o
   dejarlo si solo contiene `ping`.
2. Crear en ese proyecto los archivos de `library_src/` y pegar el contenido de
   cada uno.
3. Guardar.
4. Crear una version nueva de la libreria.
5. En la planilla de prueba, actualizar la libreria `EtiquetadorZPL` a esa
   nueva version.
6. En el Apps Script vinculado a la planilla de prueba, NO hacerlo todavia en la
   planilla real:
   - crear backup del codigo actual;
   - dejar solo el contenido de `bridge_src/00_bridge.gs`;
   - mantener agregada la libreria con identificador exacto `EtiquetadorZPL`.
7. Guardar.
8. Recargar la planilla.
9. Probar en este orden:
   - abrir menu `Neo`;
   - ejecutar una funcion liviana, por ejemplo `testSheetAccess`;
   - abrir `NeoCalculo`;
   - abrir algun sidebar de etiquetas;
   - recien despues probar sincronizaciones Odoo.

## Si falla

Errores habituales:

- `EtiquetadorZPL is not defined`: la libreria no esta agregada o el
  identificador no es exacto.
- `EtiquetadorZPL.nombreFuncion is not a function`: falta publicar una version
  nueva de la libreria o falta esa funcion en `library_src`.
- Error desde un sidebar con `google.script.run`: falta wrapper local en
  `bridge_src/00_bridge.gs`.

Rollback:

1. Volver al Apps Script vinculado a la planilla de prueba.
2. Restaurar el codigo completo anterior desde `googleScripts`.
3. Guardar y recargar la planilla.

## Nota sobre triggers

Los triggers instalables deben apuntar a funciones locales del proyecto de la
planilla. Por eso el bridge incluye wrappers como:

- `syncOdooSalesOrdersNeo`
- `syncOdooManufacturingOrders`
- `crearEnlaceAlEditar`
- `notificarVentaNeoFinalizadaAlEditar`
- `runDailySalesHiddenMetadataRepair`

La implementacion real queda en la libreria.
