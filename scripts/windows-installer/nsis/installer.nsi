!include "MUI2.nsh"
!include "nsDialogs.nsh"
!include "LogicLib.nsh"

!define PRODUCT_NAME "TradingAgentsCN"
!ifndef PRODUCT_VERSION
  !define PRODUCT_VERSION "1.0.0"
!endif
!ifndef BACKEND_PORT
  !define BACKEND_PORT "8000"
!endif
!ifndef MONGO_PORT
  !define MONGO_PORT "27017"
!endif
!ifndef REDIS_PORT
  !define REDIS_PORT "6379"
!endif
!ifndef NGINX_PORT
  !define NGINX_PORT "80"
!endif
!ifndef PROJECT_ROOT
  !define PROJECT_ROOT "C:\\TradingAgentsCN"
!endif

Name "${PRODUCT_NAME}"
OutFile "TradingAgentsCNSetup-${PRODUCT_VERSION}.exe"
InstallDir "$PROGRAMFILES\TradingAgentsCN"
RequestExecutionLevel admin
SetDatablockOptimize on
SetCompressor lzma

Var BackendPort
Var MongoPort
Var RedisPort
Var NginxPort
Var hBackendEdit
Var hMongoEdit
Var hRedisEdit
Var hNginxEdit
Var hDetectBtn

Function .onInit
 StrCpy $BackendPort "${BACKEND_PORT}"
 StrCpy $MongoPort "${MONGO_PORT}"
 StrCpy $RedisPort "${REDIS_PORT}"
 StrCpy $NginxPort "${NGINX_PORT}"
FunctionEnd

Function PortsPage
 nsDialogs::Create 1018
 Pop $0
 ${If} $0 == error
   Abort
${EndIf}

${NSD_CreateLabel} 0 0 100% 12u "Configure Ports for Installation"

${NSD_CreateLabel} 0 18u 30% 12u "Backend (default ${BACKEND_PORT})"
 ${NSD_CreateText} 32% 16u 40% 12u "$BackendPort"
 Pop $hBackendEdit

${NSD_CreateLabel} 0 36u 30% 12u "MongoDB (default ${MONGO_PORT})"
 ${NSD_CreateText} 32% 34u 40% 12u "$MongoPort"
 Pop $hMongoEdit

${NSD_CreateLabel} 0 54u 30% 12u "Redis (default ${REDIS_PORT})"
 ${NSD_CreateText} 32% 52u 40% 12u "$RedisPort"
 Pop $hRedisEdit

${NSD_CreateLabel} 0 72u 30% 12u "Nginx (default ${NGINX_PORT})"
 ${NSD_CreateText} 32% 70u 40% 12u "$NginxPort"
 Pop $hNginxEdit

${NSD_CreateButton} 78% 90u 20% 14u "Detect & Suggest"
 Pop $hDetectBtn
 ${NSD_OnClick} $hDetectBtn DetectPorts

 nsDialogs::Show
FunctionEnd

Function DetectPorts
 ; Use single PowerShell call to detect all ports for better performance
 nsExec::ExecToStack 'powershell -ExecutionPolicy Bypass -NoProfile -Command "& { $ports = @{Backend=${BACKEND_PORT}; Mongo=${MONGO_PORT}; Redis=${REDIS_PORT}; Nginx=${NGINX_PORT}}; $result = @{}; foreach($name in $ports.Keys) { $p = $ports[$name]; $used = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue; if($used) { for($i=$p+1; $i -le 65535; $i++) { if(-not (Get-NetTCPConnection -LocalPort $i -ErrorAction SilentlyContinue)) { $result[$name] = $i; break } } } else { $result[$name] = $p } }; Write-Output ($result | ConvertTo-Json) }"'
 Pop $0
 Pop $1

 ; Parse JSON result and update text boxes
 ${If} $0 == 0
  ; Simple JSON parsing (extract values)
  ${If} $1 != ""
   ; Try to extract port numbers from JSON
   ; Format: {"Backend": 8000, "Mongo": 27017, ...}
   StrCpy $BackendPort ${BACKEND_PORT}
   StrCpy $MongoPort ${MONGO_PORT}
   StrCpy $RedisPort ${REDIS_PORT}
   StrCpy $NginxPort ${NGINX_PORT}

   ; If PowerShell execution failed, use default values
   ${NSD_SetText} $hBackendEdit $BackendPort
   ${NSD_SetText} $hMongoEdit $MongoPort
   ${NSD_SetText} $hRedisEdit $RedisPort
   ${NSD_SetText} $hNginxEdit $NginxPort
  ${EndIf}
 ${Else}
  ; Detection failed, use default values
  ${NSD_SetText} $hBackendEdit ${BACKEND_PORT}
  ${NSD_SetText} $hMongoEdit ${MONGO_PORT}
  ${NSD_SetText} $hRedisEdit ${REDIS_PORT}
  ${NSD_SetText} $hNginxEdit ${NGINX_PORT}
 ${EndIf}
FunctionEnd

