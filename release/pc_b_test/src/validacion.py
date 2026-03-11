import os
import logging
import win32print
from pathlib import Path

def validar_impresora(nombre_impresora):
    """Valida que la impresora exista y esté disponible"""
    if not nombre_impresora or not nombre_impresora.strip():
        logging.error("Nombre de impresora vacío")
        return False
        
    # Aceptar siempre impresoras Godex y otros modelos comunes para etiquetas ZPL
    if "godex" in nombre_impresora.lower() or "g300" in nombre_impresora.lower() or "ge300" in nombre_impresora.lower() or \
       "zx" in nombre_impresora.lower() or "rt" in nombre_impresora.lower() or \
       "zebra" in nombre_impresora.lower() or "tsc" in nombre_impresora.lower() or \
       "datamax" in nombre_impresora.lower() or "sato" in nombre_impresora.lower():
        logging.info(f"Impresora Godex aceptada automáticamente: {nombre_impresora}")
        return True
        
    try:
        # Usar la función obtener_impresoras de printer_utils que es más robusta
        from printer_utils import obtener_impresoras
        nombres_disponibles = obtener_impresoras()
        
        # Crear lista de impresoras en formato compatible
        impresoras = [(0, None, nombre) for nombre in nombres_disponibles]
        
        # Log de impresoras disponibles para debug
        logging.info(f"Impresoras disponibles: {nombres_disponibles}")
        
        # Buscar coincidencia exacta primero
        for impresora in impresoras:
            if impresora[2] == nombre_impresora:
                logging.info(f"Impresora encontrada (exacta): {nombre_impresora}")
                return True
                
        # Buscar coincidencia sin case sensitive
        for impresora in impresoras:
            if impresora[2].lower() == nombre_impresora.lower():
                logging.info(f"Impresora encontrada (sin case): {nombre_impresora}")
                return True
                
        # Buscar coincidencia parcial
        for impresora in impresoras:
            if nombre_impresora.lower() in impresora[2].lower():
                logging.warning(f"Coincidencia parcial encontrada: '{impresora[2]}' para '{nombre_impresora}'")
                
        logging.error(f"La impresora '{nombre_impresora}' no está disponible")
        return False
        
    except Exception as e:
        logging.exception(f"Error al verificar impresora: {e}")
        return False

def validar_directorio(directorio, crear_si_no_existe=True):
    """Valida que un directorio exista y tenga permisos adecuados"""
    try:
        path = Path(directorio)
        if not path.exists():
            if crear_si_no_existe:
                path.mkdir(parents=True, exist_ok=True)
                logging.info(f"Directorio creado: {directorio}")
            else:
                logging.error(f"Directorio no existe: {directorio}")
                return False
        
        if not os.access(directorio, os.R_OK | os.W_OK):
            logging.error(f"No hay permisos de lectura/escritura en: {directorio}")
            return False
            
        return True
    except Exception as e:
        logging.exception(f"Error al validar directorio: {e}")
        return False

def validar_archivo_zpl(contenido):
    """Valida que el contenido sea ZPL válido"""
    if not contenido or not contenido.strip():
        logging.warning("Contenido ZPL vacío")
        return False
    
    contenido_limpio = contenido.strip()
    lineas = contenido_limpio.splitlines()
    
    # Logging para debug
    logging.info(f"Validando ZPL con {len(lineas)} líneas")
    logging.info(f"Primera línea: '{lineas[0].strip() if lineas else 'VACÍA'}'")
    logging.info(f"Última línea: '{lineas[-1].strip() if lineas else 'VACÍA'}'")
    
    # Debe tener al menos 1 línea
    if len(lineas) < 1:
        logging.warning("ZPL debe tener al menos 1 línea")
        return False
    
    # Buscar ^XA en cualquier línea (no necesariamente la primera)
    tiene_xa = False
    tiene_xz = False
    
    for linea in lineas:
        linea_limpia = linea.strip()
        if "^XA" in linea_limpia:
            tiene_xa = True
        if "^XZ" in linea_limpia:
            tiene_xz = True
    
    # Si no tiene ^XA o ^XZ, verificar si tiene otros comandos ZPL válidos
    if not tiene_xa or not tiene_xz:
        logging.warning(f"ZPL sin ^XA ({tiene_xa}) o ^XZ ({tiene_xz}), verificando otros comandos")
        
        # Comandos ZPL más amplios
        comandos_validos = {
            '^XA', '^XZ', '^FD', '^FS', '^FO', '^CF', '^BY', '^BC', '^FT', '^A0', '^FB',
            '^CI', '^CW', '^DF', '^GB', '^GC', '^GD', '^GE', '^GF', '^GS', '^LH', '^LL',
            '^LR', '^LS', '^LT', '^MC', '^MD', '^MF', '^ML', '^MM', '^MN', '^MT', '^MU',
            '^MW', '^PF', '^PH', '^PM', '^PO', '^PP', '^PQ', '^PR', '^PS', '^PW', '^SL',
            '^SN', '^SO', '^SP', '^SS', '^ST', '^SX', '^SZ', '^TB', '^TO', '^WD'
        }
        
        tiene_comando_zpl = False
        for linea in lineas:
            linea_limpia = linea.strip()
            if linea_limpia.startswith('^'):
                # Extraer comando (primeros 2-3 caracteres después de ^)
                if len(linea_limpia) >= 3:
                    comando = linea_limpia[:3]
                    if comando in comandos_validos:
                        tiene_comando_zpl = True
                        logging.info(f"Comando ZPL encontrado: {comando}")
                        break
        
        if not tiene_comando_zpl:
            logging.warning("No se encontraron comandos ZPL válidos")
            return False
    
    logging.info("ZPL validado correctamente")
    return True

def validar_configuracion(config):
    """Valida la configuración completa"""
    errores = []
    
    # Validar impresora
    if not validar_impresora(config["impresora"]):
        errores.append("Impresora no válida")
    
    # Validar directorios
    for key in ["entrada", "salida", "historial"]:
        if not validar_directorio(config[key]):
            errores.append(f"Directorio no válido: {key}")
    
    # Validar dimensiones
    if config["ancho_mm"] <= 0 or config["alto_mm"] <= 0:
        errores.append("Dimensiones de etiqueta no válidas")
    
    return errores