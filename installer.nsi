Unicode true
ManifestSupportedOS win10
RequestExecutionLevel admin

!define APP_NAME "Sijill Warehouse"
!define APP_EXE "Sijill Warehouse.exe"
!define APP_VERSION "1.0.0"
!define INSTALL_DIR "$PROGRAMFILES64\${APP_NAME}"

Name "${APP_NAME}"
Caption "تثبيت ${APP_NAME}"
OutFile "dist\Sijill Warehouse-1.0.0-Setup.exe"
InstallDir "${INSTALL_DIR}"
InstallDirRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "InstallLocation"

VIProductVersion "1.0.0.0"
VIAddVersionKey /LANG=0 "ProductName" "${APP_NAME}"
VIAddVersionKey /LANG=0 "CompanyName" "م. باسل أشرف"
VIAddVersionKey /LANG=0 "FileDescription" "نظام سِجِلّ المخازن - أرشيف مستندات المخازن"
VIAddVersionKey /LANG=0 "FileVersion" "${APP_VERSION}"
VIAddVersionKey /LANG=0 "LegalCopyright" "م. باسل أشرف - 01014543845"

SetCompressor /SOLID lzma
SetCompressorDictSize 64

!include "MUI2.nsh"
!define MUI_ABORTWARNING
!define MUI_ICON "${__FILEDIR__}\sijill.ico"
!define MUI_UNICON "${__FILEDIR__}\sijill.ico"
!define MUI_WELCOMEPAGE_TITLE "مرحباً بك في تثبيت سِجِلّ المخازن"
!define MUI_WELCOMEPAGE_TEXT "سيتم تثبيت تطبيق سِجِلّ المخازن على جهازك. لا يحتاج التطبيق إلى Python أو Node.js أو أي برامج إضافية للعمل."
!define MUI_FINISHPAGE_RUN "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT "تشغيل سِجِلّ المخازن"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "Arabic"
!insertmacro MUI_LANGUAGE "English"

Section "Application" SEC_APP
  SectionIn RO
  SetOutPath "$INSTDIR"
  File /r "dist\win-unpacked\*"
  File "sijill.ico"
  WriteUninstaller "$INSTDIR\Uninstall.exe"

  CreateDirectory "$SMPROGRAMS\${APP_NAME}"
  CreateShortcut "$SMPROGRAMS\${APP_NAME}\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\sijill.ico" 0
  CreateShortcut "$DESKTOP\${APP_NAME}.lnk" "$INSTDIR\${APP_EXE}" "" "$INSTDIR\sijill.ico" 0

  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "Publisher" "م. باسل أشرف"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "UninstallString" "$INSTDIR\Uninstall.exe"
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "NoModify" 1
  WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}" "NoRepair" 1
SectionEnd

Section "Uninstall"
  Delete "$DESKTOP\${APP_NAME}.lnk"
  RMDir /r "$SMPROGRAMS\${APP_NAME}"
  DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
  RMDir /r "$INSTDIR"
SectionEnd
