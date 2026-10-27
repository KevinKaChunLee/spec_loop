"""Where an agent works: a SWE-bench instance container (DockerExecutor) or, for the smoke test, a
plain directory on the host (LocalExecutor). Both start the workspace with a fresh one-commit git
history, launch opencode with an isolated configuration, and collect the patch."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path

from lib import runner
from lib.common import log, remove_tree
from lib.opencode_runner import OPENCODE_ENV

# The image's history can contain the upstream fix; the agent gets only the base state.
FRESH_GIT = ("rm -rf .git && git init -q && git add -A && "
             "git -c user.name=swe -c user.email=swe@localhost commit -qm base")
# Files the agent's tooling may create that are not part of a fix.
PATCH_EXCLUDES = (".opencode",)
OC_IN_CONTAINER = "/opt/opencode/opencode"
OC_HOME = "/root/.oc"


def _isolated_env(home: str) -> dict:
    return {"HOME": home, **{f"XDG_{k}_HOME": f"{home}/{k.lower()}" for k in ("CONFIG", "DATA", "CACHE", "STATE")},
            **OPENCODE_ENV}


def _patch_script(excludes: tuple[str, ...]) -> str:
    spec = " ".join(f"':(exclude){e}'" for e in excludes)
    return f"git add -A -- . {spec} && git diff --cached HEAD"


def docker(*args: str, timeout: float = 600, check: bool = True, input_text: str | None = None) -> str:
    r = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout, input=input_text)
    if check and r.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args[:3])} failed ({r.returncode}): {(r.stderr or r.stdout)[-800:]}")
    return r.stdout


class DockerExecutor:
    """One container per attempt, started from the task's image; opencode is mounted read-only,
    keeps its sessions inside the container, and reaches only what the container network allows."""

    def __init__(self, image: str, name: str, opencode_bin: str, config: dict, workdir: str = "/testbed",
                 fresh_git: bool = True, conda_activate: str | None = None, seed: Path | None = None):
        self.image, self.name, self.opencode_bin = image, name, opencode_bin
        self.workdir, self.fresh_git, self.conda_activate, self.seed = workdir, fresh_git, conda_activate, seed
        self.config = config
        self.env: dict = {}
        self._hook = lambda: docker("rm", "-f", self.name, check=False, timeout=60)

    def start(self) -> None:
        dc = self.config
        docker("rm", "-f", self.name, check=False, timeout=60)
        docker("run", "-d", "--name", self.name, "--network", dc["network"], "--memory", dc["memory"],
               "--cpus", str(dc["cpus"]), "-v", f"{self.opencode_bin}:{OC_IN_CONTAINER}:ro",
               "-w", self.workdir, "--entrypoint", "/bin/sleep", self.image, "infinity")
        runner.add_stop_hook(self._hook)
        path = self.sh("echo $PATH", activate=True).strip()
        self.env = {**_isolated_env(OC_HOME), "PATH": path or "/usr/local/bin:/usr/bin:/bin"}
        self.sh(f"mkdir -p {self.workdir} {OC_HOME}")
        if self.seed:
            self.copy_in(self.seed, self.workdir)
        if self.fresh_git:
            self.sh(f"cd {self.workdir} && {FRESH_GIT}")

    def sh(self, script: str, activate: bool = False, timeout: float = 600, check: bool = True) -> str:
        if activate and self.conda_activate:
            script = f"{self.conda_activate} >/dev/null 2>&1; {script}"
        return docker("exec", self.name, "bash", "-c", script, timeout=timeout, check=check)

    def launch(self, args: list[str], config_content: str) -> tuple[list[str], dict | None]:
        envs = [x for k, v in {**self.env, "OPENCODE_CONFIG_CONTENT": config_content}.items() for x in ("-e", f"{k}={v}")]
        return ["docker", "exec", "-w", self.workdir, *envs, self.name, OC_IN_CONTAINER, *args], None

    def kill_agent(self) -> None:
        docker("exec", self.name, "pkill", "-f", OC_IN_CONTAINER, check=False, timeout=60)

    def copy_in(self, src: Path, dst: str) -> None:
        self.sh(f"mkdir -p {dst}")
        docker("cp", f"{src}/.", f"{self.name}:{dst}", timeout=600)

    def read(self, path: str) -> str | None:
        r = subprocess.run(["docker", "exec", self.name, "cat", path], capture_output=True, text=True, timeout=120)
        return r.stdout if r.returncode == 0 else None

    def patch(self) -> str:
        return self.sh(f"cd {self.workdir} && {_patch_script(PATCH_EXCLUDES)}")

    def stop(self) -> None:
        runner.remove_stop_hook(self._hook)
        self._hook()


class LocalExecutor:
    """For the smoke test: the workspace is a copy of a directory on the host, and opencode runs on
    the host with its own isolated configuration and data directories."""

    def __init__(self, src: Path, root: Path, opencode_bin: str, fresh_git: bool = True):
        self.src, self.root, self.opencode_bin, self.fresh_git = src, root, opencode_bin, fresh_git
        self.workdir = str(root / "ws")
        self.env: dict = {}

    def start(self) -> None:
        remove_tree(self.root)
        shutil.copytree(self.src, self.workdir, symlinks=True)
        self.env = {**_isolated_env(str(self.root / "home")), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        if self.fresh_git:
            self.sh(f"cd {self.workdir} && {FRESH_GIT}")

    def sh(self, script: str, activate: bool = False, timeout: float = 600, check: bool = True) -> str:
        r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, timeout=timeout)
        if check and r.returncode != 0:
            raise RuntimeError(f"{script[:80]} failed ({r.returncode}): {(r.stderr or r.stdout)[-800:]}")
        return r.stdout

    def launch(self, args: list[str], config_content: str) -> tuple[list[str], dict | None]:
        return [self.opencode_bin, *args], {**self.env, "OPENCODE_CONFIG_CONTENT": config_content}

    def kill_agent(self) -> None:
        pass

    def copy_in(self, src: Path, dst: str) -> None:
        shutil.copytree(src, dst, dirs_exist_ok=True)

    def read(self, path: str) -> str | None:
        p = Path(path)
        return p.read_text(encoding="utf-8") if p.exists() else None

    def patch(self) -> str:
        return self.sh(f"cd {self.workdir} && {_patch_script(PATCH_EXCLUDES)}")

    def stop(self) -> None:
        pass


EGRESS_BLOCKED = ("https://pypi.org/simple/", "https://github.com")


def egress_probe(image: str, docker_cfg: dict, allowed_urls: list[str]) -> dict:
    """From a container on the loop's network: {url: reachable} for the model endpoints, which must
    be reachable, and for EGRESS_BLOCKED, which must not be."""
    name = "swe-loop-egress-probe"
    urls = [*allowed_urls, *EGRESS_BLOCKED]
    script = ("import sys, urllib.request\n"
              "def ok(u):\n"
              "    try:\n"
              "        urllib.request.urlopen(u, timeout=8); return True\n"
              "    except Exception as e:\n"
              "        return 'HTTP Error' in str(e)\n"
              "print(*(ok(u) for u in sys.argv[1:]))\n")
    docker("rm", "-f", name, check=False, timeout=60)
    cmd = f"{docker_cfg['conda_activate']} >/dev/null 2>&1; python -c {shlex.quote(script)} " + \
        " ".join(map(shlex.quote, urls))
    try:
        out = docker("run", "--rm", "--name", name, "--network", docker_cfg["network"], "--entrypoint", "bash",
                     image, "-c", cmd, timeout=180).split()
    except RuntimeError as e:
        return {"error": str(e)[:300]}
    if len(out) < len(urls):
        return {"error": f"unexpected probe output: {' '.join(out)[:300]}"}
    return {"reachable": dict(zip(urls, (x == "True" for x in out[-len(urls):])))}


def docker_available() -> str | None:
    """None when the Docker daemon answers, else why not."""
    try:
        r = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True,
                           timeout=30)
    except FileNotFoundError:
        return "the docker command is not installed"
    except subprocess.TimeoutExpired:
        return "docker info timed out"
    return None if r.returncode == 0 else (r.stderr.strip() or "docker info failed")[:300]


def ensure_image(image: str) -> None:
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode != 0:
        log(f"pulling {image}")
        docker("pull", image, timeout=3600)


def config_json(cfg: dict) -> str:
    return json.dumps(cfg, separators=(",", ":"))
