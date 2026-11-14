#!/usr/bin/env bash
# =============================================================================
# Boomerang - one-shot setup for macOS and Ubuntu
#
# Usage (from the repo folder):
#   ./install.sh            # create the Python env + install packages + make .env
#   ./install.sh --system   # ALSO install OS tools (apt/brew) and serial-port access
#   ./install.sh --venv     # use a plain .venv folder even if conda is installed
#
# Safe to run again: it skips anything that already exists.
# =============================================================================
set -euo pipefail          # stop on any error (-e), on unset variables (-u),
                           # and if any command in a pipe fails (-o pipefail)

export PYTHONNOUSERSITE=1  # this script's pip never sees ~/.local packages
ENV_NAME="boomerang"       # conda env name (or .venv folder if no conda)
PY_VERSION="3.11"          # Python version every laptop uses
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"   # absolute path of this repo
cd "$REPO_DIR"

WITH_SYSTEM=0
FORCE_VENV=0
for arg in "$@"; do
  case "$arg" in
    --system) WITH_SYSTEM=1 ;;
    --venv)   FORCE_VENV=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)"; exit 1 ;;
  esac
done

say()  { printf "\n\033[1;34m==> %s\033[0m\n" "$*"; }   # blue bold heading
ok()   { printf "\033[1;32m  ok\033[0m  %s\n" "$*"; }     # green
warn() { printf "\033[1;33m  !!\033[0m  %s\n" "$*"; }     # yellow

# -----------------------------------------------------------------------------
# 1. Which OS are we on?
# -----------------------------------------------------------------------------
case "$(uname -s)" in
  Darwin) OS="mac" ;;
  Linux)  OS="linux" ;;
  *) echo "Unsupported OS: $(uname -s). Use macOS or Ubuntu."; exit 1 ;;
esac
say "Detected OS: $OS ($(uname -m))"

# -----------------------------------------------------------------------------
# 2. Optional system tools (only with --system)
# -----------------------------------------------------------------------------
if [[ "$WITH_SYSTEM" == 1 ]]; then
  if [[ "$OS" == "linux" ]]; then
    say "Installing Ubuntu packages (needs your sudo password)"
    sudo apt update
    sudo apt install -y git curl libfuse2t64    # libfuse2t64 = needed by the Arduino AppImage
    if ! id -nG "$USER" | grep -qw dialout; then
      sudo usermod -aG dialout "$USER"          # lets you open /dev/ttyACM* without sudo
      warn "Added you to 'dialout'. LOG OUT and back in before uploading to the Arduino."
    else
      ok "already in dialout group"
    fi
  else
    say "Checking macOS tools"
    if ! xcode-select -p >/dev/null 2>&1; then
      xcode-select --install || true
      warn "Finish the Command Line Tools popup, then run ./install.sh again."
      exit 0
    fi
    ok "Xcode Command Line Tools"
    if ! command -v brew >/dev/null 2>&1; then
      warn "Homebrew not found. Install it from https://brew.sh then rerun with --system."
    else
      brew list --cask arduino-ide >/dev/null 2>&1 || brew install --cask arduino-ide
      ok "Arduino IDE"
      if ! command -v conda >/dev/null 2>&1 && ! command -v python3.11 >/dev/null 2>&1; then
        brew install python@3.11                  # gives us python3.11 for the .venv route
      fi
    fi
  fi
fi

# -----------------------------------------------------------------------------
# 3. Python environment: conda env if conda exists, otherwise .venv
# -----------------------------------------------------------------------------
if command -v conda >/dev/null 2>&1 && [[ "$FORCE_VENV" == 0 ]]; then
  MODE="conda"
  say "Using conda env '$ENV_NAME' (Python $PY_VERSION)"
  if conda env list | awk '{print $1}' | grep -qx "$ENV_NAME"; then
    ok "env already exists"
  else
    conda create -n "$ENV_NAME" "python=$PY_VERSION" -y
  fi
  # Ignore ~/.local/lib/pythonX.Y/site-packages inside this env, so packages
  # from other projects (IsaacLab etc.) never leak in. Applies on every activate.
  conda env config vars set PYTHONNOUSERSITE=1 -n "$ENV_NAME" >/dev/null
  ok "env isolated from ~/.local user packages"
  PY=(conda run --no-capture-output -n "$ENV_NAME" python)
  ACTIVATE="conda activate $ENV_NAME"
else
  MODE="venv"
  say "Using a .venv folder in the repo"
  PYBIN=""
  for cand in python3.11 python3.12 python3.13 python3; do
    if command -v "$cand" >/dev/null 2>&1 && \
       "$cand" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
      PYBIN="$cand"; break
    fi
  done
  if [[ -z "$PYBIN" ]]; then
    echo "Need Python 3.10+. Mac: ./install.sh --system   Ubuntu: sudo apt install python3.12-venv"
    exit 1
  fi
  [[ -d .venv ]] || "$PYBIN" -m venv .venv
  ok "using $("$PYBIN" --version)"
  PY=(.venv/bin/python)
  ACTIVATE="source .venv/bin/activate"
fi

# -----------------------------------------------------------------------------
# 4. Install pinned packages
# -----------------------------------------------------------------------------
say "Installing Python packages from backend/requirements.txt"
"${PY[@]}" -m pip install --upgrade pip
"${PY[@]}" -m pip install -r backend/requirements.txt
ok "packages installed"

# -----------------------------------------------------------------------------
# 5. .env file (secrets live here, git ignores it)
# -----------------------------------------------------------------------------
say "Setting up .env"
if [[ ! -f .env ]]; then
  cp .env.example .env
  SECRET="$("${PY[@]}" -c 'import secrets; print(secrets.token_hex(32))')"
  # replace the empty LINK_SIGNING_SECRET= line with a random value (works on mac + linux sed)
  "${PY[@]}" - "$SECRET" <<'EOF'
import sys, re, pathlib
p = pathlib.Path(".env")
p.write_text(re.sub(r"^LINK_SIGNING_SECRET=.*$", f"LINK_SIGNING_SECRET={sys.argv[1]}", p.read_text(), flags=re.M))
EOF
  if [[ "$OS" == "mac" ]]; then
    sed -i '' 's#^SERIAL_PORT=/dev/ttyACM0#SERIAL_PORT=/dev/cu.usbmodemXXXX#' .env
  fi
  ok "created .env (fill in AWS + MongoDB values)"
else
  ok ".env already exists - left untouched"
fi
chmod 600 .env                                  # only you can read the secrets file

# -----------------------------------------------------------------------------
# 6. Make sure git never tracks .env
# -----------------------------------------------------------------------------
if [[ -d .git ]] && git ls-files --error-unmatch .env >/dev/null 2>&1; then
  git rm --cached .env
  warn ".env WAS tracked by git - removed from the index. Rotate your AWS keys!"
fi

# -----------------------------------------------------------------------------
# 7. Quick self-test (no network calls)
# -----------------------------------------------------------------------------
say "Running unit tests"
"${PY[@]}" -m pytest -q || warn "tests failed - tell the team"

say "Done ($MODE)."
cat <<EOF

Next steps:
  1. $ACTIVATE
  2. Fill in .env  (AWS profile or keys, S3_BUCKET, MONGODB_URI)
  3. python scripts/check_setup.py      # tests AWS, Bedrock, S3, MongoDB
  4. uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000
     then open http://localhost:8000/docs
EOF
