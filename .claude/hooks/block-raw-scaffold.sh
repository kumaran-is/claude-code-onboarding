#!/bin/bash
# PreToolUse (Bash) hook — blocks raw project-creation commands unless the call carries an explicit,
# per-command scaffold authorization.
#
# Why: new projects must come from the scaffold commands (standard structure, pinned versions, design
# system). Sub-agents run headlessly, cannot invoke slash commands, and used to fall back to a raw
# `flutter create`, skipping that structure.
#
# Authorization (the scaffold commands do this themselves in their first step):
#   CC_SCAFFOLD=<scaffold-command-name> <raw creator command>
#   e.g.  CC_SCAFFOLD=scaffold-flutter-app flutter create --org com.example my_app
# - It applies to that single command only: nothing persists between calls, there is no state file
#   to leave behind, and it is visible in the transcript.
# - The value must name the scaffold command that owns that technology; a Flutter marker does not
#   authorize `ng new`.
# - Every authorized call is appended to <git dir>/claude-state/scaffold-audit.log (inside .git, never committed).
# Anything else that matches a raw creator is blocked (exit 2).
#
# Inert heredoc bodies: the body of `cat [>|>>] FILE <<'DELIM'` / `tee [-a] FILE <<'DELIM'` is data written to a
# file, so it is not scanned (report appends and notes that mention a creator used to be blocked). Only that exact
# shape, alone on its line, with a QUOTED delimiter (no $(...) or backtick expansion in the body) is exempt. A body
# fed to a shell or an interpreter (bash/sh/python/node <<, cat <<X | bash, $(cat <<X)), an unquoted delimiter, or a
# missing terminator is scanned as before (fail closed).
#
# Write advisory (PreToolUse Write, register the matcher as "Bash|Write"): creating a NEW angular.json, or a new
# src/main.ts, src/app/app.config.ts, tsconfig.app.json or tsconfig.spec.json inside an Angular workspace, prints
# a CLI-first reminder as additionalContext. Advisory only: exit 0, silent for existing files (overwrites/Edits).
#
# Nx / Melos workspace host files: creating a NEW nx.json or melos.yaml is blocked (human must
# approve Nx with CC_NX_INIT=1 npx nx init). Edits of an existing nx.json are allowed.
# Raw `nx init` / `create-nx-workspace` / `nx configure-ai-agents` need CC_NX_INIT=1 (there is
# no /scaffold-monorepo on purpose).
#
# Test: bash .claude/hooks/block-raw-scaffold.sh --selftest

