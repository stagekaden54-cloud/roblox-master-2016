param(
    [string]$ContribPath = $env:CONTRIB_PATH,
    [ValidateSet("Debug", "NoOpt", "Release")]
    [string]$Configuration = "Debug"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$script:Checks = @()

function Add-Check {
    param([string]$Name, [string]$Path, [bool]$Required = $true)
    $script:Checks += [pscustomobject]@{
        Name = $Name
        Path = $Path
        Required = $Required
        Exists = (Test-Path -LiteralPath $Path)
    }
}

# Files and tools tracked in this repository.
Add-Check "Windows client project" (Join-Path $RepoRoot "WindowsClient\WindowsClient.vcxproj")
Add-Check "Visual Studio solution" (Join-Path $RepoRoot "Client_2012.sln")
Add-Check "Core script converter" (Join-Path $RepoRoot "CoreScriptConverter2\tool\win32\rsc.exe")
Add-Check "Shader compiler (x86)" (Join-Path $RepoRoot "Rendering\ShaderCompiler\ShaderCompiler.exe")
Add-Check "Shader compiler (x64)" (Join-Path $RepoRoot "Rendering\ShaderCompiler\ShaderCompiler_x64.exe")
Add-Check "FMOD headers" (Join-Path $RepoRoot "fmod\include\fmod.hpp")
Add-Check "FMOD import library" (Join-Path $RepoRoot "fmod\win32\lib\fmod_vc.lib")
# TBB is required by active Debug|Win32 code, including scalable allocation
# calls in Base/rbx/Memory.cpp. Keep this check blocking until a compatible SDK
# is restored; do not silently compile without the allocator implementation.
Add-Check "TBB 4.1 headers (repository-relative)" (Join-Path $RepoRoot "TBB_4_1\include\tbb\tbb.h")
Add-Check "Core script converter config used by pre-build" (Join-Path $RepoRoot "CoreScriptConverter2\tool\rsc.config")
Add-Check "Core script config template" (Join-Path $RepoRoot "CoreScriptConverter2\rsc.config.template") $false

$missingContribPath = [string]::IsNullOrWhiteSpace($ContribPath)
if ($missingContribPath) {
    Write-Host "CONTRIB_PATH is not set. Pass -ContribPath or set the environment variable." -ForegroundColor Yellow
} else {
    $ContribPath = [System.IO.Path]::GetFullPath($ContribPath)

    # External dependency paths referenced by the Windows client and its project dependencies.
    Add-Check "Boost 1.56 headers" (Join-Path $ContribPath "boost_1_56_0\include\boost\version.hpp")
    Add-Check "Boost program_options sources" (Join-Path $ContribPath "boost_1_56_0\libs\program_options\src\options_description.cpp")
    Add-Check "SDL2 headers (project expects SDL2.0.4)" (Join-Path $ContribPath "SDL2.0.4\include\SDL.h")
    Add-Check "SDL2 Visual C++ import library" (Join-Path $ContribPath "SDL2\VisualC\Win32\Release\SDL2.lib")
    Add-Check "OpenSSL legacy libraries" (Join-Path $ContribPath "openssl\out32\ssleay32.lib")
    Add-Check "OpenSSL legacy crypto library" (Join-Path $ContribPath "openssl\out32\libeay32.lib")
    Add-Check "DirectShow base-class headers" (Join-Path $ContribPath "DSBaseClasses\Sources\streams.h")
    if ($Configuration -eq "Debug") {
        Add-Check "DirectShow Debug library" (Join-Path $ContribPath "DSBaseClasses\Lib\strmbasd.lib")
    } else {
        Add-Check "DirectShow library" (Join-Path $ContribPath "DSBaseClasses\Lib\strmbase.lib")
    }
    Add-Check "Windows SDK headers" (Join-Path $ContribPath "SDK\Include\d3d9.h")
    Add-Check "Windows SDK libraries folder" (Join-Path $ContribPath "SDK\Lib")
    Add-Check "zlib 1.2.8 headers" (Join-Path $ContribPath "windows\x86\zlib\zlib-1.2.8\include\zlib\zlib.h")
    Add-Check "zlib library" (Join-Path $ContribPath "windows\x86\zlib\zlib-1.2.8\lib\zlib.lib")
    Add-Check "libcurl 7.43 headers" (Join-Path $ContribPath "windows\x86\curl\curl-7.43.0\include\curl\curl.h")
    Add-Check "libcurl static library" (Join-Path $ContribPath "windows\x86\curl\curl-7.43.0\lib\libcurl_a.lib")
    Add-Check "cpp-netlib sources" (Join-Path $ContribPath "cpp-netlib-0.11.0-final\libs\network\src\uri\uri.cpp")
    Add-Check "W3C libwww source folder" (Join-Path $ContribPath "w3c-libwww-5.4.0\Library\src")
    # The Debug|Win32 source audit found no Telemetry references in the active
    # translation units or listed headers. Keep the configured include path visible,
    # but do not block Debug on an SDK that is not demonstrated to be used.
    $debugOnlyOptional = ($Configuration -eq "Debug")
    Add-Check "Telemetry SDK headers" (Join-Path $ContribPath "Telemetry\Telemetry2SDKWin32_20M\include") (-not $debugOnlyOptional)

    # VMProtect references in the Debug|Win32 source set are guarded by
    # I_AM_GOY_THAT_LOVES_VMPROTECT, which is absent from active Debug definitions.
    # Keep the SDK mandatory for NoOpt/Release; do not disable protection code.
    Add-Check "VMProtect SDK headers" (Join-Path $ContribPath "VMProtectWin_2.13") (-not $debugOnlyOptional)
    if ($Configuration -eq "Release") {
        Add-Check "VMProtect command-line packer" (Join-Path $ContribPath "VMProtectWin_2.13\VMProtect_Con.exe")
        Add-Check "VMProtect project file" (Join-Path $ContribPath "VMProtectWin_2.13\RobloxPlayer.exe.vmp")
        Add-Check "VMProtect key file" (Join-Path $ContribPath "VMProtectWin_2.13\VMProtect.key")
    }
}

Write-Host ""
Write-Host "Windows client prerequisite report" -ForegroundColor Cyan
Write-Host "Repository: $RepoRoot"
Write-Host "Configuration: $Configuration"
Write-Host "CONTRIB_PATH: $(if ($ContribPath) { $ContribPath } else { '<not set>' })"
Write-Host ""

$missingRequired = 0
if ($missingContribPath) {
    $missingRequired++
}
foreach ($check in $script:Checks) {
    if ($check.Exists) {
        Write-Host ("[OK]      {0}" -f $check.Name) -ForegroundColor Green
    } elseif ($check.Required) {
        Write-Host ("[MISSING] {0} -- {1}" -f $check.Name, $check.Path) -ForegroundColor Red
        $missingRequired++
    } else {
        Write-Host ("[OPTIONAL] {0} -- {1}" -f $check.Name, $check.Path) -ForegroundColor Yellow
    }
}

Write-Host ""
if ($missingRequired -gt 0) {
    Write-Host "$missingRequired required item(s) are missing. Resolve these before starting MSBuild." -ForegroundColor Red
    exit 1
}

Write-Host "All checked required paths exist. This is a prerequisite check, not proof that compilation or linking will succeed." -ForegroundColor Green
exit 0
