import subprocess

REPLACE_ID = "48151623"


def notify(
    summary: str,
    body: str = "",
    urgent: bool = False,
    persist: bool = False,
    run=subprocess.run,
) -> None:
    timeout = "0" if persist else ("5000" if urgent else "2000")
    argv = ["notify-send", "-r", REPLACE_ID, "-t", timeout]
    if urgent:
        argv += ["-u", "critical"]
    argv.append(summary)
    if body:
        argv.append(body)
    try:
        run(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except (OSError, subprocess.SubprocessError):
        pass