state_dir_for() { # $1 project root -> runtime state dir inside its git dir (never the working tree); temp dir outside git
  local d
  if d=$(git -C "$1" rev-parse --git-common-dir 2>/dev/null); then
    case "$d" in /*) ;; *) d="$1/$d" ;; esac
    printf '%s/claude-state' "$d"
  else
    printf '%s/claude-state/%s' "${TMPDIR:-/tmp}" "$(printf '%s' "$1" | shasum | cut -c1-12)"
  fi
}
LOG_DIR=$(state_dir_for "${CLAUDE_PROJECT_DIR:-.}")

# <scaffold command>#<raw-creator ERE>#<label>#<technology>   ('#' is the field separator; the ERE may contain '|')
RULES=(
  'scaffold-flutter-app#flutter[[:space:]]+create#flutter create#Flutter / Dart'
  'scaffold-angular-app#(ng[[:space:]]+new|(npx|bunx|pnpm[[:space:]]+dlx|npm[[:space:]]+exec|yarn[[:space:]]+dlx)([[:space:]]+-[^[:space:]]+)*[[:space:]]+@angular/cli(@[^[:space:]]+)?[[:space:]]+new)#ng new / npx @angular/cli new#Angular'
  'scaffold-nestjs-api#((npx|bunx|pnpm[[:space:]]+dlx|npm[[:space:]]+exec|yarn[[:space:]]+dlx)([[:space:]]+-[^[:space:]]+)*[[:space:]]+@nestjs/cli(@[^[:space:]]+)?[[:space:]]+new|nest[[:space:]]+new)#npx @nestjs/cli new / nest new#NestJS'
  'scaffold-python-api#django-admin[[:space:]]+startproject#django-admin startproject#Python / Django'
  'scaffold-spring-api#(spring[[:space:]]+init|mvn[[:space:]]+archetype:generate)#spring init / mvn archetype:generate#Java / Spring Boot'
  'scaffold-react-app#((npm|pnpm|yarn|bun)[[:space:]]+(create|init)[[:space:]]+vite(@[^[:space:]]+)?|(npx|bunx|pnpm[[:space:]]+dlx|npm[[:space:]]+exec|yarn[[:space:]]+dlx)([[:space:]]+-[^[:space:]]+)*[[:space:]]+create-vite(@[^[:space:]]+)?|([^[:space:]]*/)?create-vite(@[^[:space:]]+)?)#npm create vite / npx create-vite#React (Vite)'
  'scaffold-react-app#(npx|bunx|pnpm[[:space:]]+dlx|npm[[:space:]]+exec|yarn[[:space:]]+dlx)([[:space:]]+-[^[:space:]]+)*[[:space:]]+(--[[:space:]]+)?shadcn(@[^[:space:]]+)?[[:space:]]+init([[:space:]]+[^;&|[:space:]]+)*[[:space:]]+(-t|--template|-n|--name)(=[^[:space:]]*)?#npx shadcn init --template / --name#React (shadcn new project)'
  'scaffold-react-app#((npm|pnpm|yarn|bun)[[:space:]]+(create|init)[[:space:]]+(next-app|react-router)(@[^[:space:]]+)?|(npx|bunx|pnpm[[:space:]]+dlx|npm[[:space:]]+exec|yarn[[:space:]]+dlx)([[:space:]]+-[^[:space:]]+)*[[:space:]]+create-(next-app|react-router)(@[^[:space:]]+)?|([^[:space:]]*/)?create-(next-app|react-router)(@[^[:space:]]+)?)#npm create next-app / create-react-router#React full-stack (Next.js, React Router framework mode)'
)

# Nx bring-up. Marker is CC_NX_INIT=1 (same class as CC_SCAFFOLD: visible in the transcript, not
# a human-proof token). <label>#<ERE>
NX_RULES=(
  'create-nx-workspace#(npx|bunx|pnpm[[:space:]]+dlx|yarn[[:space:]]+dlx|npm[[:space:]]+exec)([[:space:]]+-[^[:space:]]+)*[[:space:]]+create-nx-workspace(@[^[:space:]]+)?'
  'create-nx-workspace#(npm|pnpm|yarn|bun)[[:space:]]+(create|init)[[:space:]]+nx-workspace(@[^[:space:]]+)?'
  'create-nx-workspace#create-nx-workspace(@[^[:space:]]+)?'
  'nx init#(npx|bunx|pnpm[[:space:]]+dlx|yarn[[:space:]]+dlx|npm[[:space:]]+exec)([[:space:]]+-[^[:space:]]+)*[[:space:]]+nx(@[^[:space:]]+)?[[:space:]]+init'
  'nx init#(pnpm|yarn)[[:space:]]+nx[[:space:]]+init'
  'nx init#nx[[:space:]]+init'
  'nx configure-ai-agents#(npx|bunx|pnpm[[:space:]]+dlx|yarn[[:space:]]+dlx|npm[[:space:]]+exec)([[:space:]]+-[^[:space:]]+)*[[:space:]]+nx(@[^[:space:]]+)?[[:space:]]+configure-ai-agents'
  'nx configure-ai-agents#(pnpm|yarn)[[:space:]]+nx[[:space:]]+configure-ai-agents'
  'nx configure-ai-agents#nx[[:space:]]+configure-ai-agents'
)

block() { # $1 matched label, $2 scaffold command, $3 tech
  cat >&2 <<EOF
BLOCKED: raw project creation detected ($1, $3).
New projects must come from the scaffold command. In the MAIN session run the Skill tool:
    skill: "$2"   args: "<project-name>"
The scaffold command itself runs the raw creator with an explicit marker:
    CC_SCAFFOLD=$2 $1 ...
Sub-agents cannot invoke slash commands: run the scaffold first, then hand them the scaffolded path.
See .claude/skills/subagent-driven-development/reference/orchestration-and-context.md (Orchestrator Pre-Flight).
EOF
  exit 2
}

