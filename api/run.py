"""
api/run.py — programmatic uvicorn entry point for BizBrief.

Use this instead of the uvicorn CLI so that forwarded_allow_ips=[] is passed
directly to uvicorn.Config before the Config object is constructed.  The CLI
approach reads FORWARDED_ALLOW_IPS from the environment BEFORE api.main is
imported, so setting os.environ["FORWARDED_ALLOW_IPS"] inside api.main is
always too late (RT-001 root cause).

Start the server with:
    uv run python -m api.run

Never use:
    uv run uvicorn api.main:app --reload
...unless you also export FORWARDED_ALLOW_IPS= in the shell before running
(see .env.example).
"""

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
        forwarded_allow_ips=[],  # never trust XFF — no proxy in front of this server
    )
