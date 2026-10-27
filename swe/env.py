"""Where an agent works: a SWE-bench instance container (DockerExecutor) or, for the smoke test, a
plain directory on the host (LocalExecutor). Both start the workspace with a fresh one-commit git
history, launch opencode with an isolated configuration, and collect the patch."""

from __future__ import annotations

import os
import re
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
# Everything the agent changed, except what its own tooling may create (.opencode).
PATCH_SCRIPT = "git add -A -- . ':(exclude).opencode' && git diff --cached HEAD"
OC_IN_CONTAINER = "/opt/opencode/opencode"
OC_HOME = "/root/.oc"
EGRESS_BLOCKED = ("https://pypi.org/simple/", "https://github.com")


def container_name(*parts: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]", "-", "-".join(("swe", *parts)))


def _isolated_env(home: str) -> dict:
    return {"HOME": home, **{f"XDG_{k}_HOME": f"{home}/{k.lower()}" for k in ("CONFIG", "DATA", "CACHE", "STATE")},
            **OPENCODE_ENV}


def docker(*args: str, timeout: float = 600, check: bool = True) -> str:
    r = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=timeout)
    if check and r.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args[:3])} failed ({r.returncode}): {(r.stderr or r.stdout)[-800:]}")
    return r.stdout


class DockerExecutor:
    """One container per attempt, started from the task's image; opencode is mounted read-only,
    keeps its sessions inside the container, and reaches only what the container network allows.
    `seed`, if given, is copied to `workdir` first (the synthesizer's inputs)."""

    def __init__(self, image: str, name: str, opencode_bin: str, config: dict, workdir: str = "/testbed",
                 seed: Path | None = None):
        self.image, self.name, self.opencode_bin, self.config = image, name, opencode_bin, config
        self.workdir, self.seed = workdir, seed
        self.env: dict = {}
        self._hook = lambda: docker("rm", "-f", self.name, check=False, timeout=60)

    def start(self) -> None:
        dc = self.config
        docker("rm", "-f", self.name, check=False, timeout=60)
        runner.add_stop_hook(self._hook)
        docker("run", "-d", "--name", self.name, "--network", dc["network"], "--memory", dc["memory"],
               "--cpus", str(dc["cpus"]), "-v", f"{self.opencode_bin}:{OC_IN_CONTAINER}:ro",
               "-w", self.workdir, "--entrypoint", "/bin/sleep", self.image, "infinity")
        if self.seed:
            docker("cp", f"{self.seed}/.", f"{self.name}:{self.workdir}", timeout=600)
        # The agent's shell gets the PATH of the image's activated conda environment.
        path = self.sh(f"mkdir -p {self.workdir} {OC_HOME} && cd {self.workdir} && {FRESH_GIT} && "
                       f"{{ {dc['conda_activate']} >/dev/null 2>&1; echo \"$PATH\"; }}").strip().splitlines()
        self.env = {**_isolated_env(OC_HOME), "PATH": path[-1] if path else "/usr/local/bin:/usr/bin:/bin"}

    def sh(self, script: str) -> str:
        return docker("exec", self.name, "bash", "-c", script)

    def launch(self, args: list[str], config_content: str) -> tuple[list[str], dict | None]:
        envs = [x for k, v in {**self.env, "OPENCODE_CONFIG_CONTENT": config_content}.items() for x in ("-e", f"{k}={v}")]
        return ["docker", "exec", "-w", self.workdir, *envs, self.name, OC_IN_CONTAINER, *args], None

    def kill_agent(self) -> None:
        docker("exec", self.name, "pkill", "-f", OC_IN_CONTAINER, check=False, timeout=60)

    def read(self, path: str) -> str:
        """The file's text, or "" when it does not exist."""
        r = subprocess.run(["docker", "exec", self.name, "cat", path], capture_output=True, text=True, timeout=120)
        return r.stdout if r.returncode == 0 else ""

    def patch(self) -> str:
        return self.sh(f"cd {self.workdir} && {PATCH_SCRIPT}")

    def stop(self) -> None:
        runner.remove_stop_hook(self._hook)
        self._hook()


class LocalExecutor:
    """For the smoke test: the workspace is a copy of a directory on the host, and opencode runs on
    the host with its own isolated configuration and data directories."""

    def __init__(self, src: Path, root: Path, opencode_bin: str):
        self.src, self.root, self.opencode_bin = src, root, opencode_bin
        self.workdir = str(root / "ws")
        self.env: dict = {}

    def start(self) -> None:
        remove_tree(self.root)
        shutil.copytree(self.src, self.workdir, symlinks=True)
        self.env = {**_isolated_env(str(self.root / "home")), "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        self._git(FRESH_GIT)

    def _git(self, script: str) -> str:
        return subprocess.run(["bash", "-c", script], cwd=self.workdir, capture_output=True, text=True,
                              check=True).stdout

    def launch(self, args: list[str], config_content: str) -> tuple[list[str], dict | None]:
        return [self.opencode_bin, *args], {**self.env, "OPENCODE_CONFIG_CONTENT": config_content}

    def kill_agent(self) -> None:
        """Nothing to do: the agent runs in the process group the runner signals."""

    def read(self, path: str) -> str:
        p = Path(path)
        return p.read_text(encoding="utf-8") if p.exists() else ""

    def patch(self) -> str:
        return self._git(PATCH_SCRIPT)

    def stop(self) -> None:
        pass


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


def network_exists(name: str) -> bool:
    return subprocess.run(["docker", "network", "inspect", name], capture_output=True).returncode == 0


def ensure_image(image: str) -> None:
    if subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode != 0:
        log(f"pulling {image}")
        docker("pull", image, timeout=3600)
