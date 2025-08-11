# 📋 Manual de Usuario - EtiquetadorZPL

## 🚀 Inicio Rápido

### Opción 1: Launcher Principal
```bash
python quick_start.py
```

**Opciones disponibles:**
1. **API solamente** - Solo servidor web
2. **Servicio completo** - API + Monitoreo de archivos
3. **GUI solamente** - Interfaz gráfica
4. **TODO** - API + Monitoreo + GUI (Recomendado)

### Opción 2: Componentes Individuales
```bash
# Solo API
python api/fast_api.py

# Solo GUI
python gui/main_gui_optimized_fixed.py

# Solo servicio
python api/simple_service.py
```

## 🌐 Acceso Web

### Dashboard Local
- **URL**: `http://localhost:8002/web/`
- **Login**: `admin / admin123`

### Acceso desde Red
- **URL**: `http://192.168.1.8:8002/web/`
- **Configurar**: Cambiar IP por la de tu equipo

## ⚙️ Configuración

### 1. Configuración de Carpetas (GUI)

**Pasos:**
1. Abrir GUI con `python quick_start.py` → Opción 4
2. Configurar hasta 3 carpetas simultáneas:
   - **Carpeta**: Directorio a monitorear
   - **Impresora**: Impresora de destino
   - **Historial**: Carpeta para archivos procesados
   - **Activa**: Habilitar/deshabilitar monitoreo
   - **Recortar PDF**: Recorte automático
   - **Copias**: Cantidad (1-10)

**Ejemplo de configuración:**
```
Carpeta 1:
✓ Activa
✓ Recortar PDF automáticamente
Carpeta: C:\EtiquetasFlex\Entrada1
Impresora: Zebra ZT230
Historial: C:\EtiquetasFlex\Historial1
Copias: 1

Carpeta 2:
✓ Activa
Carpeta: C:\EtiquetasFlex\Entrada2  
Impresora: Godex GE300
Historial: C:\EtiquetasFlex\Historial2
Copias: 2
```

### 2. Configuración Manual (config.ini)

**Ubicación**: `config/config.ini`

```ini
[CARPETA1]
entrada = C:\EtiquetasFlex\Entrada1
impresora = Zebra ZT230
historial = C:\EtiquetasFlex\Historial1
activa = True
recortar_pdf = True
copias = 1

[CARPETA2]
entrada = C:\EtiquetasFlex\Entrada2
impresora = Godex GE300
historial = C:\EtiquetasFlex\Historial2
activa = True
recortar_pdf = False
copias = 2
```

## 📁 Uso del Sistema

### 1. Procesamiento Automático

**Archivos soportados:**
- **PDF** - Se convierte a ZPL automáticamente
- **ZPL** - Se envía directamente a impresora
- **TXT** - Archivos de texto con código ZPL
- **ZIP** - Contiene múltiples archivos ZPL/TXT

**Flujo de trabajo:**
1. Colocar archivo en carpeta monitoreada
2. Sistema detecta archivo automáticamente
3. Procesa según tipo:
   - PDF → Convierte a ZPL → Envía a impresora
   - ZPL/TXT → Envía directamente a impresora
4. Mueve archivo a carpeta historial
5. Registra actividad en log

### 2. Monitoreo en Tiempo Real

**Estados del sistema:**
- ⏸️ **Detenido** - No hay monitoreo activo
- ▶️ **Monitoreando X carpeta(s)** - Sistema activo
- 🔄 **Procesando** - Archivo en proceso

**Log de actividad:**
- ✅ Trabajos completados exitosamente
- ❌ Errores de procesamiento
- 📁 Carpetas siendo monitoreadas
- 🖨️ Trabajos enviados a impresora

## 🌐 Dashboard Web

### Funciones Principales

**1. Vista General**
- Estadísticas de trabajos
- Estado del sistema
- Trabajos recientes
- Gráficos de rendimiento

**2. Gestión de Trabajos**
- Lista de todos los trabajos
- Filtros por estado/fecha
- Detalles de cada trabajo
- Reenvío de trabajos fallidos

**3. Configuración**
- Configuración de notificaciones
- Gestión de backups
- Configuración de red
- Herramientas del sistema

**4. Monitoreo**
- Métricas del sistema en tiempo real
- Uso de CPU/RAM/Disco
- Alertas automáticas
- Logs del sistema

### Acceso Remoto

**Para acceder desde otros PCs:**
1. Obtener IP del servidor: `ipconfig`
2. Abrir navegador en PC remoto
3. Ir a: `http://IP_SERVIDOR:8002/web/`
4. Login: `admin / admin123`

## 🔔 Notificaciones

### Configuración

**Tipos de notificaciones:**
- **Notificaciones de escritorio** - Ventanas emergentes Windows
- **Notificar errores** - Alertas cuando fallan trabajos
- **Notificar éxitos** - Confirmación de trabajos completados

**Configurar desde:**
- Dashboard web → Configuración → Notificaciones
- GUI → Configuración (si disponible)

### Ejemplos de Notificaciones

**Trabajo exitoso:**
```
✅ Impresión Exitosa
Archivo: etiqueta_001.pdf
Impresora: Zebra ZT230
```

