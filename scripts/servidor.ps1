<#
EtiquetadorZPL - administracion del servidor (API + web) en una PC Windows.

Acciones:
  Instalar     Copia el paquete a InstallDir, crea .venv, instala dependencias,
               importa la config (si hay un EtiquetadorZPL_config_*.zip junto al paquete),
               abre el firewall y registra la tarea de inicio automatico.
               Se usa igual para actualizar: la config en %APPDATA% no se toca.
  Supervisar   Mantiene la API corriendo (la relanza si se cae). Lo ejecuta la tarea.
  Exportar     Detiene la API y comprime %APPDATA%\EtiquetadorZPL en un ZIP.
  Importar     Restaura un ZIP exportado en %APPDATA%\EtiquetadorZPL (con backup previo).
  Desactivar   Quita el inicio automatico y detiene la API en esta PC.
  Estado       Muestra tarea, proceso y URL.

Este archivo es ASCII a proposito (PowerShell 5.1 lee .ps1 sin BOM como ANSI).
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Instalar", "Supervisar", "Exportar", "Importar", "Desactivar", "Estado")]
    [string]$Accion,
    [string]$InstallDir = "C:\EtiquetadorZPL",
    [int]$Port = 8002,
    [string]$ConfigDir = (Join-Path $env:APPDATA "EtiquetadorZPL"),
    [string]$ZipPath = "",
    [string]$TaskName = "EtiquetadorZPL Servidor",
    [switch]$SinTarea,
    [switch]$NoPausar
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path $PSScriptRoot -Parent
$LegacyTaskNames = @("EtiquetadorZPL API", "EtiquetadorZPL_API_Autostart")
$PauseFlag = Join-Path $ConfigDir "servidor_pausado.flag"
$ConfigExclude = @("logs", "client_assets_previews")

