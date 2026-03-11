import logging

def obtener_impresoras():
    """
    Obtiene la lista de impresoras disponibles en el sistema.
    Muestra solo las impresoras que aparecen en Impresoras y escáneres de Windows.
    """
    todas_impresoras = set()  # Usar un conjunto para evitar duplicados
    
    # Método principal: PowerShell Get-Printer (muestra exactamente las impresoras de Windows)
    try:
        import subprocess
        # Usar startupinfo para ocultar la ventana de PowerShell
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE
        
        cmd = ["powershell", "-WindowStyle", "Hidden", "-Command", "Get-Printer | Select-Object -ExpandProperty Name"]
        result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo)
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                    todas_impresoras.add(line.strip())
            logging.info(f"Impresoras encontradas (PowerShell): {len(todas_impresoras)}")
    except Exception as e:
        logging.warning(f"Error al obtener impresoras con PowerShell: {e}")
        
        # Método alternativo: win32print (solo si PowerShell falla)
        try:
            import win32print
            # Solo impresoras locales y la predeterminada
            impresoras_local = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)
            for imp in impresoras_local:
                todas_impresoras.add(imp[2])
                
            # Agregar impresora predeterminada
            try:
                default_printer = win32print.GetDefaultPrinter()
                if default_printer:
                    todas_impresoras.add(default_printer)
                    logging.info(f"Impresora predeterminada: {default_printer}")
            except Exception:
                pass
                
            logging.info(f"Impresoras encontradas (win32print): {len(todas_impresoras)}")
        except Exception as e2:
            logging.warning(f"Error al obtener impresoras con win32print: {e2}")
    
    # Asegurar que la impresora Godex esté disponible si existe
    godex_encontrada = False
    for impresora in todas_impresoras:
        if "godex" in impresora.lower():
            godex_encontrada = True
            logging.info(f"Impresora Godex encontrada: {impresora}")
            break
            
    # Si no se encontró ninguna Godex, buscar específicamente
    if not godex_encontrada:
        try:
            # Buscar impresoras Godex y otros modelos comunes de impresoras térmicas
            import subprocess
            # Usar startupinfo para ocultar la ventana de PowerShell
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            
            # Buscar por fabricantes comunes de impresoras térmicas
            fabricantes = ["Godex", "Zebra", "TSC", "Datamax", "Intermec", "Sato", "Honeywell"]
            for fabricante in fabricantes:
                cmd = ["powershell", "-WindowStyle", "Hidden", "-Command", 
                      f"Get-WmiObject -Class Win32_Printer | Where-Object {{$_.Name -like '*{fabricante}*'}} | Select-Object -ExpandProperty Name"]
                result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo)
                if result.returncode == 0:
                    for line in result.stdout.strip().split('\n'):
                        if line.strip():
                            todas_impresoras.add(line.strip())
                            logging.info(f"Impresora {fabricante} encontrada: {line.strip()}")
                            if fabricante.lower() == "godex":
                                godex_encontrada = True
            
            # Buscar por puertos COM, USB y TCP/IP que suelen usar las impresoras térmicas
            cmd = ["powershell", "-WindowStyle", "Hidden", "-Command", 
                  "Get-WmiObject -Class Win32_Printer | Where-Object {$_.PortName -like 'COM*' -or $_.PortName -like 'USB*' -or $_.PortName -like 'IP_*' -or $_.PortName -like 'TCP*' -or $_.Network -eq $true} | Select-Object -ExpandProperty Name"]
            result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo)
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        todas_impresoras.add(line.strip())
                        logging.info(f"Impresora en puerto COM/USB/RED encontrada: {line.strip()}")
                        # Verificar si es una Godex
                        if "godex" in line.lower() or "g300" in line.lower() or "ge300" in line.lower() or \
                           "zx" in line.lower() or "rt" in line.lower():
                            godex_encontrada = True
                            
            # Buscar impresoras de red específicamente
            cmd = ["powershell", "-WindowStyle", "Hidden", "-Command", 
                  "Get-WmiObject -Class Win32_Printer | Where-Object {$_.Network -eq $true} | Select-Object -ExpandProperty Name"]
            result = subprocess.run(cmd, capture_output=True, text=True, startupinfo=startupinfo)
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        todas_impresoras.add(line.strip())
                        logging.info(f"Impresora de red encontrada: {line.strip()}")
        except Exception as e:
            logging.warning(f"Error al buscar impresoras Godex: {e}")
    
    # Agregar impresoras predeterminadas si la lista está vacía
    if not todas_impresoras:
        todas_impresoras = {"Microsoft Print to PDF", "Microsoft XPS Document Writer"}
        logging.warning("Usando lista de impresoras predeterminadas")
        
        # Agregar Godex GE300 si no se encontró ninguna Godex
        if not godex_encontrada:
            todas_impresoras.add("Godex GE300")
            logging.warning("Añadiendo impresora Godex GE300 predeterminada")
    
    # Convertir el conjunto a lista y ordenar
    impresoras = sorted(list(todas_impresoras))
    logging.info(f"Total de impresoras encontradas: {len(impresoras)}")
    logging.info(f"Impresoras: {impresoras}")
    
    return impresoras

def obtener_impresora_predeterminada():
    """
    Obtiene la impresora predeterminada del sistema.
    """
    try:
        import win32print
        return win32print.GetDefaultPrinter()
    except Exception as e:
        logging.warning(f"Error al obtener impresora predeterminada: {e}")
        return None