**Error de impresión:**
```
❌ Error de Impresión  
Archivo: etiqueta_002.pdf
Impresora: Impresora_Inexistente
Error: Impresora no encontrada
```

## 💾 Backup y Restauración

### Backup Automático

**Qué incluye:**
- Base de datos con historial completo
- Configuraciones de carpetas e impresoras
- Configuración de notificaciones
- Logs del sistema

**Programación:**
- Backups automáticos diarios
- Retención de 7 días
- Ubicación: `backups/`

### Backup Manual

**Desde Dashboard Web:**
1. Ir a Configuración → Backup
2. Clic en "Crear Backup Manual"
3. Descargar archivo generado

**Desde línea de comandos:**
```bash
python src/backup_manager.py
```

### Restauración

**Pasos:**
1. Detener sistema
2. Copiar archivos de backup a directorio principal
3. Reiniciar sistema
4. Verificar configuración

## 🖨️ Gestión de Impresoras

### Impresoras Soportadas

**Marcas compatibles:**
- Zebra (ZT230, ZT410, etc.)
- Godex (GE300, GE330, etc.)
- Datamax
- Honeywell
- Cualquier impresora compatible con ZPL

### Configuración de Impresoras

**Requisitos:**
1. Impresora instalada en Windows
2. Driver correcto instalado
3. Impresora configurada como compartida (opcional)

**Verificación:**
- GUI → Botón "🔄 Actualizar Impresoras"
- Dashboard → Ver lista de impresoras disponibles

### Resolución de Problemas

**Impresora no aparece:**
1. Verificar que esté instalada en Windows
2. Actualizar lista de impresoras
3. Reiniciar servicio de impresión Windows

**Trabajos no se imprimen:**
1. Verificar estado de impresora
2. Revisar cola de impresión Windows
3. Comprobar conectividad (USB/Red)

## 🔧 Mantenimiento

### Limpieza Regular

**Logs:**
- Limpiar logs antiguos: Dashboard → Herramientas
- Exportar logs: GUI → Botón "💾 Exportar Logs"

**Base de datos:**
- Limpiar trabajos antiguos: Dashboard → Herramientas
- Optimizar BD automáticamente cada 7 días

**Archivos temporales:**
- Limpiar carpeta temp automáticamente
- Verificar espacio en disco

### Monitoreo del Sistema

**Métricas importantes:**
- **CPU**: < 80% normal
- **RAM**: < 85% normal  
- **Disco**: < 90% normal
- **BD**: < 100MB normal

**Alertas automáticas:**
- Recursos altos
- Errores frecuentes
- Espacio en disco bajo

## 🚨 Resolución de Problemas

### Problemas Comunes

**1. "No module named..."**
```bash
# Solución: Usar launcher principal
python quick_start.py
```

**2. "API no disponible"**
```bash
# Verificar que esté ejecutándose
python api/fast_api.py
```

**3. "Poppler no encontrado"**
```bash
# Instalar Poppler
python install_poppler.py
```

**4. "Impresora no encontrada"**
- Verificar instalación en Windows
- Actualizar lista de impresoras
- Revisar nombre exacto

### Logs de Diagnóstico

**Ubicaciones:**
- `logs/etiquetador.log` - Log principal
- `logs/errores.log` - Solo errores
- Dashboard → Ver logs en tiempo real

**Niveles de log:**
- **INFO** - Información general
- **WARNING** - Advertencias
- **ERROR** - Errores que requieren atención
- **CRITICAL** - Errores críticos del sistema

### Contacto y Soporte

**Para problemas técnicos:**
1. Revisar logs de error
2. Exportar logs del sistema
3. Documentar pasos para reproducir problema
4. Incluir configuración actual

## 📊 Estadísticas y Reportes

### Métricas Disponibles

**Dashboard Web:**
- Total de trabajos procesados
- Tasa de éxito/error
- Tiempo promedio de procesamiento
- Trabajos por impresora
- Actividad por día/semana

**Exportación:**
- Reportes en formato JSON
- Logs detallados en ZIP
- Estadísticas por período

### Interpretación de Métricas

**Rendimiento óptimo:**
- Tasa de éxito > 95%
- Tiempo promedio < 5 segundos
- Sin errores críticos
- CPU/RAM estables

## 🔄 Actualizaciones

### Verificar Versión Actual
```bash
python quick_start.py
# Ver información en dashboard web
```

### Backup Antes de Actualizar
```bash
# Crear backup completo
python src/backup_manager.py
```

### Aplicar Actualizaciones
1. Detener sistema completamente
2. Crear backup de seguridad
3. Aplicar nuevos archivos
4. Verificar configuración
5. Reiniciar sistema
6. Probar funcionalidad básica

---

## 📞 Información de Contacto

**Sistema**: EtiquetadorZPL v1.0  
**Documentación**: Manual de Usuario  
**Última actualización**: 2025-01-08

---

*Este manual cubre las funcionalidades principales del sistema. Para casos específicos o problemas técnicos, consultar los logs del sistema y la documentación técnica.*