# Documentation

Guides moved out of the public README. Start with the [README](../README.md), then open a page below when you need depth.

| Guide | When to read it |
|-------|-----------------|
| [Claude-Mem](getting-started/claude-mem.md) | Optional persistent memory and team sharing |
| [Voice Mode](getting-started/voice-mode.md) | Optional STT/TTS setup |
| [Hands-on exercises](examples/hands-on-exercises.md) | Practice scaffolds and agents in this repo |
| [Security](security.md) | Hooks, secrets, SAST, and the real-project checklist |
| [Troubleshooting](troubleshooting.md) | PATH, MCP, Windows/WSL, `claude doctor` |
| [Customizing the kit](engineering/customizing.md) | Add or remove agents, commands, skills, hooks |
| [CI/CD](engineering/cicd.md) | Toolkit workflows and `@deployment-engineer` |
| [Terraform / GCP](engineering/terraform.md) | `@terraform-specialist` provisioning |
| [iOS App Store release](mobile/ios-app-store-release.md) | ASC skills and XcodeBuildMCP |
| [Android Google Play release](mobile/android-google-play-release.md) | GPD skills and AAB upload |
| [Notes](articles.md) | Author write-ups |
| [Nx + Melos polyglot architecture (MONO-ARCH-001)](Nx_Melos_Polyglot_Monorepo_Architecture_Spec.md) | Four modes, Flutter bridge, graph/affected/cache rules |

Skill, agent, and command catalog: [`.claude/SKILLS_GUIDE.md`](../.claude/SKILLS_GUIDE.md). Polyglot modes (native-only / Melos-only / Nx-only / Nx + Melos): [MONO-ARCH-001](Nx_Melos_Polyglot_Monorepo_Architecture_Spec.md), [README — Polyglot monorepo](../README.md#polyglot-monorepo-native-only-melos-only-nx-only-nx--melos) and [`.claude/skills/polyglot-monorepo/SKILL.md`](../.claude/skills/polyglot-monorepo/SKILL.md).

Existing design-system verification notes stay in [`plans/`](plans/).
