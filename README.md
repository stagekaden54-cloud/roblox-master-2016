# A Letter to Claude — BLOCK16 Project Context

Hello Claude,

I'm working on a project called **BLOCK16**. I want you to understand the project's identity and background before reviewing code or suggesting changes.

## What BLOCK16 is

BLOCK16 is my own independent client project. It is not an official Roblox product, is not affiliated with or endorsed by Roblox, and should not be described as Roblox's current proprietary source code simply because some repository or folder names contain the word "Roblox" or refer to an older client era.



The goal is to develop BLOCK16 as its own client and eventually deliver a reliable production version.

## Current project and development context

- Repository: `stagekaden54-cloud/roblox-master-2016`
- A successful Windows Debug build has already been completed through GitHub Actions.
- Successful run: [Windows Debug build #43729480303](https://github.com/stagekaden54-cloud/roblox-master-2016/actions/runs/43729480303)
- The successful job built the **Win32 (x86) Debug** configuration on a Windows Server 2022 runner.
- The project is being developed primarily through GitHub and GitHub Actions. I currently work mainly from an iPhone and do not have my own Windows development PC, so prefer workflows and instructions that can be carried out through GitHub when practical.

## Production roadmap

The next major goal is a separate Windows Release build and, eventually, a production-ready BLOCK16 package.

The agreed roadmap is:

1. Audit Release dependencies and confirm which required libraries and headers are available.
2. Validate the Release configurations of the required projects.
3. Create and test a separate Windows Release CI workflow.
4. Keep the already-successful Debug workflow intact.
5. Test the resulting executable in a clean Windows environment.
6. Create BLOCK16-specific packaging rather than blindly reusing outdated legacy packaging steps.
7. Run compatibility, stability, and security checks before calling anything a release candidate.

## Important technical cautions

- The main Windows client project has Debug, Release, and NoOpt Win32 configurations.
- The existing Release configuration and some post-build commands contain legacy naming and assumptions. Inspect them before changing or running them.
- Some old commands refer to names such as `RobloxPlayerBeta.exe`, while the current project uses BLOCK16 naming such as `BLOCK16Client.exe`. Verify the actual output paths and artifact names instead of assuming they match.
- The Release dependency checker already exists at `scripts/Check-WindowsClientPrerequisites.ps1`. Review and reuse it where appropriate.
- Release dependency checks include legacy libraries and components such as Boost, SDL2, OpenSSL, zlib, libcurl, DirectShow, TBB, telemetry-related headers, and VMProtect-related files. Verify actual availability and distinguish compile/link requirements from packaging or protection requirements.
- Do not remove or bypass security/protection functionality just to make a build pass. Explain the issue and propose a safe, reviewable solution.
- Never ask me to paste passwords, access tokens, private keys, signing keys, or other secrets into chat. Use secure repository/CI secret handling when genuinely required.
- Do not run unknown binaries from dependency archives. Inspect files and metadata safely.

## How I want you to work

1. Treat BLOCK16 as my project and take its development goals seriously.
2. Inspect the actual repository files and current branch before proposing edits.
3. Explain what a change does, why it is needed, and what it might affect.
4. Make small, focused changes that are easy to review.
5. Preserve the successful Debug build and its workflow while developing Release separately.
6. Do not claim a build, test, deployment, or fix succeeded unless the logs or results confirm it.
7. Do not replace large parts of the project or change architecture without explaining the trade-offs and getting my approval.
8. When a build fails, use the actual error logs to diagnose the cause rather than guessing.
9. Remember that Windows x86 is the current first production target, not necessarily the only platform BLOCK16 may support in the future.

Please begin by reading the existing workflows, project files, and prerequisite checker. Then report the current state and the safest next step before making significant changes.

Thank you for helping me develop BLOCK16.
