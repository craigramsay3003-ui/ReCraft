#ifndef AppVersion
  #error AppVersion must be supplied by scripts/build_release.ps1
#endif
#ifndef ProjectRoot
  #error ProjectRoot must be supplied by scripts/build_release.ps1
#endif

#define AppName "ReCraft"
#define AppPublisher "Craig Ramsay"
#define AppExeName "ReCraft.exe"

[Setup]
AppId={{9E548267-4944-4CDA-82A9-806BDE339644}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir={#ProjectRoot}\dist
OutputBaseFilename=ReCraft-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile={#ProjectRoot}\src\recraft\assets\recraft.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "{#ProjectRoot}\dist\ReCraft\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\ReCraft"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\ReCraft"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch ReCraft"; Flags: nowait postinstall skipifsilent
