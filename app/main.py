import os ## For accessing environment variables/reading computer files
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates ## For reading HTML templates
from fastapi.staticfiles import StaticFiles ## For taking care of static files like CSS
from fastapi.responses import RedirectResponse ## For redirecting users to different pages
from starlette.middleware.sessions import SessionMiddleware ## Allows the app to uses "sessions" and remember information across different pages
from supabase import create_client, Client ## For connecting to Supabase
from dotenv import load_dotenv ## For loading environment variables from .env file

## Connecting to Supabase
load_dotenv() ## Load environment variables from .env file

url: str = os.environ.get("SUPABASE_URL") ## Get Supabase URL from environment variable
key: str = os.environ.get("SUPABASE_KEY") ## Get Supabase Key from environment variable"

supabase = create_client(url, key) ## Create Supabase client using the URL and Key

##  Grabbing app admin password
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

##  Grabbing special "escape" password to exit scanning mode
ESCAPE_PASSWORD = os.environ.get("ESCAPE_PASSWORD")

##  Create FastAPI app
app = FastAPI()

## Adds middleware tool to the app object so it can be used
app.add_middleware(SessionMiddleware, secret_key=os.environ.get("SESSION_SECRET_KEY"))

##  Point Jinja to correct directory holding templates
templates = Jinja2Templates(directory="templates")

##  Mount the static files directory to serve CSS and other static assets
app.mount("/static", StaticFiles(directory="static"), name="static")

##  Global event variable to hold the current event name, which can be updated by the admin
current_name = ""


##  Decorator for the root endpoint and then define 
##  the function that will be called when the root endpoint is accessed
@app.get("/")
def read_root(request: Request):
    ##  Root endpoint... redirects to admin login page as main entry point of program
    return RedirectResponse(url="/admin", status_code=303) 

##  Admin page information
@app.get("/admin")
def admin_logIn(request: Request):

    ##  Check to see if an "error" status has been stored
    ##  Stores "" if no error message exists
    err_msg = request.session.pop("error", "")

    if err_msg:
        current_status = "error"

    else:
        current_status = "default"
    return templates.TemplateResponse(request=request,
                                      name="admin.html",
                                      context={"status": current_status, "message": err_msg})

@app.post("/admin-setup")
def admin_setup(request: Request, a_pass: str = Form(...)):

    ##  Check if the password entered matches the admin password
    if a_pass == ADMIN_PASSWORD:
        ## creates a session key "is_admin" and sets it to True, which can be used to check if the user is an admin on other pages
        request.session["is_admin"] = True

        return RedirectResponse(url="/dashboard", status_code=303)

    else:
        ## If password is incorrect, redirect back to login page and flash error message
        request.session["error"] = "Incorrect password, try again."
        return RedirectResponse(url="/admin", status_code=303)

@app.get("/dashboard")
def dash_page(request: Request):
    ##  Check to see if user is admin by checking the session key "is_admin" that was set during login
    if request.session.get("is_admin"):
        return templates.TemplateResponse(request=request,
                                      name="dashboard.html",
                                      context={})   
    else:
        return RedirectResponse(url="/admin", status_code=303)

@app.get("/event_name")
def get_event_name(request: Request):
    ## First check to see if user is admin (security measure to prevent malicious users 
    ## from accessing this page and changing the event name without permission)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303) ##   Redirects back to login page if user is not admin

    ##  Check to see if an "error" status has been stored
    err_msg = request.session.pop("error", "")

    if err_msg:
        current_status = "error"
    else:
        current_status = "default"
    ##  Get the event name from the database
    return templates.TemplateResponse(request=request,
                                      name="event_name.html",
                                      context={"status": current_status, "message": err_msg})

@app.post("/event_name")
def post_event_name(request: Request, event_name: str = Form(...)):
    ##  Check to see if user is admin (security measure to prevent malicious users 
    ## from accessing this page and changing the event name without permission)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303)

    ##  Update the event name in the database
    ##  Progress to scanning page
    global current_name 
    current_name = event_name   

    if current_name:
        ##  Store event name in a session variable
        request.session["event_name"] = current_name
        return RedirectResponse(url="/scan", status_code=303)

    else:
        request.session["error"] = "Please Enter a Valid Name."
        return RedirectResponse(url="/event_name", status_code=303)

@app.get("/scan")
def scan_get(request: Request):
    ## First check to see if user is admin (security measure to prevent malicious users 
    ## from accessing this page and changing the event name without permission)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303) ##   Redirects back to login page if user is not admin

    return templates.TemplateResponse(request=request,
                                      name="index.html",
                                      context={"status": "default", "message": f"Scanning for..... \n{request.session.get('event_name')}"})

@app.post("/scan")
def scan(request: Request, scanned_id: str = Form(...)):

    ## First check to see if user is admin (security measure to prevent malicious users 
    ## from accessing this page and changing the event name without permission)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303) ##   Redirects back to login page if user is not admin


    ##  Check to make sure escape password wasn't inputted
    if scanned_id == ESCAPE_PASSWORD:
        ##  Redirect to dashboard to use other admin functions
        return RedirectResponse(url="/dashboard", status_code=303)

    ##  Checking to make sure the scanned ID is in the database already
    check = supabase.table('users').select('*').eq('card_id', scanned_id).execute()

    if check.data:
        ##  Package data and update database: user_id
        update = {"event_name": current_name, "user_id": check.data[0]['user_id']}
        supabase.table('attendance_log').insert(update).execute()

        return templates.TemplateResponse(request=request,
                                          name="index.html",
                                          context={"status": "success",
                                                   "message": f"Welcome, {check.data[0]['first_name']} {check.data[0]['last_name']}!",
                                                   "event_name": current_name})

    else:

        return templates.TemplateResponse(request=request,
                                          name="index.html",
                                          context={"status": "error", "message": "User not in database.", "event_name": current_name})
       