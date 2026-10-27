# swe_loop: SWE-bench playbook distillation

**Teach a weaker model to fix real GitHub issues with a playbook.** A student model (Qwen3-8B) solves SWE-bench Verified Django tasks through opencode, each attempt in the task's own Docker image. The official SWE-bench harness scores every patch. A teacher model (Qwen3-32B) reads the student's failures on the training tasks, together with the correct patches and the stronger model's own attempts, and writes a short playbook of general advice. The student gets the playbook on its next attempt. After a fixed number of iterations, the best playbook is tested on held-out tasks against no playbook, paired task by task.

The pilot uses 15 training tasks and 5 held-out tasks from `django/django`, with difficulty `<15 min fix` or `15 min - 1 hour`. With 5 held-out tasks no test can reach p < 0.05 (the smallest possible p is 0.0625), so the held-out result is a sanity check. It is not proof that the playbook works.

`swe_loop.py` is standard-library Python. Only the harness needs `swebench`, and it runs in the Python interpreter that `python` in `swe_config.json` points to.

---

## Requirements on the server

- Linux, Python 3.10+, `git`, and Docker with your user in the `docker` group. Each Django task image is a few GB, so the 20 tasks need plenty of disk space.
- `swebench` 5.x in some Python environment, for example `python3 -m venv ~/swebench-venv && ~/swebench-venv/bin/pip install swebench`. Set `python` in `swe_config.json` to that interpreter.
- opencode, at the version in `swe_config.json` (`opencode.version`), installed with the opencode.ai install script. The loop mounts this binary into the task containers, so it must be the standalone binary, not the npm package's wrapper script. Put it on `PATH` or set `opencode.bin`.
- SGLang with GPUs for Qwen3-32B (oracle and synthesizer) and Qwen3-8B (student). Each model runs as its own server on its own port.

---

## Setup

1. **Start the model servers**, each on its own GPUs:

   ```bash
   CUDA_VISIBLE_DEVICES=0,1 swe/setup/serve_sglang.sh Qwen/Qwen3-32B 30000 --tp 2
   CUDA_VISIBLE_DEVICES=2   swe/setup/serve_sglang.sh Qwen/Qwen3-8B  30001
   ```

   The script adds the flags the loop needs: `--tool-call-parser qwen25`, `--reasoning-parser qwen3`, and a 64K context through YaRN. It binds to `0.0.0.0`. Set `SGLANG_API_KEY` to require a key; the loop sends the key from that variable (`server.api_key_env`).

2. **Edit `swe_config.json`.** Set `models.<role>.base_url` (or `server.base_url` as the default) to URLs that the containers can reach. Do not use `localhost`: inside a container it is the container itself. If SGLang runs on the Docker host, use the gateway address of the `swe-loop` network, which step 3 prints. Also set `python` to the swebench interpreter. The model ids must match the servers' served names, which by default are the model paths.

3. **Restrict container egress** to the model servers:

   ```bash
   sudo swe/setup/egress.sh
   ```

   This creates the `swe-loop` Docker network if needed. It then lets containers on that network connect only to the endpoints in `swe_config.json`, so an agent cannot fetch the upstream fix from GitHub or install packages from PyPI. Run it again after a reboot.

4. **Run the smoke test.** It runs the whole pipeline on a toy repository with a scripted fake model, on the host. It needs opencode, but no GPU, Docker or swebench:

   ```bash
   python3 swe_loop.py smoke
   ```

   It ends with a PASS/FAIL checklist covering stages, evaluation, noise, both syntheses, the leak check stripping a leaky line, playbook hand-over between iterations, the held-out test, and transcript export.

5. **Check the environment:**

   ```bash
   python3 swe_loop.py check --image swebench/sweb.eval.x86_64.django_1776_django-11099:latest
   ```

   The command checks the following:
   - the opencode version, and that opencode is the standalone binary;
   - swebench and the Docker daemon;
   - each SGLang endpoint (version and parsers), and that each role's model is served and makes a tool call;
   - that opencode runs inside a task image;
   - from a container on `swe-loop`, that the model endpoints can be reached and PyPI and GitHub cannot.

   It exits non-zero if any check fails. After `prepare` you can use `--run R` instead of `--image`.

---

## Running the pilot

```bash
python3 swe_loop.py prepare --run p1     # pick 15 + 5 tasks, pull images, check the gold patches resolve
python3 swe_loop.py oracle  --run p1     # Qwen3-32B solves the 15 training tasks once
python3 swe_loop.py iterate --run p1     # iterations 0..2 and two syntheses (see below)
python3 swe_loop.py test    --run p1     # held-out tasks: no playbook vs the best playbook
python3 swe_loop.py status  --run p1
```