function Write-Step([string]$msg) { Write-Host "`n>> $msg" -ForegroundColor Cyan }
function Write-Ok([string]$msg) { Write-Host "   [OK] $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "   [AVISO] $msg" -ForegroundColor Yellow }

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal $id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-PortListening([int]$p) {
    $client = New-Object Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect("127.0.0.1", $p, $null, $null)
        if (-not $iar.AsyncWaitHandle.WaitOne(1000)) { return $false }
        $client.EndConnect($iar)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-ApiHealthy([int]$p) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$p/api/status" -TimeoutSec 3
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

function Wait-ApiHealthy([int]$p, [int]$seconds) {
    $deadline = (Get-Date).AddSeconds($seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-ApiHealthy $p) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Get-LanUrls([int]$p) {
    $ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.PrefixOrigin -ne "WellKnown" } |
        Select-Object -ExpandProperty IPAddress
    $urls = @("http://$($env:COMPUTERNAME):$p/web/")
    foreach ($ip in $ips) { $urls += "http://${ip}:$p/web/" }
    return $urls
}

function Stop-Api([int]$p, [switch]$KeepSupervisor) {
    # Supervisores primero, para que no relancen la API apenas la cerramos.
    # Con -KeepSupervisor se asume que servidor_pausado.flag ya lo frena.
    if (-not $KeepSupervisor) {
        Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
            Where-Object { $_.CommandLine -match "servidor\.ps1" -and $_.CommandLine -match "Supervisar" -and $_.CommandLine -match "-Port $p\b" -and $_.ProcessId -ne $PID } |
            ForEach-Object {
                Write-Host "   Cerrando supervisor PID $($_.ProcessId)"
                Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
            }
    }

    $pids = @(Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique)
    foreach ($procId in $pids) {
        if ($procId -and $procId -ne 0) {
            Write-Host "   Cerrando API PID $procId (puerto $p)"
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        }
    }

    for ($i = 0; $i -lt 10; $i++) {
        if (-not (Test-PortListening $p)) { return }
        Start-Sleep -Seconds 1
    }
    throw "No se pudo liberar el puerto $p. Ejecutar como Administrador."
}

function Find-BasePython {
    $candidates = @(
        @("py", "-3.10"),
        @("py", "-3"),
        @("python")
    )
    foreach ($cand in $candidates) {
        $exe = $cand[0]
        if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
        $cmdArgs = @()
        if ($cand.Count -gt 1) { $cmdArgs += $cand[1..($cand.Count - 1)] }
        $cmdArgs += @("-c", "import sys; print(sys.executable if sys.version_info >= (3, 10) else '')")
        try {
            $out = & $exe @cmdArgs 2>$null | Select-Object -Last 1
        } catch {
            continue
        }
        if ($out -and (Test-Path $out) -and ($out -notmatch "WindowsApps")) { return $out.Trim() }
    }
    return $null
}

function Get-VenvPython([string]$root) {
    return (Join-Path $root ".venv\Scripts\python.exe")
}

# ---------------------------------------------------------------- Supervisar

function Invoke-Supervisar {
    $root = $ProjectRoot
    $py = Get-VenvPython $root
    if (-not (Test-Path $py)) {
        $py = Find-BasePython
        if (-not $py) { throw "No hay Python: falta $root\.venv (correr la instalacion)." }
    }

    # Una sola instancia del supervisor por puerto.
    $created = $false
    $mutex = New-Object Threading.Mutex($true, "Global\EtiquetadorZPL_Supervisor_$Port", [ref]$created)
    if (-not $created) {
        Write-Host "Ya hay un supervisor corriendo para el puerto $Port."
        return
    }

    $logDir = Join-Path $ConfigDir "logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $supLog = Join-Path $logDir "supervisor.log"
    $outLog = Join-Path $logDir "api_stdout.log"
    $errLog = Join-Path $logDir "api_stderr.log"
    $emptyIn = Join-Path $logDir "stdin_vacio.txt"
    Set-Content -Path $emptyIn -Value "" -Encoding ascii

    function Log([string]$m) {
        $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $m
        Add-Content -Path $supLog -Value $line -Encoding utf8
        Write-Host $line
    }

    $env:ETIQUETADOR_API_HOST = "0.0.0.0"
    $env:ETIQUETADOR_API_PORT = "$Port"
    $env:PYTHONUNBUFFERED = "1"
    $env:PYTHONIOENCODING = "utf-8"

    Log "Supervisor iniciado (python=$py, puerto=$Port, usuario=$env:USERNAME, config=$ConfigDir)"
    $busyLogged = $false
    try {
        while ($true) {
            if (Test-Path $PauseFlag) {
                Start-Sleep -Seconds 5
                continue
            }
            if (Test-PortListening $Port) {
                # Otra instancia (ej. la app de escritorio) ya ocupa el puerto: no duplicar.
                if (-not $busyLogged) { Log "Puerto $Port ocupado por otro proceso; espero."; $busyLogged = $true }
                Start-Sleep -Seconds 30
                continue
            }
            $busyLogged = $false

            foreach ($f in @($outLog, $errLog)) {
                if ((Test-Path $f) -and ((Get-Item $f).Length -gt 5MB)) { Move-Item $f "$f.1" -Force }
            }
            if (Test-Path $outLog) { Add-Content -Path $outLog -Value "`n===== $(Get-Date -Format s) =====" -Encoding utf8 }

            Log "Iniciando API..."
            $started = Get-Date
            # cmd /c para poder ANEXAR a los logs (Start-Process -Redirect* los pisa).
            $cmdLine = "`"`"$py`" start_api_simple.py < `"$emptyIn`" >> `"$outLog`" 2>> `"$errLog`"`""
            $proc = Start-Process -FilePath "cmd.exe" -ArgumentList "/c $cmdLine" -WorkingDirectory $root -WindowStyle Hidden -PassThru
            $proc.WaitForExit()
            $ranSeconds = [int]((Get-Date) - $started).TotalSeconds
            Log "API terminada (codigo $($proc.ExitCode), duro $ranSeconds s)"

            # Si se cae enseguida, esperar mas para no quedar en bucle.
            if ($ranSeconds -lt 60) { Start-Sleep -Seconds 15 } else { Start-Sleep -Seconds 5 }
        }
    } finally {
        $mutex.ReleaseMutex()
    }
}

# ---------------------------------------------------------------- Exportar / Importar

function Invoke-Exportar {
    if (-not (Test-Path $ConfigDir)) { throw "No existe $ConfigDir" }

    $zip = $ZipPath
    if (-not $zip) {
        $desktop = [Environment]::GetFolderPath("Desktop")
        $zip = Join-Path $desktop ("EtiquetadorZPL_config_{0}_{1:yyyyMMdd-HHmm}.zip" -f $env:COMPUTERNAME, (Get-Date))
    }

    $wasRunning = Test-PortListening $Port
    New-Item -ItemType File -Force -Path $PauseFlag | Out-Null
    try {
        if ($wasRunning) {
            Write-Step "Deteniendo API para copiar la base de datos de forma consistente"
            Stop-Api $Port -KeepSupervisor
        }

        Write-Step "Comprimiendo $ConfigDir"
        $staging = Join-Path $env:TEMP ("etiq_export_" + [Guid]::NewGuid().ToString("N"))
        New-Item -ItemType Directory -Force -Path $staging | Out-Null
        try {
            Get-ChildItem -Path $ConfigDir -Force |
                Where-Object { $ConfigExclude -notcontains $_.Name -and $_.Name -ne "servidor_pausado.flag" -and $_.Name -notlike "*.backup-*" } |
                ForEach-Object { Copy-Item -Path $_.FullName -Destination $staging -Recurse -Force }
            if (Test-Path $zip) { Remove-Item $zip -Force }
            Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zip -Force
        } finally {
            Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
        }
    } finally {
        Remove-Item $PauseFlag -Force -ErrorAction SilentlyContinue
    }

    $sizeMb = [math]::Round((Get-Item $zip).Length / 1MB, 1)
    Write-Ok "Config exportada: $zip ($sizeMb MB)"
    Write-Warn "El ZIP contiene credenciales (Odoo, Mercado Libre, Totalnet). No subirlo a ningun lado; borrarlo despues de importarlo."
    return $zip
}

function Find-ConfigZip {
    if ($ZipPath) { return $ZipPath }
    $zips = @(Get-ChildItem -Path $ProjectRoot -Filter "EtiquetadorZPL_config_*.zip" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending)
    if ($zips.Count -gt 0) { return $zips[0].FullName }
    return $null
}

function Invoke-Importar([string]$zip) {
    if (-not $zip -or -not (Test-Path $zip)) { throw "No se encontro el ZIP de configuracion." }

    Write-Step "Importando configuracion desde $zip"
    if (Test-PortListening $Port) { Stop-Api $Port }

    if ((Test-Path $ConfigDir) -and (Get-ChildItem $ConfigDir -Force | Where-Object { $_.Name -ne "logs" })) {
        $backup = "{0}.backup-{1:yyyyMMdd-HHmmss}" -f $ConfigDir, (Get-Date)
        Move-Item -Path $ConfigDir -Destination $backup
        Write-Ok "Config anterior guardada en $backup"
    }
    New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
    Expand-Archive -Path $zip -DestinationPath $ConfigDir -Force
    Write-Ok "Config importada en $ConfigDir"
}

# ---------------------------------------------------------------- Tarea programada

function Register-ServerTask([string]$root) {
    $ps1 = Join-Path $root "scripts\servidor.ps1"
    $argLine = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$ps1`" -Accion Supervisar -Port $Port"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $argLine -WorkingDirectory $root
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
        -MultipleInstances IgnoreNew -StartWhenAvailable
    $user = "$env:USERDOMAIN\$env:USERNAME"

    Write-Host ""
    Write-Host "   Para que el servidor arranque al PRENDER la PC (sin que nadie inicie sesion)," -ForegroundColor White
    Write-Host "   Windows necesita la contrasena del usuario $user." -ForegroundColor White
    Write-Host "   Si la dejas vacia, arranca recien cuando $user inicie sesion." -ForegroundColor White
    $secure = Read-Host "   Contrasena de $user (Enter = sin contrasena)" -AsSecureString
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))

    if ($plain) {
        $triggers = @((New-ScheduledTaskTrigger -AtStartup), (New-ScheduledTaskTrigger -AtLogOn -User $user))
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Settings $settings `
            -User $user -Password $plain -RunLevel Highest -Force | Out-Null
        Write-Ok "Tarea '$TaskName': arranca al prender la PC (modo sin sesion)."
    } else {
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $user
        $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Highest
        Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
            -Principal $principal -Force | Out-Null
        Write-Ok "Tarea '$TaskName': arranca cuando $user inicia sesion."
    }
    $plain = $null
}

function Remove-ServerTasks {
    foreach ($name in @($TaskName) + $LegacyTaskNames) {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($task) {
            Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
            Unregister-ScheduledTask -TaskName $name -Confirm:$false
            Write-Ok "Tarea eliminada: $name"
        }
    }
}

# ---------------------------------------------------------------- Instalar

function Invoke-Instalar {
    if (-not $SinTarea -and -not (Test-Admin)) { throw "La instalacion necesita permisos de Administrador." }

    $source = $ProjectRoot
    $target = [IO.Path]::GetFullPath($InstallDir)
    $isUpdate = Test-Path (Join-Path $target "start_api_simple.py")

    # Algunas dependencias (playwright) tienen rutas internas de ~130 caracteres.
    $longPaths = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -ErrorAction SilentlyContinue).LongPathsEnabled
    if ($target.Length -gt 60 -and $longPaths -ne 1) {
        throw "La carpeta de instalacion tiene una ruta muy larga para Windows: $target. Usar una corta, ej. C:\EtiquetadorZPL"
    }

    if ($isUpdate -and (Test-PortListening $Port)) {
        Write-Step "Deteniendo el servidor para actualizar"
        Stop-Api $Port
    }

    if ($source.TrimEnd("\") -ne $target.TrimEnd("\")) {
        Write-Step "Copiando programa a $target"
        New-Item -ItemType Directory -Force -Path $target | Out-Null
        & robocopy $source $target /E /NFL /NDL /NJH /NJS /NP /XD ".venv" "__pycache__" "logs" /XF "EtiquetadorZPL_config_*.zip" "api_port.txt" | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "robocopy fallo (codigo $LASTEXITCODE)" }
        Write-Ok "Archivos copiados"
    }

    Write-Step "Preparando Python (.venv)"
    $venvPy = Get-VenvPython $target
    if (-not (Test-Path $venvPy)) {
        $basePy = Find-BasePython
        if (-not $basePy) {
            throw "No se encontro Python 3.10+. Instalarlo con: winget install --id Python.Python.3.10 -e  (y volver a correr esto)"
        }
        Write-Host "   Python base: $basePy"
        & $basePy -m venv (Join-Path $target ".venv")
        if ($LASTEXITCODE -ne 0) { throw "No se pudo crear el entorno .venv" }
    }

    $req = Join-Path $target "requirements.txt"
    $hashFile = Join-Path $target ".venv\requirements.sha256"
    $reqHash = (Get-FileHash $req -Algorithm SHA256).Hash
    $oldHash = if (Test-Path $hashFile) { (Get-Content $hashFile -Raw).Trim() } else { "" }
    if ($reqHash -ne $oldHash) {
        Write-Step "Instalando dependencias (la primera vez tarda varios minutos)"
        & $venvPy -m pip install --upgrade pip --disable-pip-version-check -q
        & $venvPy -m pip install -r $req --disable-pip-version-check
        if ($LASTEXITCODE -ne 0) { throw "Fallo la instalacion de dependencias" }
        Set-Content -Path $hashFile -Value $reqHash -Encoding ascii
        Write-Ok "Dependencias instaladas"

        Write-Step "Instalando Chromium de Playwright (para Administrado)"
        & $venvPy -m playwright install chromium
        if ($LASTEXITCODE -ne 0) { Write-Warn "No se pudo instalar Chromium; Administrado puede no funcionar." } else { Write-Ok "Chromium listo" }
    } else {
        Write-Ok "Dependencias sin cambios"
    }

    $zip = Find-ConfigZip
    if ($zip) {
        Invoke-Importar $zip
    } elseif (-not (Test-Path $ConfigDir)) {
        Write-Warn "No se encontro EtiquetadorZPL_config_*.zip junto al paquete: el servidor arranca sin configuracion."
    }

    if (-not $SinTarea) {
        Write-Step "Firewall (puerto $Port para la red local)"
        $ruleName = "EtiquetadorZPL API $Port"
        if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
            New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Domain, Private | Out-Null
        }
        Write-Ok "Regla '$ruleName' activa (redes privadas/dominio)"

        Write-Step "Inicio automatico"
        foreach ($name in $LegacyTaskNames) {
            if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
                Unregister-ScheduledTask -TaskName $name -Confirm:$false
                Write-Ok "Tarea vieja eliminada: $name"
            }
        }
        Register-ServerTask $target

        Write-Step "Arrancando servidor"
        Start-ScheduledTask -TaskName $TaskName
        if (Wait-ApiHealthy $Port 120) {
            Write-Ok "Servidor funcionando"
        } else {
            Write-Warn "El servidor no respondio en 2 minutos. Ver $ConfigDir\logs\api_stderr.log"
        }
        Write-Host ""
        Write-Host "   Abrir desde cualquier PC de la oficina:" -ForegroundColor White
        foreach ($u in Get-LanUrls $Port) { Write-Host "     $u" }
    }

    if ($zip -and ($zip -like "$source*")) {
        Write-Warn "Borrar el ZIP de configuracion cuando confirmes que todo anda: $zip"
    }
}

