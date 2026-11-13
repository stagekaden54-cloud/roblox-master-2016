# Windows Client Build Notes

This document covers the first native Windows build of the client in this repository. It deliberately keeps the existing C++ implementation and legacy dependency versions unchanged.

## Target

- Solution: \`Client_2012.sln\`
- Project: \`WindowsClient/WindowsClient.vcxproj\`
- Initial configuration: \`Debug | Win32\` (x86)
- Output name: \`RobloxPlayerBetaRaw.exe\`
- Platform toolset in the project: \`v110\` (Visual Studio 2012)

The Windows client references the App, Base, Network, Log, Boost, Bullet Physics, GfxCore, and GfxRender projects. Build the solution/project graph rather than trying to compile \`WindowsClient.vcxproj\` as an isolated source file.

## Before building

1. Check out the \`modern-windows\` branch.
2. Open a Visual Studio developer command prompt with the legacy v110 toolset available.
3. Set \`CONTRIB_PATH\` to the directory containing the dependency folders described below.
4. Run the prerequisite checker from the repository root:

   \`\`\`powershell
   powershell -ExecutionPolicy Bypass -File .\\scripts\\Check-WindowsClientPrerequisites.ps1 -Configuration Debug
   \`\`\`

5. Resolve every \`[MISSING]\` entry before attempting the build.
6. Build \`Client_2012.sln\` using \`Debug | Win32\`.

For example, if the dependencies are in \`D:\\Trunk2016\\Contribs\`:

\`\`\`powershell
$env:CONTRIB_PATH = "D:\\Trunk2016\\Contribs"
.\\scripts\\Check-WindowsClientPrerequisites.ps1 -Configuration Debug
\`\`\`

The checker only inspects paths. It does not download, install, copy, or modify dependencies.

## Dependency path contract

The project files reference these external dependency roots beneath \`CONTRIB_PATH\`:

- \`boost_1_56_0\`
- \`SDL2.0.4\` (headers) and \`SDL2\\VisualC\\Win32\\Release\` (library)
- \`openssl\\out32\`
- \`DSBaseClasses\\Sources\` and \`DSBaseClasses\\Lib\`
- \`SDK\\Include\` and \`SDK\\Lib\`
- \`windows\\x86\\zlib\\zlib-1.2.8\`
- \`windows\\x86\\curl\\curl-7.43.0\`
- \`cpp-netlib-0.11.0-final\`
- \`w3c-libwww-5.4.0\`
- \`Telemetry\\Telemetry2SDKWin32_20M\`
- \`VMProtectWin_2.13\`

The repository also references \`TBB_4_1\` relative to the repository root and uses FMOD files under \`fmod\`.

## Known blockers and inconsistencies found during inspection

- The repository tree does not contain the expected root-level \`TBB_4_1\` directory.
- The Windows client pre-build command passes \`..\\rsc.config\`, which resolves to a root-level \`rsc.config\`; that file is not tracked. A template exists at \`CoreScriptConverter2/rsc.config.template\`, but its contents must be reviewed and configured before using it.
- SDL2 paths are inconsistent: project files refer to both \`SDL2.0.4\` and \`SDL2\`, while the repository contains a separate \`SDL2/Win/2.0.4\` binary layout. These are not automatically interchangeable.
- Several dependencies have some binaries or source fragments committed in the repository, but the active project files expect a different external \`CONTRIB_PATH\` layout. A checked-in file does not prove the linker is looking in that location.
- Release packaging invokes VMProtect tools and expects project/key files. These are not needed for the first Debug build and should remain outside the initial build attempt.
- The project uses the old \`v110\` toolset. Do not retarget every project to a modern compiler as a first fix; that would introduce a separate compatibility project.

## First build command

After the prerequisite checker reports no missing required paths, run this from a developer command prompt at the repository root:

\`\`\`bat
msbuild Client_2012.sln /m /t:WindowsClient /p:Configuration=Debug /p:Platform=Win32 /v:minimal
\`\`\`

If the solution target name is not accepted by the local MSBuild version, build the \`WindowsClient\` project directly in Visual Studio with the same configuration and platform.

## Important

A successful prerequisite report only means the listed paths exist. It does not prove the dependencies have compatible architectures, compiler settings, or binary interfaces. The first real build log is needed to identify the next compile or link error.
