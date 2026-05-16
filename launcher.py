import sys ##   Gives the ability to look at operating system
import subprocess ##    Gives the ability to start a process and then run it in the backgroun
import time ##  Give ability to "sleep"


##  Reads what type of operating system and stores a 
##  common phrase that is OS dependent  
operating_system = sys.platform

##  Command to spin up server
subprocess.Popen(["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"])

##  Variable for localhost link
link = "http://localhost:8000"

##  Brief pause so server can start completely
time.sleep(4)

if operating_system == "win32":
    print ("Starting Windows Launcher")

    ##  Start up app in "kiosk" mode
    subprocess.Popen(["start", "chrome", "--kiosk", link], shell=True)

elif operating_system == "darwin":
    print("Starting Mac Launcher")

    ##  Start up app in "kiosk" mode
    subprocess.Popen(["open", "-a", "Google Chrome", "--args", "--kiosk", link])

elif operating_system == "linux":
    print("Starting Linux")

    ##  Start up app in "kiosk" mode
    subprocess.Popen(["chromium-browser", "--kiosk", link])
else:
    print("Unsupported OS!")