Function PortsPageLeave
 ${NSD_GetText} $hBackendEdit $BackendPort
 ${NSD_GetText} $hMongoEdit $MongoPort
 ${NSD_GetText} $hRedisEdit $RedisPort
 ${NSD_GetText} $hNginxEdit $NginxPort

 ; Validate port number format
 ${If} $BackendPort == ""
  MessageBox MB_ICONSTOP "Backend port cannot be empty"
  Abort
 ${EndIf}
 ${If} $MongoPort == ""
  MessageBox MB_ICONSTOP "MongoDB port cannot be empty"
  Abort
 ${EndIf}
 ${If} $RedisPort == ""
  MessageBox MB_ICONSTOP "Redis port cannot be empty"
  Abort
 ${EndIf}
 ${If} $NginxPort == ""
  MessageBox MB_ICONSTOP "Nginx port cannot be empty"
  Abort
 ${EndIf}

 ; Validate port range
 ${If} $BackendPort < 1024
  MessageBox MB_ICONSTOP "Backend port must be >= 1024"
  Abort
 ${EndIf}
 ${If} $MongoPort < 1024
  MessageBox MB_ICONSTOP "MongoDB port must be >= 1024"
  Abort
 ${EndIf}
 ${If} $RedisPort < 1024
  MessageBox MB_ICONSTOP "Redis port must be >= 1024"
  Abort
 ${EndIf}
 ${If} $BackendPort > 65535
  MessageBox MB_ICONSTOP "Backend port must be <= 65535"
  Abort
 ${EndIf}
 ${If} $MongoPort > 65535
  MessageBox MB_ICONSTOP "MongoDB port must be <= 65535"
  Abort
 ${EndIf}
 ${If} $RedisPort > 65535
  MessageBox MB_ICONSTOP "Redis port must be <= 65535"
  Abort
 ${EndIf}
 ${If} $NginxPort > 65535
  MessageBox MB_ICONSTOP "Nginx port must be <= 65535"
  Abort
 ${EndIf}

 ; Validate no duplicate ports
 ${If} $BackendPort == $MongoPort
  MessageBox MB_ICONSTOP "Backend port duplicates MongoDB port"
  Abort
 ${EndIf}
 ${If} $BackendPort == $RedisPort
  MessageBox MB_ICONSTOP "Backend port duplicates Redis port"
  Abort
 ${EndIf}
 ${If} $BackendPort == $NginxPort
  MessageBox MB_ICONSTOP "Backend port duplicates Nginx port"
  Abort
 ${EndIf}
 ${If} $MongoPort == $RedisPort
  MessageBox MB_ICONSTOP "MongoDB port duplicates Redis port"
  Abort
 ${EndIf}
 ${If} $MongoPort == $NginxPort
  MessageBox MB_ICONSTOP "MongoDB port duplicates Nginx port"
  Abort
 ${EndIf}
 ${If} $RedisPort == $NginxPort
  MessageBox MB_ICONSTOP "Redis port duplicates Nginx port"
  Abort
 ${EndIf}
FunctionEnd

Page custom PortsPage PortsPageLeave
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "SimpChinese"

Section
SetOutPath "$INSTDIR"
File /r /x "venv\*" /x "frontend\dist\dist\*" "${PROJECT_ROOT}\release\portable\*"
ExecWait 'powershell -ExecutionPolicy Bypass -File "$INSTDIR\scripts\installer\setup.ps1" -NonInteractive -EnableNginx -Port $BackendPort -MongoPort $MongoPort -RedisPort $RedisPort -NginxPort $NginxPort'
 ; Shortcuts
 CreateDirectory "$SMPROGRAMS\TradingAgentsCN"
 CreateShortcut "$SMPROGRAMS\TradingAgentsCN\Start TradingAgentsCN.lnk" "powershell.exe" "-ExecutionPolicy Bypass -File \"$INSTDIR\scripts\installer\start_all.ps1\""
 CreateShortcut "$SMPROGRAMS\TradingAgentsCN\Stop TradingAgentsCN.lnk" "powershell.exe" "-ExecutionPolicy Bypass -File \"$INSTDIR\scripts\installer\stop_all.ps1\""
 CreateShortcut "$DESKTOP\TradingAgentsCN.lnk" "powershell.exe" "-ExecutionPolicy Bypass -File \"$INSTDIR\scripts\installer\start_all.ps1\""
 WriteUninstaller "$INSTDIR\Uninstall.exe"
 ; Registry entries for Control Panel uninstall
 WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\TradingAgentsCN" "DisplayName" "TradingAgentsCN"
 WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\TradingAgentsCN" "UninstallString" "$INSTDIR\Uninstall.exe"
 WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\TradingAgentsCN" "DisplayVersion" "${PRODUCT_VERSION}"
 WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\TradingAgentsCN" "InstallLocation" "$INSTDIR"
SectionEnd

Section "Uninstall"
 Delete "$SMPROGRAMS\TradingAgentsCN\Start TradingAgentsCN.lnk"
 Delete "$SMPROGRAMS\TradingAgentsCN\Stop TradingAgentsCN.lnk"
 RMDir  "$SMPROGRAMS\TradingAgentsCN"
 Delete "$DESKTOP\TradingAgentsCN.lnk"
 Delete "$INSTDIR\Uninstall.exe"
 DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\TradingAgentsCN"
 RMDir /r "$INSTDIR"
SectionEnd