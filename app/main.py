import os ## For accessing environment variables/reading computer files
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates ## For reading HTML templates
from fastapi.staticfiles import StaticFiles ## For taking care of static files like CSS
from fastapi.responses import RedirectResponse ## For redirecting users to different pages
from fastapi import File, UploadFile ## For handling CSV file uploads
from starlette.middleware.sessions import SessionMiddleware ## Allows the app to uses "sessions" and remember information across different pages
from supabase import create_client, Client ## For connecting to Supabase
from dotenv import load_dotenv ## For loading environment variables from .env file
import io ## Wrapping file data to look like file from local machine
import csv ## Gives tools like csvDictReader
import uuid ## Used to give batch tags to groups of data

## Connecting to Supabase
load_dotenv() ## Load environment variables from .env file

url: str = os.environ.get("SUPABASE_URL") ## Get Supabase URL from environment variable
key: str = os.environ.get("SUPABASE_KEY") ## Get Supabase Key from environment variable

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


##  Decorator for the root endpoint and then define 
##  the function that will be called when the root endpoint is accessed
@app.get("/")
def read_root(request: Request):
    ##  Root endpoint... redirects to admin login page as main entry point of program
    return RedirectResponse(url="/admin", status_code=303) 

##  Admin page information
@app.get("/admin")
def admin_logIn(request: Request):

    ##  Check to see if admin is already logged in
    if request.session.get("is_admin"):
        return RedirectResponse(url="/dashboard", status_code=303)

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
                                      context={"ev_name": request.session.get("event_name")})   
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
    request.session["event_name"]= event_name   

    if request.session.get("event_name"):
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
        update = {"event_name": request.session.get("event_name"), "user_id": check.data[0]['user_id']}
        supabase.table('attendance_log').insert(update).execute()

        return templates.TemplateResponse(request=request,
                                          name="index.html",
                                          context={"status": "success",
                                                   "message": f"Welcome, {check.data[0]['first_name']} {check.data[0]['last_name']}!",
                                                   "event_name": request.session.get("event_name")})

    else:

        return templates.TemplateResponse(request=request,
                                          name="index.html",
                                          context={"status": "error", "message": "User not in database.", "event_name": request.session.get("event_name")})

@app.get("/logout")
def logout(request: Request):

    ##  Check to see if user is admin (security measure to prevent malicious users
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303)
        
    ## Clears the session dictionary, including event_name and is_admin to rest for next login/event
    request.session.clear() 
    return templates.TemplateResponse(request=request,
                                      name="logout.html",
                                      context={"status": "log out", "message": "Signing out ...."})

@app.get("/end")
def end_event(request: Request):
    ##  Check to see if user is admin (security measure to prevent malicious users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303)

    ##  Remove event name from .session dictionary to reset for next event
    request.session.pop("event_name", None) 
    return templates.TemplateResponse(request=request,
                                      name="end.html",
                                      context={"message": "Ending Event ...."})

@app.get("/add_users")
def add_users(request: Request):
    return templates.TemplateResponse(request=request,
                                      name="add_users.html",
                                      context={})

@app.get("/add_onsite")
def onsite_get(request: Request):
    ##  Check to see if user is admin (security measure to prevent malicious users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303)

    ##  Added to see if flash message exists from successful user addition
    flash_msg = request.session.pop("flash_msg", "")

    if flash_msg:
        current_status = "success"

    else:
        flash_msg = "Scan new card to begin ..."
        current_status = "default"

    return templates.TemplateResponse(request=request,
                                       name="add_onsite.html",
                                       context={"status": current_status, "message": flash_msg})

@app.post("/add_onsite")
def onsite_post(request: Request, scanned_id: str = Form(...)):  
    ##  Check to see if user is admin (security measure to prevent malicious users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code = 303)

    ##  Check to make sure escape password wasn't inputted
    if scanned_id == ESCAPE_PASSWORD:
        return RedirectResponse(url="/add_users", status_code = 303)

    ##  Check to see if card id is already in the database
    checked = supabase.table('users').select('*').eq('card_id', scanned_id).execute()
    
    if checked.data:
        return templates.TemplateResponse(request=request,
                                          name="add_onsite.html",
                                          context={"status": "error", "message": "Card id already exists ... Please scan another."})
    ##  If card id is not in the database
    request.session["card_id"] = scanned_id
    return RedirectResponse(url="/onsite_form", status_code = 303)

@app.get("/onsite_form")
def onsite_form_get(request: Request):
    ##  Check to see if user is admin (security measure to prevent malicious users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code = 303)
    return templates.TemplateResponse(request=request,
                                      name="onsite_form.html",
                                      context={})

@app.post("/onsite_form")
def onsite_form_post(request: Request, first: str = Form(...), last: str = Form(...), cin: str = Form(...), email: str = Form(...), major: str = Form(...)):
    ## Check to see if user is admin (security measure to prevent malicious users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code = 303)

    
    ##  Just in case "somehow" a card wasn't scanned/stored
    if not request.session.get("card_id"):
        return RedirectResponse(url="/add_onsite", status_code = 303)


    ##  Add form values to update dictionary
    new_user = {"card_id": request.session.pop("card_id", None), "first_name": first,
                "last_name": last, "cin": cin, "major": major, "email": email}
    supabase.table('users').insert(new_user).execute()

    ##  Create a flash message
    request.session["flash_msg"] = f"{first} {last} has been successfully added to the database!"

    ## redirect back to scanning page with success message
    return RedirectResponse(url="/add_onsite", status_code = 303)

@app.get("/bulk_import")
def bulk_import_get(request: Request):
    ##  Check to see if user is admin (security measure to prevent malicious users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code = 303)

    return templates.TemplateResponse(request=request,
                                      name="bulk_import.html",
                                      context={})

@app.post("/bulk_import")
def bulk_import_post(request: Request, input_file: UploadFile = File(...)):
    ## Check to see if user is admin (security measure to prevent malicisous users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code = 303)

    ##  Take file, read it in byte form, decode from bytes to string, convert to 
    ##  csvDictReader readable format and parse
    file_in_bytes = input_file.file.read()

    decoded_string = file_in_bytes.decode('utf-8')

    input_data = csv.DictReader(io.StringIO(decoded_string))

    input_list = list(input_data)

    ##  "Tag" current data so it can be referenced later when adding card_id
    curr_batch_tag = str(uuid.uuid4())

    ##  Place into .session memory (cookies)
    request.session['batch_tag'] = curr_batch_tag

    ##  Add tag to each user in list
    for user in input_list:
        user["upload_tag"] = curr_batch_tag

    ##  After parsing, add user information to database, using CIN column
    ##  to avoid duplicates "UPSERT" allows to use a column to check for duplicates, overrides
    ##  existing data with new data if duplicate is found
    supabase.table('users').upsert(user, on_conflict='cin').execute()

    return RedirectResponse(url="/batch_scan", status_code=303)