# ---------------------------------------------------------------- Desactivar / Estado

function Invoke-Desactivar {
    Write-Step "Quitando inicio automatico"
    if (-not (Test-Admin)) { Write-Warn "Sin permisos de Administrador puede no poder borrar las tareas." }
    Remove-ServerTasks
    Write-Step "Deteniendo API"
    if (Test-PortListening $Port) { Stop-Api $Port; Write-Ok "API detenida" } else { Write-Ok "No estaba corriendo" }
}

function Invoke-Estado {
    foreach ($name in @($TaskName) + $LegacyTaskNames) {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($task) {
            $trig = ($task.Triggers | ForEach-Object { $_.CimClass.CimClassName -replace "MSFT_Task", "" -replace "Trigger", "" }) -join ", "
            Write-Host ("Tarea '{0}': {1} | disparadores: {2} | modo: {3}" -f $name, $task.State, $trig, $task.Principal.LogonType)
        }
    }
    if (Test-ApiHealthy $Port) {
        Write-Host "API: respondiendo en puerto $Port" -ForegroundColor Green
        foreach ($u in Get-LanUrls $Port) { Write-Host "  $u" }
    } elseif (Test-PortListening $Port) {
        Write-Host "API: puerto $Port ocupado pero /api/status no responde" -ForegroundColor Yellow
    } else {
        Write-Host "API: detenida" -ForegroundColor Yellow
    }
    Write-Host "Config: $ConfigDir"
}

# ---------------------------------------------------------------- main

$exitCode = 0
try {
    switch ($Accion) {
        "Supervisar" { Invoke-Supervisar }
        "Instalar" { Invoke-Instalar }
        "Exportar" { Invoke-Exportar | Out-Null }
        "Importar" {
            Invoke-Importar (Find-ConfigZip)
            if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
                Start-ScheduledTask -TaskName $TaskName
                if (Wait-ApiHealthy $Port 120) { Write-Ok "Servidor reiniciado con la config importada" }
            }
        }
        "Desactivar" { Invoke-Desactivar }
        "Estado" { Invoke-Estado }
    }
} catch {
    Write-Host "`n[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    $exitCode = 1
}

if ($Accion -ne "Supervisar" -and -not $NoPausar) {
    Write-Host ""
    Read-Host "Enter para cerrar" | Out-Null
}
exit $exitCode
