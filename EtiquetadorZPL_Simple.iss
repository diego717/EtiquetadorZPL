[Setup]
AppName=EtiquetadorZPL
AppVersion=1.0
AppPublisher=Tu Empresa
DefaultDirName={autopf}\EtiquetadorZPL
DefaultGroupName=EtiquetadorZPL
OutputDir=installer
OutputBaseFilename=EtiquetadorZPL_Setup
; SetupIconFile=etiquetador_icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear icono en el escritorio"; GroupDescription: "Iconos adicionales:"
Name: "autostart"; Description: "Iniciar automaticamente con Windows"; GroupDescription: "Opciones de inicio:"

[Files]
; Ejecutable principal
Source: "dist\EtiquetadorZPL.exe"; DestDir: "{app}"; Flags: ignoreversion

; Archivos web
Source: "web\*"; DestDir: "{app}\web"; Flags: ignoreversion recursesubdirs createallsubdirs

; Poppler binaries
Source: "poppler\poppler-23.08.0\Library\bin\*"; DestDir: "{app}\poppler\poppler-23.08.0\Library\bin"; Flags: ignoreversion
Source: "poppler\poppler-23.08.0\share\*"; DestDir: "{app}\poppler\poppler-23.08.0\share"; Flags: ignoreversion recursesubdirs createallsubdirs

; Configuración
; Archivos de configuración (solo si no existen)
Source: "config\*"; DestDir: "{app}\config"; Flags: ignoreversion onlyifdoesntexist

; Archivos adicionales necesarios
Source: "config.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "poppler_manager.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "get_writable_path.py"; DestDir: "{app}"; Flags: ignoreversion

; Manual de usuario
Source: "MANUAL_USUARIO.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\EtiquetadorZPL"; Filename: "{app}\EtiquetadorZPL.exe"
Name: "{group}\Dashboard Web"; Filename: "http://localhost:8002/web/"
Name: "{group}\{cm:UninstallProgram,EtiquetadorZPL}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\EtiquetadorZPL"; Filename: "{app}\EtiquetadorZPL.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\EtiquetadorZPL.exe"; Description: "Ejecutar EtiquetadorZPL"; Flags: nowait postinstall skipifsilent

[Registry]
; Agregar poppler al PATH del sistema
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}\poppler\poppler-23.08.0\Library\bin"; Check: NeedsAddPath('{app}\poppler\poppler-23.08.0\Library\bin')

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_LOCAL_MACHINE,
    'SYSTEM\CurrentControlSet\Control\Session Manager\Environment',
    'Path', OrigPath)
  then begin
    Result := True;
    exit;
  end;
  // look for the path with leading and trailing semicolon
  // Pos() returns 0 if not found
  Result := Pos(';' + UpperCase(Param) + ';', ';' + UpperCase(OrigPath) + ';') = 0;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Crear carpetas de trabajo
    ForceDirectories('C:\EtiquetasFlex');
    ForceDirectories('C:\EtiquetasFlex\Entrada1');
    ForceDirectories('C:\EtiquetasFlex\Historial1');
    
    // Crear carpetas de logs y temp en la aplicación
    ForceDirectories(ExpandConstant('{app}\logs'));
    ForceDirectories(ExpandConstant('{app}\temp'));
    
    // Configurar inicio automatico si se selecciono
    if IsTaskSelected('autostart') then
    begin
      CreateShellLink(
        ExpandConstant('{userstartup}\EtiquetadorZPL.lnk'),
        'Iniciar EtiquetadorZPL automaticamente',
        ExpandConstant('{app}\EtiquetadorZPL.exe'),
        '',
        ExpandConstant('{app}'),
        ExpandConstant('{app}\EtiquetadorZPL.exe'),
        0,
        SW_SHOWNORMAL
      );
    end;
  end;
end;