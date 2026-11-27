#if Ver != EncodeVer(6, 7, 4)
  #error Build Ratatoss with Inno Setup 6.7.4.
#endif

[Setup]
AppId={{65E60AFD-3F08-4FC7-9206-02E65C2ABC49}
AppName=Ratatoss
AppVersion={#ReleaseVersion}
DefaultDirName={localappdata}\Programs\Ratatoss
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
MinVersion=10.0.22000
ArchitecturesAllowed=x64os
ArchitecturesInstallIn64BitMode=x64os
OutputDir={#OutputPath}
OutputBaseFilename=Ratatoss-Setup-{#ReleaseVersion}-win-x64
UninstallDisplayIcon={app}\Ratatoss.exe
CloseApplications=yes
RestartApplications=no
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
LaunchRatatoss=Mở Ratatoss

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "{#DistributionPath}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Ratatoss\Ratatoss"; Filename: "{app}\Ratatoss.exe"; WorkingDir: "{localappdata}"
Name: "{userprograms}\Ratatoss\Ratatoss Terminal"; Filename: "{app}\Ratatoss-Terminal.exe"; WorkingDir: "{localappdata}"
Name: "{userdesktop}\Ratatoss"; Filename: "{app}\Ratatoss.exe"; WorkingDir: "{localappdata}"; Tasks: desktopicon

[Run]
Filename: "{app}\Ratatoss.exe"; Parameters: "--from-setup"; WorkingDir: "{localappdata}"; Description: "{cm:LaunchRatatoss}"; Flags: nowait postinstall skipifsilent
