# Voice Mode (optional)

Claude Code does not include voice by default. [VoiceMode](https://github.com/mbailey/voicemode) is a community MCP server that lets you talk to Claude Code using an OpenAI-compatible STT/TTS service.

The README keeps the one-prompt setup. This page is the full install.

## One-prompt setup

Paste this inside a Claude Code session (macOS, Linux, and Windows WSL2):

```text
Set up VoiceMode for Claude Code using OpenAI Whisper (STT) and OpenAI TTS (speech output). Do the following steps in order:
1. Check if UV is installed (uv --version). If not, install it: curl -LsSf https://astral.sh/uv/install.sh | sh
2. Run: uvx voice-mode-install
3. Run: claude mcp add --scope user voicemode -- uvx --refresh voice-mode
4. Create or update ~/.voicemode/voicemode.env with these two lines:
   VOICEMODE_TTS_BASE_URLS=https://api.openai.com/v1
   VOICEMODE_STT_BASE_URLS=https://api.openai.com/v1
5. Check if OPENAI_API_KEY is set in the environment. If not, remind me to add it to ~/.zshrc and re-source it.
Tell me when each step completes and flag any errors before moving to the next step.
```

Restart Claude Code so the MCP server loads.

## Manual setup

Prerequisites: Python 3.14+, a microphone and speakers, and an OpenAI API key (or another OpenAI-compatible STT/TTS endpoint).

```bash
# 1. Install UV if needed
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install VoiceMode
uvx voice-mode-install

# 3. Register the MCP server
claude mcp add --scope user voicemode -- uvx --refresh voice-mode
```

```bash
export OPENAI_API_KEY=your-openai-key   # add to ~/.zshrc to persist

# ~/.voicemode/voicemode.env
VOICEMODE_TTS_BASE_URLS=https://api.openai.com/v1
VOICEMODE_STT_BASE_URLS=https://api.openai.com/v1
```

The MCP server reads `OPENAI_API_KEY` at startup. Restart Claude Code after setting it.

```bash
claude converse
```

Speak into the microphone. Say "stop" or press `Ctrl+C` to exit.

This kit does **not** pre-approve VoiceMode tools. Committed `settings.json` has no allow list. If prompts become noisy, add `mcp__voicemode__*` rules to `.claude/settings.local.json`. Do not use `--dangerously-skip-permissions` on a real project.

## Platform packages

**macOS** — usually works. If audio fails: `brew install portaudio ffmpeg`

**Ubuntu / Debian**

```bash
sudo apt update
sudo apt install -y ffmpeg libasound2-dev libasound2-plugins libportaudio2 portaudio19-dev python3-dev
```

**Fedora**

```bash
sudo dnf install alsa-lib-devel ffmpeg portaudio portaudio-devel python3-dev
```

**Windows (WSL2)**

```bash
sudo apt install -y ffmpeg libasound2-dev libasound2-plugins libportaudio2 portaudio19-dev pulseaudio pulseaudio-utils python3-dev
```

Clone and run Claude Code inside WSL, not on `/mnt/c/`.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "No audio input device" | System Settings → Privacy → Microphone |
| `[BLANK_AUDIO]` | Speak during the recording window; confirm default input |
| Audio choppy | Close other audio apps; prefer a wired headset |
| MCP not connecting | `/mcp` in Claude Code; restart after install |
| API key not picked up | Restart Claude Code |