block_nx() { # $1 matched label
  cat >&2 <<EOF
BLOCKED: Nx workspace initialization detected ($1).
Ask the human first (polyglot-monorepo / MONO-ARCH-001). Approve a mode (native-only / melos-only / nx-only / nx-plus-melos). If they agreed, re-run THAT command only with:
    CC_NX_INIT=1 $1 ...
CC_NX_INIT is a visible transcript marker (same class as CC_SCAFFOLD), not a cryptographic human gate.
Never run nx configure-ai-agents on the onboarding kit. Product repos need nx.json first.
See .claude/skills/polyglot-monorepo/reference/nx-and-mcp.md.
EOF
  exit 2
}

strip_inert_heredocs() { # stdin: command text -> stdout: same text with inert heredoc bodies removed (see header)
  python3 -c '
import re, sys
text = sys.stdin.read()
lines = text.split("\n")
file_arg = r"[^\s;&|<>`$()]+"
head = re.compile(r"^[ \t]*(?:cat(?:[ \t]+>>?[ \t]*" + file_arg + r")?|tee(?:[ \t]+-a)?[ \t]+" + file_arg + r")"
                  r"[ \t]*<<(-?)[ \t]*([\x27\x22])([A-Za-z_][A-Za-z0-9_]*)\2"
                  r"(?:[ \t]*>>?[ \t]*" + file_arg + r")?[ \t]*$")
out, i = [], 0
while i < len(lines):
    m = head.match(lines[i])
    out.append(lines[i])
    i += 1
    if not m:
        continue
    term = re.compile(r"^" + ("\t*" if m.group(1) else "") + re.escape(m.group(3)) + r"$")
    j = i
    while j < len(lines) and not term.match(lines[j]):
        j += 1
    if j == len(lines):          # no terminator: keep everything (fail closed)
        continue
    i = j                         # drop the body, keep the terminator line
sys.stdout.write("\n".join(out))
'
}

