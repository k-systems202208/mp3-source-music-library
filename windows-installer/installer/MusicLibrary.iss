#define MyAppName "自宅音楽ライブラリ"
#define MyAppEnglishName "Music Library"
#define MyAppVersion "2.6.1"
#define MyAppPublisher "tojiii"
#define MyAppExeName "MusicLibrary.exe"
#define MyAppId "{{DDF12346-0D38-4D31-A4AF-27B406C91D8A}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\MusicLibrary
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=MusicLibrary-Setup-{#MyAppVersion}-x64
SetupIconFile=..\build\music-library.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
AppMutex=MusicLibraryLauncherMutex
InfoBeforeFile=..\docs\INSTALL_INFO.txt
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作成"; GroupDescription: "追加アイコン:"; Flags: unchecked
Name: "autostart"; Description: "Windowsログイン時に自動起動（外部接続を使う場合に推奨）"; GroupDescription: "追加設定:"; Flags: unchecked

[Files]
Source: "..\dist\MusicLibrary\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\docs\README_USER.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\MUTAGEN_LICENSE.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "..\docs\REMOTE_ACCESS_USER.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\docs\REMOTE_ACCESS_FAMILY.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\外部接続を設定"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--remote-setup"; WorkingDir: "{app}"
Name: "{group}\外部接続ガイド"; Filename: "{app}\REMOTE_ACCESS_USER.txt"
Name: "{group}\データ保存先を開く"; Filename: "{sys}\explorer.exe"; Parameters: """{localappdata}\MusicLibrary"""
Name: "{group}\アンインストール"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName}を起動"; Flags: nowait postinstall skipifsilent