- **prepare** loads the dataset with the swebench Python. It filters Django tasks by difficulty and draws a seeded sample (`dataset.seed`), so the split is reproducible. It writes `tasks.json`, which is what agents may see. It writes `gold/<id>.json` (gold patch, test patch, tests), which only the harness, the synthesizer and the leak check read. Then it pulls the images and runs the harness on the gold patches. Every gold patch must resolve; if one does not, the environment is broken for that task. In that case, look at `runs/p1/harness/`, or change `dataset.seed` and prepare again. `inputs.lock.json` records the config, the prompts, the opencode and swebench versions, and, per role, what the SGLang server reports.
- **oracle** gives the synthesizer contrastive evidence (how the stronger model fixed the same issues) and an upper bound.
- **iterate** works as follows:
  - Iteration 0 runs the student without a playbook, twice per task (`iteration0_samples`), and writes the noise baseline.
  - A synthesis follows, producing the playbook of iter-00.
  - Iteration 1 runs the student with that playbook, followed by a second synthesis (the playbook of iter-01).
  - Iteration 2 runs the student with the second playbook.
  - `iterate` is resumable: completed attempts with the same prompt and model are reused. `--start K` begins at iteration K.
- **test** picks the playbook whose iteration resolved the most training attempts; `--playbook iter-NN` picks one yourself. It runs the student on the 5 held-out tasks with no playbook (`test-none`) and with the chosen playbook (`test-full`), then compares the two arms task by task.

Each stage runs up to `max_parallel_agents` attempts at once. A stage's worst-case duration is about attempts × `timeouts_min` / `max_parallel_agents`, plus harness time. Ctrl-C stops the agents and removes their containers. Rerunning the command continues where it stopped.

If prompts, config, the opencode or swebench version, or a model server's launch arguments change after `prepare`, commands refuse to continue, because results would no longer be comparable. Pass `--allow-drift` to continue anyway; the drift is recorded in `state.json`. Server URLs and operational keys (`workspace_root`, `python`, `max_parallel_agents`) can change freely.

---

## What keeps it fair

- **Validity.** An attempt is invalid, and retried (`infra_retries`), only for reasons outside the model: the endpoint failed, or a network command or web tool got through. A timeout, an empty patch or a model that gives up counts as unresolved, so failures are never dropped from a resolve rate. A task that the harness could not evaluate is reported as unscored, not as resolved or unresolved.
- **No access to the fix.** Each attempt runs in a fresh container of the task's image. The repository gets a new one-commit git history, because the image's history can contain the upstream fix. opencode's web tool is denied, and egress is limited to the model servers. Every bash call is also scanned for network attempts.
- **Playbook leak check.** A playbook must give general advice. Before use, a script checks every line against the following material from all 20 tasks, including the held-out tasks: paths, defined names and failing-test names from the gold and test patches, plus 40-character n-grams of the gold patches' added code. The synthesizer gets one chance to rewrite. Lines still flagged after that are removed and listed in the changelog. Length is capped by `playbook_limits`.
- **Noise.** Iteration 0's two samples per task show how often a task flips between resolved and unresolved by chance (`noise.md`). A playbook effect smaller than that flip rate does not mean much.
- **Statistics.** The held-out comparison is paired by task. It uses McNemar's exact test with one sample per arm, and a sign-flip permutation test with more (`test --samples N`). `report.md` states the smallest p the test set allows.

---

## Run directory

```
runs/<run>/
  tasks.json, gold/<id>.json, inputs.lock.json, state.json
  results.csv                       one row per attempt: stage, task, sample, valid, resolved, tests, tokens, minutes
  oracle/<id>/s1/                   attempt.json, patch.diff, eval.json, trajectory.md/.jsonl/.transcript.json, guards.json
  iter-00/<id>/s1, s2/              student, no playbook
  iter-00/playbook/                 playbook.md, playbook.raw.md, changelog.md, leak_report.json, workspace/_inputs/
  iter-01/..., iter-02/...          student with the previous iteration's playbook
  noise.json, noise.md
  test-none/, test-full/            held-out attempts
  test/ablation.json, test/report.md
  harness/                          predictions, harness logs and reports
```

`iter-NN/playbook/workspace/_inputs/` shows exactly what the synthesizer saw: a summary table and one digest per training task (outcome, issue, correct patch when the student failed, the student's patch, failing tests, test output, and a one-line-per-tool-call trajectory).

---

## Configuration (`swe_config.json`)

| key | meaning |
|---|---|
| `dataset` | dataset name and split, repository, difficulties, number of train and test tasks, sampling seed |
| `server`, `models.<role>.base_url` | SGLang endpoints; the API key is read from the variable named by `api_key_env` |
| `models` | model id, context and output token limits per role (oracle, synthesizer, student) |
| `docker` | network name, memory and CPU limits per container, conda activation command of the images |
| `harness` | harness parallelism and per-task timeout |
| `timeouts_min` | per-attempt time limit per role |
| `iterations`, `iteration0_samples`, `test_samples` | loop length and samples |
| `max_parallel_agents`, `infra_retries`, `completion_nudges` | concurrency, retries of invalid attempts, nudges when an attempt ends without a patch |
| `repo_hints` | how to run the repository's tests, given to the student |
| `playbook_limits`, `digest_limits` | playbook size and leak-check settings; how much of each input the synthesizer sees |