evaluate() { # $1 = command text. Exits 2 via block() on a violation; returns 0 otherwise.
  local cmd="$1" rule name rx label tech lead remaining stripped nx_redir nx_add_remaining
  lead='(^|[;&|(`][[:space:]]*)([A-Za-z_][A-Za-z0-9_]*=[^[:space:]]*[[:space:]]+)*'
  # Inert heredoc bodies are data, not commands. Any failure keeps the original text (fail closed).
  stripped=$(printf '%s' "$cmd" | strip_inert_heredocs 2>/dev/null) && [ -n "$stripped" ] && cmd="$stripped"
  for rule in "${RULES[@]}"; do
    IFS='#' read -r name rx label tech <<<"$rule"
    # Replace each AUTHORIZED occurrence with a neutral token, then see whether a raw one is left.
    # '#' is the sed delimiter because the creator patterns contain '/'. If sed fails, keep the original
    # command so the raw check below still runs (fail closed, never fail open).
    remaining=$(printf '%s' "$cmd" | sed -E "s#(^|[;&|(\`][[:space:]]*)CC_SCAFFOLD=${name}[[:space:]]+${rx}#\1AUTHORIZED_SCAFFOLD#g" 2>/dev/null) || remaining="$cmd"
    [ -n "$remaining" ] || remaining="$cmd"
    if printf '%s' "$remaining" | grep -qE "${lead}${rx}([[:space:]]|\$)"; then
      block "$label" "$name" "$tech"
    fi
    if [ "$remaining" != "$cmd" ]; then
      mkdir -p "$LOG_DIR" 2>/dev/null && printf '%s | %s | %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$name" "$(printf '%s' "$cmd" | head -c 200)" >> "$LOG_DIR/scaffold-audit.log" 2>/dev/null
    fi
  done
  # React Native has no scaffold command yet: warn only (stderr), never block.
  if printf '%s' "$cmd" | grep -qE '(npx[[:space:]]+react-native[[:space:]]+init|npx[[:space:]]+create-expo-app|npx[[:space:]]+@react-native-community/cli[[:space:]]+init)([[:space:]]|$)'; then
    echo "WARNING: raw React Native project creation; consider the mobile-developer skill first (no scaffold command exists)." >&2
  fi
  # Nx bring-up: same command-start rules; authorization is CC_NX_INIT=1 immediately before the creator.
  local nx_rule nx_label nx_rx nx_remaining
  for nx_rule in "${NX_RULES[@]}"; do
    IFS='#' read -r nx_label nx_rx <<<"$nx_rule"
    nx_remaining=$(printf '%s' "$cmd" | sed -E "s#(^|[;&|(\`][[:space:]]*)CC_NX_INIT=1[[:space:]]+${nx_rx}#\1AUTHORIZED_NX#g" 2>/dev/null) || nx_remaining="$cmd"
    [ -n "$nx_remaining" ] || nx_remaining="$cmd"
    if printf '%s' "$nx_remaining" | grep -qE "${lead}${nx_rx}([[:space:]]|\$)"; then
      block_nx "$nx_label"
    fi
  done
  if printf '%s' "$cmd" | grep -qE 'nx(@[^[:space:]]+)?[[:space:]]+configure-ai-agents' \
    && [ -d "${CLAUDE_PROJECT_DIR:-.}/.claude/skills/polyglot-monorepo" ]; then
    echo "BLOCKED: nx configure-ai-agents is never allowed on the onboarding kit (would rewrite CLAUDE.md / MCP)." >&2
    exit 2
  fi
  # Bash redirects that create nx.json (Write tool is a separate path).
  nx_redir=$(printf '%s' "$cmd" | sed -E 's#(^|[;&|(`][[:space:]]*)CC_NX_INIT=1[[:space:]]+#\1AUTHORIZED_NX #g' 2>/dev/null) || nx_redir="$cmd"
  if printf '%s' "$nx_redir" | grep -qE '(>|>>|tee[[:space:]]+(-a[[:space:]]+)?)[[:space:]]*(\./)?nx\.json([[:space:]]|$)'; then
    block_nx 'write nx.json'
  fi
  # nx add / nx g @nx/... installs Nx plugins. Allow when nx.json already exists; block as bring-up otherwise.
  if [ ! -f "${CLAUDE_PROJECT_DIR:-.}/nx.json" ]; then
    nx_add_remaining=$(printf '%s' "$cmd" | sed -E 's#(^|[;&|(`][[:space:]]*)CC_NX_INIT=1[[:space:]]+#\1AUTHORIZED_NX #g' 2>/dev/null) || nx_add_remaining="$cmd"
    if printf '%s' "$nx_add_remaining" | grep -qE "${lead}((npx|bunx|pnpm[[:space:]]+dlx|yarn[[:space:]]+dlx|npm[[:space:]]+exec)([[:space:]]+-[^[:space:]]+)*[[:space:]]+)?(pnpm[[:space:]]+|yarn[[:space:]]+)?nx(@[^[:space:]]+)?[[:space:]]+(add|g|generate)[[:space:]]+@nx/"; then
      block_nx 'nx add / generate @nx'
    fi
  fi
  return 0
}

block_new_workspace_file() { # $1 file path. Exit 2 on a NEW nx.json or melos.yaml; existing files allowed.
  local f="$1" base
  [ -n "$f" ] || return 0
  [ -e "$f" ] && return 0
  base=$(basename "$f")
  case "$base" in
    nx.json)
      echo "BLOCKED: creating nx.json requires explicit human approval (polyglot-monorepo). If they approved: CC_NX_INIT=1 npx nx init — do not Write nx.json." >&2
      exit 2
      ;;
    melos.yaml)
      echo "BLOCKED: Melos 7+ configures from the root pubspec.yaml (workspace: + melos:). Do not add melos.yaml. See flutter-mobile / polyglot-monorepo." >&2
      exit 2
      ;;
  esac
  return 0
}

ANGULAR_CLI_FIRST_MSG="Angular scaffolding is CLI-first: create workspaces with /scaffold-angular-app and files with \`npm exec --no -- ng generate …\` (.claude/rules/web-frontend.md)."
in_angular_workspace() { # $1 dir: an ancestor (or itself) holds angular.json or a package.json with @angular/core
  local d="$1"
  while [ -n "$d" ] && [ "$d" != "/" ] && [ "$d" != "." ]; do
    [ -f "$d/angular.json" ] && return 0
    [ -f "$d/package.json" ] && grep -qE '"@angular/core"[[:space:]]*:' "$d/package.json" && return 0
    d=$(dirname "$d")
  done
  return 1
}
write_advisory() { # $1 tool name, $2 file path. Prints PreToolUse additionalContext JSON or nothing. Always returns 0.
  local tool="$1" f="$2" dir hit=0
  [ "$tool" = Write ] && [ -n "$f" ] || return 0
  [ -e "$f" ] && return 0                                  # overwrite of an existing file: not a scaffold
  case "$f" in
    */angular.json|angular.json) hit=1 ;;
    */src/main.ts|*/src/app/app.config.ts|*/tsconfig.app.json|*/tsconfig.spec.json|src/main.ts|src/app/app.config.ts|tsconfig.app.json|tsconfig.spec.json)
      dir=$(dirname "$f"); in_angular_workspace "$dir" && hit=1 ;;
  esac
  [ "$hit" -eq 1 ] || return 0
  MSG="$ANGULAR_CLI_FIRST_MSG ($f)" python3 -c 'import json,os;print(json.dumps({"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":os.environ["MSG"]}}))'
  return 0
}

