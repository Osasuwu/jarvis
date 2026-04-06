"""
setup-device.py — Configure a new device for Jarvis (personal-AI-agent)
Run from anywhere. Idempotent — safe to re-run.

What it does:
  1. Python venv + memory server deps
  2. .env from template (if missing)
  3. Validates everything works
"""
import os
import sys
import subprocess
import shutil
import platform

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IS_WINDOWS = platform.system() == "Windows"


def run(cmd, **kwargs):
    """Run a command, return (success, output)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, **kwargs)
        return r.returncode == 0, r.stdout.strip()
    except FileNotFoundError:
        return False, ""


def step(n, title):
    print(f"\n--- Step {n}: {title} ---")


def main():
    print("=== Jarvis device setup ===")
    print(f"Project: {ROOT}")
    print(f"OS: {platform.system()}")

    errors = 0

    # --- 1. Python venv ---
    step(1, "Python venv")
    venv_dir = os.path.join(ROOT, ".venv")

    if IS_WINDOWS:
        venv_python = os.path.join(venv_dir, "Scripts", "python.exe")
        venv_pip = os.path.join(venv_dir, "Scripts", "pip.exe")
    else:
        venv_python = os.path.join(venv_dir, "bin", "python")
        venv_pip = os.path.join(venv_dir, "bin", "pip")

    if not os.path.isdir(venv_dir):
        print("Creating venv...")
        subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
    else:
        print("Venv exists, skipping creation")

    reqs = os.path.join(ROOT, "mcp-memory", "requirements.txt")
    if os.path.isfile(reqs):
        print("Installing memory server deps...")
        subprocess.run([venv_pip, "install", "-q", "-r", reqs], check=True)
    else:
        print("Warning: mcp-memory/requirements.txt not found, skipping")

    print(f"Done: Python={venv_python}")

    # --- 2. .env file ---
    step(2, "Environment variables")
    env_file = os.path.join(ROOT, ".env")
    env_example = os.path.join(ROOT, ".env.example")

    if not os.path.isfile(env_file):
        if os.path.isfile(env_example):
            shutil.copy2(env_example, env_file)
            print(f"Created .env from template — edit it with your secrets:")
            print(f"  {env_file}")
        else:
            with open(env_file, "w") as f:
                f.write("# Required\nSUPABASE_URL=\nSUPABASE_KEY=\n\n# Optional\nGITHUB_TOKEN=\nFIRECRAWL_API_KEY=\n")
            print(f"Created minimal .env — fill in your secrets: {env_file}")
    else:
        print(".env exists, skipping")

    # --- 3. Validation ---
    step(3, "Validation")

    # Check supabase package
    ok, _ = run([venv_python, "-c", "import supabase"])
    print(f"  [{'OK' if ok else 'FAIL'}] supabase Python package")
    if not ok:
        errors += 1

    # Check .env has required vars
    env_vars = {}
    if os.path.isfile(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()

    for var in ["SUPABASE_URL", "SUPABASE_KEY"]:
        val = env_vars.get(var, "")
        if val and not val.startswith("your-"):
            print(f"  [OK] {var} is set")
        else:
            print(f"  [WARN] {var} is empty — fill in .env")

    # Check key files
    for name, path in [
        ("CLAUDE.md", os.path.join(ROOT, "CLAUDE.md")),
        (".mcp.json", os.path.join(ROOT, ".mcp.json")),
    ]:
        if os.path.isfile(path):
            print(f"  [OK] {name} present")
        else:
            print(f"  [FAIL] {name} missing")
            errors += 1

    # Check skills
    skills_dir = os.path.join(ROOT, ".claude", "skills")
    if os.path.isdir(skills_dir):
        count = sum(1 for d in os.listdir(skills_dir) if os.path.isfile(os.path.join(skills_dir, d, "SKILL.md")))
        print(f"  [OK] {count} skills found")
    else:
        print("  [WARN] .claude/skills/ not found")

    # Check CLI tools
    for tool in ["gh", "claude"]:
        ok = shutil.which(tool) is not None
        print(f"  [{'OK' if ok else 'WARN'}] {tool} CLI {'found' if ok else 'not found'}")

    # Summary
    print()
    if errors == 0:
        print("=== Setup complete! ===")
        print()
        print("Next steps:")
        print(f"  1. Fill in secrets in {env_file} (if not done)")
        print(f"  2. cd {ROOT} && claude")
        print("  3. Verify: skills load, memory works, /status runs")
    else:
        print(f"=== Setup completed with {errors} error(s) ===")
        print("Fix the issues above and re-run this script.")

    return errors


if __name__ == "__main__":
    sys.exit(main())
