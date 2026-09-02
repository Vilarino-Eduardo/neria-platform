import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = "scripts/check_secrets.py"
MAX_TEXT_FILE_BYTES = 2 * 1024 * 1024
PATTERNS = {
    "OpenAI API key": re.compile(r"sk-(?:proj-|admin-)?[A-Za-z0-9_-]{20,}"),
    "AWS access key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "Meta access token": re.compile(r"EAA[A-Za-z0-9]{30,}"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return [item for item in result.stdout.decode().split("\0") if item]


def main() -> int:
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", ".env"],
        cwd=ROOT,
        check=False,
    )
    if ignored.returncode != 0:
        print("ERRO: .env não está protegido pelo .gitignore.")
        return 1

    findings: list[tuple[str, str, int]] = []
    for relative_path in tracked_files():
        if relative_path == SELF:
            continue
        path = ROOT / relative_path
        if not path.is_file() or path.stat().st_size > MAX_TEXT_FILE_BYTES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for secret_type, pattern in PATTERNS.items():
            for match in pattern.finditer(content):
                line = content.count("\n", 0, match.start()) + 1
                findings.append((relative_path, secret_type, line))

    if findings:
        print("Possíveis segredos encontrados em arquivos rastreados:")
        for relative_path, secret_type, line in findings:
            print(f"- {relative_path}:{line} ({secret_type})")
        return 1

    print("Nenhum segredo conhecido encontrado em arquivos rastreados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