selftest() {
  local fail=0 t
  t=$(mktemp -d); LOG_DIR="$t"
  chk() { # label expected(0|2) command
    ( evaluate "$3" ) >/dev/null 2>&1; local rc=$?
    if [ "$rc" = "$2" ]; then echo "  ok   $1"; else echo "  FAIL $1 (exit $rc, want $2)"; fail=1; fi
  }
  chk "positive: bare flutter create is blocked"                         2 'flutter create my_app'
  chk "positive: chained flutter create is blocked"                      2 'cd /tmp && flutter create my_app'
  chk "positive: ng new / nest new / django / spring blocked"            2 'ng new web'
  chk "positive: npx @angular/cli@latest new blocked"                    2 'npx @angular/cli@latest new web'
  chk "negative: authorized angular scaffold is allowed"                 0 'CC_SCAFFOLD=scaffold-angular-app npx @angular/cli@latest new web --style=scss'
  chk "positive: npx @nestjs/cli new blocked"                            2 'npx @nestjs/cli new api'
  chk "positive: nest new blocked"                                       2 'nest new api'
  chk "positive: django-admin startproject blocked"                      2 'django-admin startproject site'
  chk "positive: mvn archetype:generate blocked"                         2 'mvn archetype:generate -DgroupId=a'
  chk "negative: authorized flutter create is allowed"                   0 'CC_SCAFFOLD=scaffold-flutter-app flutter create --org com.example my_app'
  chk "negative: authorized after cd is allowed"                         0 'cd /tmp/x && CC_SCAFFOLD=scaffold-flutter-app flutter create app'
  chk "negative: authorized nestjs is allowed"                           0 'CC_SCAFFOLD=scaffold-nestjs-api npx @nestjs/cli new api --skip-git'
  chk "adversarial: marker for the WRONG technology is blocked"          2 'CC_SCAFFOLD=scaffold-angular-app flutter create my_app'
  chk "adversarial: made-up marker value is blocked"                     2 'CC_SCAFFOLD=yes flutter create my_app'
  chk "adversarial: second raw create after an authorized one is blocked" 2 'CC_SCAFFOLD=scaffold-flutter-app flutter create a; flutter create b'
  chk "adversarial: marker on an unrelated command does not authorize"   2 'CC_SCAFFOLD=scaffold-flutter-app echo hi; flutter create b'
  chk "positive: npm create vite is blocked"                             2 'npm create vite@9.3.4 web -- --template react-ts'
  chk "positive: npx create-vite after cd is blocked"                    2 'cd /tmp && npx create-vite@9.3.4 web --template react-ts'
  chk "negative: authorized react scaffold is allowed"                   0 'CC_SCAFFOLD=scaffold-react-app npx create-vite@9.3.4 web --template react-ts --no-interactive'
  chk "adversarial: angular marker does not authorize create-vite"       2 'CC_SCAFFOLD=scaffold-angular-app npx create-vite@9.3.4 web'
  chk "negative: the exact documented react scaffold is allowed"          0 'CC_SCAFFOLD=scaffold-react-app npx --yes create-vite@9.3.4 web --template react-ts --no-interactive --no-immediate'
  chk "positive: npx --yes create-vite without marker is blocked"        2 'npx --yes create-vite@9.3.4 web --template react-ts'
  chk "positive: bunx create-vite is blocked"                            2 'bunx create-vite web'
  chk "positive: pnpm dlx create-vite is blocked"                        2 'pnpm dlx create-vite web'
  chk "positive: npm exec -- create-vite is blocked"                     2 'npm exec -- create-vite web'
  chk "positive: local .bin/create-vite is blocked"                      2 './node_modules/.bin/create-vite web'
  chk "positive: create-vite in a subshell is blocked"                   2 '(cd /tmp && npx create-vite web)'
  chk "positive: create-vite in command substitution is blocked"         2 'echo $(npx create-vite web)'
  chk "positive: npx -y @angular/cli new is blocked"                     2 'npx -y @angular/cli@22.3.0 new web'
  chk "negative: the exact documented angular 22 scaffold is allowed"    0 'CC_SCAFFOLD=scaffold-angular-app npx @angular/cli@22.3.0 new web --style=css --ssr=false --skip-git --defaults'
  chk "positive: npm exec @angular/cli@22.3.0 new without marker blocked" 2 'npm exec --yes -- @angular/cli@22.3.0 new web --defaults'
  chk "negative: text that only mentions create-vite"                    0 'grep -rn "create-vite" docs'
  chk "positive: npm exec create-next-app is blocked"                    2 'npm exec --yes -- create-next-app@16.4.6 web --ts --app --yes'
  chk "positive: npx create-react-router is blocked"                     2 'npx create-react-router@8.5.2 web --yes'
  chk "positive: npm create next-app is blocked"                         2 'npm create next-app@16.4.6 web'
  chk "positive: pnpm create react-router is blocked"                    2 'pnpm create react-router@8.5.2 web'
  chk "positive: local .bin/create-next-app is blocked"                  2 './node_modules/.bin/create-next-app web'
  chk "negative: authorized next scaffold is allowed"                    0 'CC_SCAFFOLD=scaffold-react-app npm exec --yes -- create-next-app@16.4.6 web --ts --app --yes'
  chk "negative: authorized react-router scaffold is allowed"            0 'CC_SCAFFOLD=scaffold-react-app npm exec --yes -- create-react-router@8.5.2 web --yes'
  chk "adversarial: angular marker does not authorize create-next-app"   2 'CC_SCAFFOLD=scaffold-angular-app npx create-next-app@16.4.6 web'
  chk "positive: shadcn init --template (new project) is blocked"       2 'npx shadcn@4.23.0 init --name my-app --preset base-nova --template vite'
  chk "positive: shadcn init -t=vite is blocked"                         2 'pnpm dlx shadcn@4.23.0 init -t=vite -y'
  chk "negative: documented shadcn init in an existing app is allowed"   0 'npx shadcn@4.23.0 init --base base -p nova --yes --no-monorepo </dev/null'
  chk "negative: shadcn add is untouched"                                0 'npx shadcn@4.23.0 add button card </dev/null'
  chk "negative: authorized shadcn template init is allowed"             0 'CC_SCAFFOLD=scaffold-react-app npx shadcn@4.23.0 init --name web --template vite --base base -p nova -y'
  chk "negative: next build/start are untouched"                         0 'npx next build && npm run start'
  chk "negative: text that only mentions create-next-app"                0 'grep -rn "create-next-app" docs'
  chk "negative: vite build/dev commands are untouched"                  0 'npx vite build && npm run dev && npx vitest run'
  chk "negative: unrelated flutter commands are untouched"               0 'flutter pub get && flutter test && flutter analyze'
  chk "negative: text that only mentions flutter create"                 0 'grep -rn "flutter create" docs'
  chk "negative: ordinary commands are untouched"                        0 'ls -la && git status'
  # inert heredoc bodies (report appends, notes) are not commands; anything executable still is
  chk "positive: npx create-nx-workspace is blocked"                   2 'npx create-nx-workspace@latest myorg'
  chk "positive: nx init is blocked"                                   2 'nx init'
  chk "positive: npx nx init is blocked"                               2 'npx nx init'
  chk "positive: nx configure-ai-agents is blocked"                    2 'npx nx configure-ai-agents'
  chk "positive: CC_NX_INIT=1 configure-ai-agents on kit is blocked"  2 'CC_NX_INIT=1 nx configure-ai-agents'
  chk "negative: CC_NX_INIT=1 nx init is allowed"                      0 'CC_NX_INIT=1 nx init'
  chk "negative: CC_NX_INIT=1 npx nx init is allowed"                  0 'CC_NX_INIT=1 npx nx init'
  chk "negative: npx nx mcp (not init) is untouched"                   0 'npx nx mcp'
  chk "negative: text that only mentions nx init"                      0 'grep -rn "nx init" docs'
  chk "negative: CC_SCAFFOLD does not authorize nx init"               2 'CC_SCAFFOLD=scaffold-angular-app nx init'
  chk "positive: npm create nx-workspace is blocked"                   2 'npm create nx-workspace@latest org'
  chk "positive: npm init nx-workspace is blocked"                     2 'npm init nx-workspace org'
  chk "positive: yarn dlx create-nx-workspace is blocked"              2 'yarn dlx create-nx-workspace org'
  chk "positive: pnpm nx init is blocked"                              2 'pnpm nx init'
  chk "positive: yarn nx init is blocked"                              2 'yarn nx init'
  chk "positive: echo redirect to nx.json is blocked"                  2 "printf '{}' > nx.json"
  chk "positive: npx nx add @nx/angular without nx.json is blocked"    2 'npx nx add @nx/angular'
  chk "negative: CC_NX_INIT=1 npx nx add @nx/angular is allowed"        0 'CC_NX_INIT=1 npx nx add @nx/angular'
  chk "negative: npx nx show projects is untouched"                    0 'npx nx show projects'
  nxexist=$(mktemp -d)
  printf '%s\n' '{}' > "$nxexist/nx.json"
  ( CLAUDE_PROJECT_DIR="$nxexist" evaluate 'npx nx add @nx/angular' ) >/dev/null 2>&1
  if [ $? -eq 0 ]; then echo "  ok   negative: npx nx add with existing nx.json is allowed"; else echo "  FAIL nx add with existing nx.json (want 0)"; fail=1; fi
  rm -rf "$nxexist"
  chk "negative: cat >> report <<'EOF' body mentioning flutter create"   0 "$(printf 'cat >> report.md <<%s\nflutter create was blocked\nEOF' "'EOF'")"
  chk "negative: cat > notes <<\"EOF\" body with npm create vite"        0 "$(printf 'cat > notes.md <<"EOF"\nnpm create vite@9.3.4 web\nEOF')"
  chk "negative: tee -a log <<'EOF' body with create-next-app"          0 "$(printf 'tee -a log.md <<%s\nnpx create-next-app@16.4.6 web\nEOF' "'EOF'")"
  chk "adversarial: cat <<'EOF' | bash body is executed"                 2 "$(printf 'cat <<%s | bash\nflutter create x\nEOF' "'EOF'")"
  chk "adversarial: bash <<'EOF' body is executed"                       2 "$(printf 'bash <<%s\nflutter create x\nEOF' "'EOF'")"
  chk "adversarial: python heredoc body stays scanned"                   2 "$(printf 'python3 - <<%s\nflutter create x\nPY' "'PY'")"
  chk "adversarial: unquoted delimiter (expansion) stays scanned"        2 "$(printf 'cat > a.md <<EOF\nflutter create x\nEOF')"
  chk "adversarial: \$(cat <<'EOF') fed to bash -c stays scanned"        2 "$(printf 'bash -c "$(cat <<%s\nflutter create x\nEOF\n)"' "'EOF'")"
  chk "adversarial: creator after the terminator is blocked"             2 "$(printf 'cat > a.md <<%s\nhi\nEOF\nflutter create x' "'EOF'")"
  chk "adversarial: missing terminator keeps the body scanned"           2 "$(printf 'cat > a.md <<%s\nflutter create x' "'EOF'")"
  chk "adversarial: cat <<'EOF' > a.sh && sh a.sh stays scanned"         2 "$(printf 'cat <<%s > a.sh && sh a.sh\nflutter create x\nEOF' "'EOF'")"
  # Write advisory (CLI-first reminder for hand-created Angular workspace files)
  local w; w=$(mktemp -d); mkdir -p "$w/demo/src/app/features/x" "$w/ws"; printf '{}' > "$w/ws/angular.json"
  wchk() { # label expect(advise|silent) tool path
    local out rc; out=$(write_advisory "$3" "$4"); rc=$?
    if [ "$rc" -ne 0 ]; then echo "  FAIL $1 (exit $rc)"; fail=1; return; fi
    case "$2" in
      advise) printf '%s' "$out" | grep -q 'CLI-first' && echo "  ok   $1" || { echo "  FAIL $1 (no advisory)"; fail=1; } ;;
      silent) [ -z "$out" ] && echo "  ok   $1" || { echo "  FAIL $1 (unexpected: $out)"; fail=1; } ;;
    esac
  }
  wchk "advisory: Write of new demo/angular.json"                        advise Write "$w/demo/angular.json"
  printf '{}' > "$w/demo/angular.json"
  wchk "advisory: Write of new src/main.ts in an Angular workspace"      advise Write "$w/demo/src/main.ts"
  wchk "advisory: Write of new tsconfig.spec.json in an Angular workspace" advise Write "$w/ws/tsconfig.spec.json"
  wchk "silent: Edit of an existing angular.json"                        silent Edit  "$w/ws/angular.json"
  wchk "silent: Write over an existing angular.json"                     silent Write "$w/ws/angular.json"
  wchk "silent: Write of a feature file"                                 silent Write "$w/demo/src/app/features/x/x.ts"
  mkdir -p "$w/vite/src"; printf '{"dependencies":{"react":"19.3.1"}}' > "$w/vite/package.json"
  wchk "silent: new tsconfig.app.json in a React (non-Angular) project"  silent Write "$w/vite/tsconfig.app.json"
  rm -rf "$w"
  local nxw
  nxw=$(mktemp -d)
  ( block_new_workspace_file "$nxw/nx.json" ) >/dev/null 2>&1
  if [ $? -eq 2 ]; then echo "  ok   positive: new nx.json is blocked"; else echo "  FAIL new nx.json (want exit 2)"; fail=1; fi
  printf '%s\n' '{}' > "$nxw/nx.json"
  ( block_new_workspace_file "$nxw/nx.json" ) >/dev/null 2>&1
  if [ $? -eq 0 ]; then echo "  ok   negative: existing nx.json is allowed"; else echo "  FAIL existing nx.json (want exit 0)"; fail=1; fi
  ( block_new_workspace_file "$nxw/melos.yaml" ) >/dev/null 2>&1
  if [ $? -eq 2 ]; then echo "  ok   positive: new melos.yaml is blocked"; else echo "  FAIL new melos.yaml (want exit 2)"; fail=1; fi
  ( block_new_workspace_file "$nxw/pubspec.yaml" ) >/dev/null 2>&1
  if [ $? -eq 0 ]; then echo "  ok   negative: new pubspec.yaml is not this hook"; else echo "  FAIL pubspec.yaml wrongly blocked"; fail=1; fi
  rm -rf "$nxw"
  # the audit trail records authorized calls
  ( evaluate 'CC_SCAFFOLD=scaffold-flutter-app flutter create audited_app' ) >/dev/null 2>&1
  if grep -q 'scaffold-flutter-app | CC_SCAFFOLD' "$t/scaffold-audit.log" 2>/dev/null; then echo "  ok   authorized call is written to the audit log"; else echo "  FAIL audit log entry missing"; fail=1; fi
  ( evaluate 'CC_SCAFFOLD=scaffold-react-app npx --yes create-vite@9.3.4 audited_web --template react-ts --no-interactive --no-immediate' ) >/dev/null 2>&1
  if grep -q 'scaffold-react-app | CC_SCAFFOLD' "$t/scaffold-audit.log" 2>/dev/null; then echo "  ok   documented react scaffold is written to the audit log"; else echo "  FAIL react audit log entry missing"; fail=1; fi
  rm -rf "$t"
  if [ "$fail" -eq 0 ]; then echo "selftest PASS"; else echo "selftest FAIL"; fi
  return "$fail"
}

if [ "${1:-}" = "--selftest" ]; then selftest; exit $?; fi

INPUT=$(cat)
TOOL=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('tool_name', ''))
except Exception:
    print('')
" 2>/dev/null)
if [ "$TOOL" = Write ]; then
  FILE=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('tool_input', {}).get('file_path', ''))
except Exception:
    print('')
" 2>/dev/null)
  block_new_workspace_file "$FILE"
  write_advisory Write "$FILE"
  exit 0
fi
COMMAND=$(printf '%s' "$INPUT" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('tool_input', {}).get('command', ''))
except Exception:
    print('')
" 2>/dev/null)
[ -z "$COMMAND" ] && exit 0
evaluate "$COMMAND"
exit 0
