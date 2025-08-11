[Setup]
; Información básica
AppName=EtiquetadorZPL
AppVersion=1.0
AppPublisher=Tu Empresa
AppPublisherURL=https://tu-sitio-web.com
AppSupportURL=https://tu-sitio-web.com/soporte
AppUpdatesURL=https://tu-sitio-web.com/actualizaciones
DefaultDirName={autopf}\EtiquetadorZPL
DefaultGroupName=EtiquetadorZPL
AllowNoIcons=yes
OutputDir=installer
OutputBaseFilename=EtiquetadorZPL_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin

; Configuración de Windows
MinVersion=6.1
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1
Name: "autostart"; Description: "Iniciar automáticamente con Windows"; GroupDescription: "Opciones de inicio:"
Name: "createfolders"; Description: "Crear carpetas de trabajo predeterminadas"; GroupDescription: "Configuración inicial:"; Flags: checked

[Files]
; Ejecutable principal
Source: "dist\EtiquetadorZPL.exe"; DestDir: "{app}"; Flags: ignoreversion

; Archivos de configuración
Source: "web\*"; DestDir: "{app}\web"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "poppler\*"; DestDir: "{app}\poppler"; Flags: ignoreversion recursesubdirs createallsubdirs

; Documentación
Source: "MANUAL_USUARIO.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Menú inicio
Name: "{group}\EtiquetadorZPL"; Filename: "{app}\EtiquetadorZPL.exe"
Name: "{group}\Dashboard Web"; Filename: "http://localhost:8002/web/"
Name: "{group}\{cm:UninstallProgram,EtiquetadorZPL}"; Filename: "{uninstallexe}"

; Escritorio
Name: "{autodesktop}\EtiquetadorZPL"; Filename: "{app}\EtiquetadorZPL.exe"; Tasks: desktopicon

; Barra de tareas
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\EtiquetadorZPL"; Filename: "{app}\EtiquetadorZPL.exe"; Tasks: quicklaunchicon

[Run]
; Ejecutar después de instalación
Filename: "{app}\EtiquetadorZPL.exe"; Description: "{cm:LaunchProgram,EtiquetadorZPL}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; Detener servicios antes de desinstalar
Filename: "taskkill"; Parameters: "/F /IM EtiquetadorZPL.exe"; Flags: runhidden; RunOnceId: "StopEtiquetador"

[Code]
// Funciones de verificación
function FileExists(const FileName: string): Boolean;
begin
  Result := FileExists(ExpandConstant('{src}\' + FileName));
end;

function DirExists(const DirName: string): Boolean;
begin
  Result := DirExists(ExpandConstant('{src}\' + DirName));
end;

// Crear carpetas de trabajo
procedure CreateWorkFolders();
begin
  if IsTaskSelected('createfolders') then
  begin
    // Crear carpetas principales
    ForceDirectories('C:\EtiquetasFlex');
    ForceDirectories('C:\EtiquetasFlex\Entrada1');
    ForceDirectories('C:\EtiquetasFlex\Entrada2');
    ForceDirectories('C:\EtiquetasFlex\Entrada3');
    ForceDirectories('C:\EtiquetasFlex\Historial1');
    ForceDirectories('C:\EtiquetasFlex\Historial2');
    ForceDirectories('C:\EtiquetasFlex\Historial3');
    
    MsgBox('Carpetas de trabajo creadas en C:\EtiquetasFlex', mbInformation, MB_OK);
  end;
end;

// Configurar inicio automático
procedure ConfigureAutoStart();
var
  StartupPath: String;
begin
  if IsTaskSelected('autostart') then
  begin
    StartupPath := ExpandConstant('{userstartup}\EtiquetadorZPL.lnk');
    CreateShellLink(
      StartupPath,
      'Iniciar EtiquetadorZPL automáticamente',
      ExpandConstant('{app}\EtiquetadorZPL.exe'),
      '',
      ExpandConstant('{app}'),
      ExpandConstant('{app}\EtiquetadorZPL.exe'),
      0,
      SW_SHOWNORMAL
    );
  end;
end;

// Verificar .NET Framework (si es necesario)
function IsDotNetDetected(version: string; service: cardinal): boolean;
var
  key: string;
  install, release, serviceCount: cardinal;
  check: boolean;
begin
  // Verificación simplificada
  Result := True;
end;

// Función principal después de instalación
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    CreateWorkFolders();
    ConfigureAutoStart();
  end;
end;

// Verificaciones antes de instalación
function InitializeSetup(): Boolean;
begin
  Result := True;
  
  // Verificar Windows version
  if not IsWin64 then
  begin
    MsgBox('Este programa requiere Windows de 64 bits.', mbError, MB_OK);
    Result := False;
  end;
  
  // Verificar espacio en disco (mínimo 500MB)
  if GetSpaceOnDisk(ExpandConstant('{autopf}'), False, nil, nil) < 500 * 1024 * 1024 then
  begin
    MsgBox('Se requieren al menos 500MB de espacio libre en disco.', mbError, MB_OK);
    Result := False;
  end;
end;

// Página personalizada de configuración
procedure CreateConfigPage();
var
  Page: TInputQueryWizardPage;
begin
  Page := CreateInputQueryPage(wpSelectTasks,
    'Configuración Inicial', 'Configure las opciones básicas del sistema',
    'Especifique la configuración inicial para EtiquetadorZPL:');
    
  Page.Add('Puerto del servidor web:', False);
  Page.Add('Carpeta principal de trabajo:', False);
  
  // Valores por defecto
  Page.Values[0] := '8002';
  Page.Values[1] := 'C:\EtiquetasFlex';
end;

[Registry]
; Registrar aplicación
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\EtiquetadorZPL"; ValueType: string; ValueName: "DisplayName"; ValueData: "EtiquetadorZPL"
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\EtiquetadorZPL"; ValueType: string; ValueName: "DisplayVersion"; ValueData: "1.0"
Root: HKLM; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\EtiquetadorZPL"; ValueType: string; ValueName: "Publisher"; ValueData: "Tu Empresa"

[UninstallDelete]
; Limpiar archivos generados
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\backups"
Type: filesandordirs; Name: "{app}\temp"
Type: files; Name: "{app}\*.log"
Type: files; Name: "{app}\*.db"