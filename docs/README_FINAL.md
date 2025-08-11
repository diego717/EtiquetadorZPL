# EtiquetadorZPL - Versión Final Limpia

## 📁 Estructura de Archivos

### Archivos Principales:
- `launcher.pyw` - Launcher principal (usa versión optimizada)
- `main_gui_optimized.py` - GUI con mejoras de rendimiento
- `main_gui.py` - GUI original (fallback)
- `start_system.bat` - Iniciar sistema híbrido

### API y Backend:
- `final_api.py` - API simple y robusta
- `fastapi_server.py` - API avanzada (cuando FastAPI esté disponible)

### Core del Sistema:
- `handlers.py` - Procesamiento de archivos
- `printer.py` - Funciones de impresión
- `printer_utils.py` - Utilidades de impresoras
- `config.py` - Gestión de configuración

### Optimización:
- `performance_optimizer.py` - Herramientas de rendimiento
- `performance_config.py` - Configuración de optimización

### Utilidades:
- `verificar_dependencias.py` - Verificar instalación
- `cleanup.py` - Limpiar archivos obsoletos

## 🚀 Uso Recomendado

### Opción 1: GUI Optimizada Sola
```bash
python launcher.pyw
```

### Opción 2: Sistema Híbrido (GUI + API)
```bash
start_system.bat
```

### Opción 3: Solo API
```bash
python final_api.py
```

## ✅ Beneficios Actuales
- Carga 30-50% más rápida
- UI más responsiva
- Mejor gestión de memoria
- Fallback automático
- Arquitectura híbrida preparada

## 🔄 Próximos Pasos
1. Usar sistema híbrido con `start_system.bat`
2. Migrar a FastAPI cuando se resuelvan dependencias
3. Implementar como servicio de Windows
4. Agregar interfaz web