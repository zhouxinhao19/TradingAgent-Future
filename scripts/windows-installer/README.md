# Windows Installer Build Scripts

Successfully built installer at: scripts\windows-installer\nsis\TradingAgentsCNSetup-1.0.1.exe

## Quick Start

Build complete installer:
```powershell
.\build\build_installer.ps1 -Version "1.0.1"
```

Skip portable package build (use existing):
```powershell
.\build\build_installer.ps1 -Version "1.0.1" -SkipPortablePackage
```

## Architecture

Two-layer approach:
1. Portable package (green version) - tested standalone package
2. NSIS installer wrapper - adds UI, shortcuts, registry integration

## Output

- Installer: scripts\windows-installer\nsis\TradingAgentsCNSetup-{VERSION}.exe
- Size: ~320 MB (compressed from ~1.3GB portable package)
