"""Test server — mimics detective.kusto.io for E2E testing.

Serves HTML pages with an inbox sidebar, challenge pages, and answer
submission. State is tracked in a JSON file so tests can verify results.

Usage:
    python tests/test_server.py                    # start on port 8765
    python tests/test_server.py --port 9000        # custom port
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse, RedirectResponse

CHALLENGES_PATH = Path(__file__).parent / "challenges.json"
STATE_PATH = Path(__file__).parent / "test_state.json"


def _load_challenges() -> list[dict]:
    import os
    cluster_uri = os.environ.get("DETECTIVE_CLUSTER_URI", "https://help.kusto.windows.net")
    raw = CHALLENGES_PATH.read_text(encoding="utf-8")
    raw = raw.replace("{cluster_uri}", cluster_uri)
    return json.loads(raw)


def _load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"solved": {}, "submissions": [], "logged_in": False}


def _save_state(state: dict) -> None:
    STATE_PATH.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def create_app() -> FastAPI:
    app = FastAPI(title="Detective Test Server")
    challenges = _load_challenges()
    challenge_map = {c["slug"]: c for c in challenges}

    def _sidebar_html(current_slug: str = "") -> str:
        """Build sidebar HTML listing all challenges with solved status."""
        items = []
        state = _load_state()
        for c in challenges:
            solved = c["slug"] in state.get("solved", {})
            mark = "✓" if solved else ""
            status_class = "solved" if solved else "unsolved"
            status_text = "COMPLETED" if solved else "NOT COMPLETED"
            active = "active" if c["slug"] == current_slug else ""
            items.append(
                f'<li class="case-item {status_class} {active}">'
                f'<a href="/inbox/{c["slug"]}">'
                f'<span class="checkmark">{mark}</span> '
                f'{c["name"]} '
                f'<span class="status-badge">{status_text}</span>'
                f'</a></li>'
            )
        return f'<ul class="case-list">{"".join(items)}</ul>'

    def _page(title: str, content: str, sidebar_slug: str = "") -> str:
        sidebar = _sidebar_html(sidebar_slug)
        return f"""<!DOCTYPE html>
