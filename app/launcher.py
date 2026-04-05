import sys ##   Gives the ability to look at operating system
import subprocess ##    Gives the ability to start a process and then run it in the backgroun
import time ##  Give ability to "sleep"


##  Reads what type of operating system and stores a 
##  common phrase that is OS dependent  
operating_system = sys.platform


if operating_system == "win32":
    print ("Starting Windows Launcher")
    ##  Command to spin up server
    subprocess.Popen(["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"], shell=True)
    
    ##  Brief pause so server can start completely
    time.sleep(4)

    ##  Start up app in "kiosk" mode
    subprocess.Popen(["start", "chrome", "--kiosk", "http://localhost:8000"], shell=True)

elif operating_system == "darwin":
    print("Starting Mac Launcher")
elif operating_system == "linux":
    print("Starting Linux")
else:
    print("Unsupported OS!")
