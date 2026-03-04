#!/usr/bin/env python
"""Production server runner."""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8888,
        workers=4,
    )
