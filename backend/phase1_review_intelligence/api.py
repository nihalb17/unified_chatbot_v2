import os
import json
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pipeline import run_pipeline

app = FastAPI()

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = os.path.join(os.path.dirname(__file__), "../data/themes_kb.json")

# In-memory status tracking
status = {"running": False, "last_run": None}

@app.get("/api/reviews/themes")
def get_themes():
    """Returns the latest Themes Knowledge Base."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"themes": [], "refresh_metadata": None}

@app.get("/api/reviews/status")
def get_status():
    """Returns the current pipeline status."""
    return status

@app.post("/api/reviews/refresh")
def refresh_reviews(background_tasks: BackgroundTasks):
    """Triggers the review intelligence pipeline in the background."""
    if status["running"]:
        return {"message": "Pipeline is already running."}
    
    status["running"] = True
    
    def run():
        try:
            run_pipeline()
            status["last_run"] = "Success"
        except Exception as e:
            print(f"Pipeline failed: {e}")
            status["last_run"] = f"Failed: {str(e)}"
        finally:
            status["running"] = False
            
    background_tasks.add_task(run)
    return {"message": "Pipeline started."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
