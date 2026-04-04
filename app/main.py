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

##  Temp setup password
SETUP_PASS = "setup"

## Connecting to Supabase
load_dotenv() ## Load environment variables from .env file

url: str = os.environ.get("SUPABASE_URL") ## Get Supabase URL from environment variable
key: str = os.environ.get("SUPABASE_KEY") ## Get Supabase Key from environment variable

##  Check so that supabase doesn't attempt to conenct to a non-existent database
if not os.path.exists(".env"):
    supabase = None

else:
    supabase = create_client(url, key) ## Create Supabase client using the URL and Key

##  Grabbing app admin password
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")

##  Grabbing special "escape" password to exit scanning mode
ESCAPE_PASSWORD = os.environ.get("ESCAPE_PASSWORD")

##  Grabbing club name, set up during initial startup
CLUB_NAME = os.environ.get("CLUB_NAME")

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
    ##  Root endpoint... works as "landing page" for program start-up

    return templates.TemplateResponse(request=request,
                                      name="landing.html",
                                      context={"club": CLUB_NAME})

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

    if not os.path.exists(".env") and a_pass == SETUP_PASS:
        ##  Create security flag so malicious users don't gain unwarranted access
        request.session["is_setup"] = True
        return RedirectResponse(url="/setup", status_code=303)

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
    ##  Check to see if user is admin (security measure to prevent malicious users)
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
    ##  Check to see if user is admin (security measure to prevent malicisous users)
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
    supabase.table('users').upsert(input_list, on_conflict='cin').execute()

    return RedirectResponse(url="/batch_scan", status_code=303)

@app.get("/batch_scan")
def batch_scan_get(request: Request):
    ##  Check to see if user is admin (security measure to prevent malicisous users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code = 303)
    
    ##  Retrieve unique "tag"/identifier to keep track of which users were recently uploaded
    batch_tag = request.session.get('batch_tag')

    ##  Pull out 1 row of data (essentially 1 users' information)
    current_user = supabase.table('users').select('*').eq('upload_tag', batch_tag).is_('card_id', 'null').limit(1).execute()

    if not current_user.data:
        ##  If all users have been updated
        request.session.pop('batch_tag', None)
        return RedirectResponse(url="/add_users", status_code= 303)


    ##  To grab count of remaining students
    current_count = supabase.table('users').select('*', count='exact').eq('upload_tag', batch_tag).is_('card_id', 'null').execute()

    message = request.session.pop("flash_msg", "")
    status = request.session.pop("status", "")

    
    return templates.TemplateResponse(request=request,
                                      name="batch_scan.html",
                                      context={"status": status, "user": current_user.data[0], "remaining": current_count.count, "message": message})

@app.post("/batch_scan")
def batch_scan_post(request: Request, cin: str = Form(...), scanned_id: str = Form(...)):
    ##  Check to see if user is admin (security measure to prevent malicisous users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code = 303)

    if scanned_id == ESCAPE_PASSWORD:
        return RedirectResponse(url="/add_users", status_code = 303)

    ##  Check to see if card has already been assigned
    check = supabase.table('users').select('*').eq('card_id', scanned_id).execute()

    if check.data:
        request.session["flash_msg"] = "Card already assigned. Try another card"
        request.session["status"] = "error"
        return RedirectResponse(url="/batch_scan", status_code = 303)

    ##  Update database with card_id (scanned_id) using CIN as a reference
    supabase.table('users').update({'card_id': scanned_id}).eq('cin', cin).execute()

    request.session["flash_msg"] = "Card Assigned"
    request.session["status"] = "success"

    return RedirectResponse(url="/batch_scan", status_code = 303)

@app.get("/lost_found")
def lost_found_get(request: Request):
    ##  Check to see if user is admin (security measure to prevent malicisous users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code = 303)

    message = request.session.pop("flash_msg", "")
    status = request.session.pop("status", "")

    return templates.TemplateResponse(request=request,
                                      name="lost_found.html",
                                      context={"status": status, "message": message})

@app.post("/lost_found")
def lost_found_post(request: Request, scanned_id: str = Form(...)):
    ##  Check to see if user is admin (security measure to prevent malicisous users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code = 303)

    ##  Escape check
    if scanned_id == ESCAPE_PASSWORD:
        return RedirectResponse(url="/add_users", status_code = 303)

    card = supabase.table('users').select('*').eq('card_id', scanned_id).execute()


    ##  If card isn't found in database (i.e. not assigned)
    if not card.data:
        request.session["flash_msg"] = "Card not found in database."
        request.session["status"] = "error"

        return RedirectResponse(url="/lost_found", status_code = 303)

    request.session["flash_msg"] = f"Card belongs to {card.data[0]['first_name']} {card.data[0]['last_name']}"
    request.session["status"] = "success"

    return RedirectResponse(url="/lost_found", status_code = 303)

@app.post("/setup")
def setup(request: Request, name: str = Form(...), url: str = Form(...), key: str = Form(...),
          admin: str = Form(...), escape: str = Form(...), session_secret: str = Form(...)):
    ##  Check to see if user is admin (security measure to prevent malicisous users)
    if not request.session.get("is_setup"):
        return RedirectResponse(url="/admin", status_code = 303)

    ##  Create .env file and write user chosen secret words
    with open(".env", "w") as file:
        file.write(f"""CLUB_NAME="{name}"
SUPABASE_URL="{url}"
SUPABASE_KEY="{key}"
ADMIN_PASSWORD="{admin}"
ESCAPE_PASSWORD="{escape}"
SESSION_SECRET_KEY="{session_secret}"
""")

    load_dotenv(override=True) ##   Reload dotenv so that the newly created .env gets loaded

    ##  Connection to previously created supabase database
    db_url = os.environ.get("SUPABASE_URL")
    db_key = os.environ.get("SUPABASE_KEY")

    global supabase
    create_client(db_url, db_key)

    ##  Clear .session variables (security check)
    request.session.clear()
    return RedirectResponse(url="/admin", status_code=303)
    