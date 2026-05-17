#   Imports
import uvicorn ##  Gives the ability to run the server
import webbrowser ##  Gives the ability to open a web browser (Should be OS independent)
import threading ##  Gives the ability to run multiple processes at the same time (Used to run server and open browser at the same time)
import time ##  Give ability to "sleep"
from app.main import app ##  Imports the FastAPI app from main.py

##  Refactor to use operating system independent code to open browser in "kiosk" mode

def start_browser():
    chrome = webbrowser.get(r"'C:\Program Files\Google\Chrome\Application\chrome.exe' --kiosk %s")
    time.sleep(4)
    chrome.open("http://127.0.0.1:8000")



if __name__ == "__main__":
    ##  Start browser timer in a separate thread (background)
    threading.Thread(target=start_browser, daemon=True).start()

    ##  Start the server (Inside Python, no command prompt)
    uvicorn.run(app, host="127.0.0.1", port=8000)