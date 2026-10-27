"""A scripted OpenAI-compatible chat endpoint for testing the opencode plumbing without a GPU.

Each served model has a script. A request that offers tools gets the step of its script after the
tool results already in the conversation: a shell command (a plain string), any tool call (a JSON
object such as {"tool": "grep", "args": {"pattern": "x"}}), or a final answer once the script is
used up. Because the step comes from the request's own history, parallel sessions do not disturb
each other. Requests without tools (session titles, summaries) get a short text reply. Serves
/v1/models and /server_info like SGLang does.

    python3 -m swe.fake_llm --port 8765 --model fake/qwen --script 'echo hello > hello.txt' 'cat hello.txt'
"""

from __future__ import annotations

import argparse
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def next_step(script: list[str], messages: list[dict]) -> dict:
    i = sum(1 for m in messages if m.get("role") == "tool")
    if i >= len(script):
        return {"text": "Done: the change is in place."}
    step = script[i]
    if step.lstrip().startswith("{"):
        return json.loads(step)
    return {"tool": "bash", "args": {"command": step, "description": f"step {i + 1}"}}


def sse(handler: BaseHTTPRequestHandler, model: str, delta: dict, finish: str | None) -> None:
    chunk = {"id": "chatcmpl-fake", "object": "chat.completion.chunk", "created": int(time.time()),
             "model": model, "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    handler.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())


def make_handler(scripts: dict[str, list[str]]):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def _json(self, data: dict) -> None:
            body = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path.rstrip("/").endswith("/models"):
                self._json({"object": "list", "data": [{"id": m, "object": "model", "owned_by": "fake", "root": m,
                                                        "max_model_len": 32768} for m in sorted(scripts)]})
            elif self.path.rstrip("/").endswith("/server_info"):
                self._json({"version": "fake-0", "model_path": "fake", "tool_call_parser": "fake",
                            "reasoning_parser": None, "context_length": 32768})
            else:
                self.send_error(404)

        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            model = req.get("model") or next(iter(scripts))
            step = next_step(scripts.get(model, []), req.get("messages", [])) if req.get("tools") \
                else {"text": "Fix the issue"}
            usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
            call = {"id": f"call_{time.time_ns()}", "type": "function",
                    "function": {"name": step.get("tool"), "arguments": json.dumps(step.get("args", {}))}}
            if not req.get("stream"):
                msg = ({"role": "assistant", "content": None, "tool_calls": [call]} if "tool" in step
                       else {"role": "assistant", "content": step["text"]})
                self._json({"id": "chatcmpl-fake", "object": "chat.completion", "model": model,
                            "choices": [{"index": 0, "message": msg,
                                         "finish_reason": "tool_calls" if "tool" in step else "stop"}],
                            "usage": usage})
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            if "tool" in step:
                sse(self, model, {"role": "assistant", "tool_calls": [{"index": 0, **call}]}, None)
                sse(self, model, {}, "tool_calls")
            else:
                sse(self, model, {"role": "assistant", "content": step["text"]}, None)
                sse(self, model, {}, "stop")
            chunk = {"id": "chatcmpl-fake", "object": "chat.completion.chunk", "model": model,
                     "choices": [], "usage": usage}
            self.wfile.write(f"data: {json.dumps(chunk)}\n\ndata: [DONE]\n\n".encode())

    return Handler


def serve(port: int, scripts: dict[str, list[str]]) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(scripts))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--model", default="fake/qwen")
    ap.add_argument("--script", nargs="*", default=[])
    args = ap.parse_args()
    server = serve(args.port, {args.model: args.script})
    print(f"fake LLM on http://127.0.0.1:{args.port}/v1 serving {args.model}", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
