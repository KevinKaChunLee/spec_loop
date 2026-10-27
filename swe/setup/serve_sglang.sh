#!/usr/bin/env bash
# Launch one SGLang server for one model of the loop, with the flags opencode and the loop rely on:
# Qwen3 tool calls (qwen25 parser), thinking split off (qwen3 reasoning parser), a 64K context
# through YaRN. Run once per model, each on its own GPUs and port:
#
#   CUDA_VISIBLE_DEVICES=0,1 swe/setup/serve_sglang.sh Qwen/Qwen3-32B 30000 --tp 2
#   CUDA_VISIBLE_DEVICES=2   swe/setup/serve_sglang.sh Qwen/Qwen3-8B  30001
#
# Extra arguments go to sglang.launch_server. The served name is the model path, which must match
# the model's id in swe_config.json. Set SGLANG_API_KEY to require a key (the loop sends it).
# Binds to 0.0.0.0 so that the task containers can reach it.
set -euo pipefail
MODEL=${1:?usage: serve_sglang.sh MODEL PORT [sglang args]}
PORT=${2:?usage: serve_sglang.sh MODEL PORT [sglang args]}
shift 2
[ -n "${SGLANG_API_KEY:-}" ] || echo "warning: SGLANG_API_KEY is not set: anyone who can reach port $PORT can use this server" >&2
exec "${SGLANG_PYTHON:-python3}" -m sglang.launch_server --model-path "$MODEL" --host 0.0.0.0 --port "$PORT" \
  --tool-call-parser qwen25 --reasoning-parser qwen3 --context-length 65536 \
  --json-model-override-args '{"rope_scaling":{"rope_type":"yarn","factor":2.0,"original_max_position_embeddings":32768}}' \
  ${SGLANG_API_KEY:+--api-key "$SGLANG_API_KEY"} "$@"