<html><head><title>{title}</title>
<style>
body {{ font-family: sans-serif; display: flex; margin: 0; }}
.sidebar {{ width: 300px; background: #f5f5f5; padding: 20px;
           border-right: 1px solid #ddd; min-height: 100vh; }}
.main {{ flex: 1; padding: 30px; max-width: 800px; }}
.case-list {{ list-style: none; padding: 0; }}
.case-item {{ padding: 8px 12px; margin: 4px 0; border-radius: 4px; }}
.case-item a {{ text-decoration: none; color: #333; display: block; }}
.case-item.active {{ background: #e3f2fd; }}
.case-item .checkmark {{ color: green; font-weight: bold; }}
.case-item .status-badge {{ font-size: 0.8em; color: #888; }}
.case-item.solved .status-badge {{ color: green; }}
.case-item.unsolved .status-badge {{ color: #c00; }}
input[type="text"] {{ padding: 8px; width: 300px; font-size: 16px; }}
button {{ padding: 8px 20px; font-size: 16px; cursor: pointer;
         background: #1976d2; color: white; border: none; border-radius: 4px; }}
button:hover {{ background: #1565c0; }}
.result {{ padding: 12px; margin: 10px 0; border-radius: 4px; }}
.result.correct {{ background: #e8f5e9; color: #2e7d32; }}
.result.wrong {{ background: #ffebee; color: #c62828; }}
.training {{ background: #fff8e1; padding: 15px; border-radius: 4px;
            border: 1px solid #ffe082; margin: 15px 0; }}
.login-form {{ max-width: 400px; margin: 100px auto; text-align: center; }}
</style></head>
<body>
<div class="sidebar">
<h3>Cases</h3>
{sidebar}
</div>
<div class="main">{content}</div>
</body></html>"""

    @app.get("/", response_class=HTMLResponse)
    async def root():
        state = _load_state()
        if not state.get("logged_in"):
            return HTMLResponse(_page("Detective Agency", """
                <div class="login-form">
                <h1>Kusto Detective Agency</h1>
                <p>Test Environment</p>
                <button onclick="window.location='/login'">Go to Inbox</button>
                </div>
            """))
        return RedirectResponse("/inbox")

    @app.get("/login", response_class=HTMLResponse)
    async def login_page():
        return HTMLResponse("""<!DOCTYPE html>
<html><head><title>Log In</title>
<style>
body { font-family: sans-serif; }
.login-form { max-width: 400px; margin: 100px auto; text-align: center; }
input[type="text"] { padding: 8px; width: 300px; font-size: 16px; margin: 10px 0; }
button { padding: 8px 20px; font-size: 16px; cursor: pointer;
         background: #1976d2; color: white; border: none; border-radius: 4px; }
</style></head>
<body>
<div class="login-form">
<h2>Log in</h2>
<form method="post" action="/login">
<p><input type="text" name="cluster_url" placeholder="Cluster URL" /></p>
<p><button type="submit">Log In</button></p>
</form>
</div>
</body></html>""")

    @app.post("/login")
    async def login_submit(cluster_url: str = Form("")):
        state = _load_state()
        state["logged_in"] = True
        state["cluster_url"] = cluster_url
        _save_state(state)
        return RedirectResponse("/inbox", status_code=303)

    @app.post("/api/reset")
    async def reset_all():
        """Reset all state — all challenges become unsolved."""
        _save_state({"solved": {}, "submissions": [], "logged_in": False})
        return {"status": "reset", "message": "All challenges reset"}

    @app.post("/api/reset/{slug}")
    async def reset_challenge(slug: str):
        """Reset a single challenge — mark it as unsolved."""
        state = _load_state()
        state.get("solved", {}).pop(slug, None)
        _save_state(state)
        return {"status": "reset", "slug": slug}

    @app.get("/inbox", response_class=HTMLResponse)
    async def inbox():
        content = "<h1>Inbox</h1><p>Select a case from the sidebar to begin.</p>"
        return HTMLResponse(_page("Inbox", content))

    @app.get("/inbox/{slug}", response_class=HTMLResponse)
    async def challenge_page(slug: str):
        c = challenge_map.get(slug)
        if not c:
            return HTMLResponse(_page("Not Found", "<h1>Case not found</h1>"), 404)

        state = _load_state()
        solved = slug in state.get("solved", {})

        problem_html = c["problem"].replace("\n", "<br>")
        content = f"""
        <h1>{c["name"]}</h1>
        <div class="challenge-text">{problem_html}</div>
        <p><a href="/inbox/{slug}/training">Train me for the case</a></p>
        """

        if solved:
            answer = state["solved"][slug]["answer"]
            content += f"""
            <div class="result correct">
            <strong>✓ Solved!</strong> Your answer: {answer}
            </div>
            """

        # Always show submission form (enables re-solving for benchmarks)
        content += f"""
        <h3>Submit your answer</h3>
        <form method="post" action="/inbox/{slug}/submit">
        <p><input type="text" name="answer" placeholder="Your answer" /></p>
        <p><button type="submit">Submit</button></p>
        </form>
        """

        return HTMLResponse(_page(c["name"], content, sidebar_slug=slug))

    @app.get("/inbox/{slug}/training", response_class=HTMLResponse)
    async def training_page(slug: str):
        c = challenge_map.get(slug)
        if not c:
            return HTMLResponse(_page("Not Found", "<h1>Not found</h1>"), 404)

        training_html = c.get("training", "No training available.").replace("\n", "<br>")
        content = f"""
        <h1>{c["name"]} — Training</h1>
        <div class="training">{training_html}</div>
        <p><a href="/inbox/{slug}">Back to challenge</a></p>
        """
        return HTMLResponse(_page("Training", content, sidebar_slug=slug))

    @app.post("/inbox/{slug}/submit", response_class=HTMLResponse)
    async def submit_answer(slug: str, answer: str = Form("")):
        c = challenge_map.get(slug)
        if not c:
            return HTMLResponse(_page("Not Found", "<h1>Not found</h1>"), 404)

        state = _load_state()
        answer = answer.strip()
        correct = answer == c["answer"]

        submission = {
            "slug": slug,
            "answer": answer,
            "correct": correct,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        state.setdefault("submissions", []).append(submission)

        if correct:
            state.setdefault("solved", {})[slug] = {
                "answer": answer,
                "solved_at": submission["timestamp"],
            }

        _save_state(state)

        if correct:
            result_html = f"""
            <div class="result correct">
            <strong>✓ Correct!</strong> The answer is {answer}.
            </div>
            """
        else:
            result_html = f"""
            <div class="result wrong">
            <strong>✗ Wrong answer.</strong> "{answer}" is not correct. Try again.
            </div>
            <form method="post" action="/inbox/{slug}/submit">
            <p><input type="text" name="answer" placeholder="Your answer" /></p>
            <p><button type="submit">Submit</button></p>
            </form>
            """

        problem_html = c["problem"].replace("\n", "<br>")
        content = f"""
        <h1>{c["name"]}</h1>
        <div class="challenge-text">{problem_html}</div>
        {result_html}
        """
        return HTMLResponse(_page(c["name"], content, sidebar_slug=slug))

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    port = 8765
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        port = int(sys.argv[idx + 1])

    # Reset state on manual start
    _save_state({"solved": {}, "submissions": [], "logged_in": False})
    print(f"Test server running on http://localhost:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)
