[Setup]
AppName=EtiquetadorZPL
AppVersion=1.0
AppPublisher=Tu Empresa
DefaultDirName={autopf}\EtiquetadorZPL
DefaultGroupName=EtiquetadorZPL
OutputDir=installer
OutputBaseFilename=EtiquetadorZPL_Setup
SetupIconFile=etiquetador_icon.ico
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
Source: "dist\EtiquetadorZPL.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "web\*"; DestDir: "{app}\web"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "poppler\*"; DestDir: "{app}\poppler"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "MANUAL_USUARIO.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\EtiquetadorZPL"; Filename: "{app}\EtiquetadorZPL.exe"
Name: "{group}\Dashboard Web"; Filename: "http://localhost:8002/web/"
Name: "{group}\{cm:UninstallProgram,EtiquetadorZPL}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\EtiquetadorZPL"; Filename: "{app}\EtiquetadorZPL.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\EtiquetadorZPL.exe"; Description: "Ejecutar EtiquetadorZPL"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // Crear carpetas de trabajo
    ForceDirectories('C:\EtiquetasFlex');
    ForceDirectories('C:\EtiquetasFlex\Entrada1');
    ForceDirectories('C:\EtiquetasFlex\Historial1');
    
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