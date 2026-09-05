##  Imports
import os ## For accessing environment variables/reading computer files
import csv ## Gives tools like csvDictReader
import uuid ## Used to give batch tags to groups of data
import secrets ## Used to create secret hash used in the app
import signal ## Used to send signals (specifically "kill" signal)
import io ## Wrapping file data to look like file from local machine
import time ## Used to create delay for synchronization purposes
import sys ## Used in logic to check if app is being ran as a bundled executable

from datetime import datetime, timezone ## Used to stamp when an event began, for duplicate scan detection

from fastapi import FastAPI, Request, Form, BackgroundTasks ## FastAPI tools for creating app, handling requests, and form data
from fastapi.templating import Jinja2Templates ## For reading HTML templates
from fastapi.staticfiles import StaticFiles ## For taking care of static files like CSS
from fastapi.responses import RedirectResponse ## For redirecting users to different pages
from fastapi import File, UploadFile ## For handling CSV file uploads
from starlette.middleware.sessions import SessionMiddleware ## Allows the app to uses "sessions" and remember information across different pages
from supabase import create_client ## For connecting to Supabase
from dotenv import load_dotenv ## For loading environment variables from .env file

##  Logic to check if app is being ran from pyinstaller package versus through regular IDE/terminal
if getattr(sys, 'frozen', False):
    ##  When being ran as a bundled executable, the path to static and templates change
    ##  This logic finds that base path and sets it so the app can then find the static and template files correctly
    base_path = sys._MEIPASS

else:
    ##  When ran through terminal or IDE, the base path is where the project is located
    base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


## Connecting to Supabase
load_dotenv() ## Load environment variables from .env file

url: str = os.environ.get("SUPABASE_URL") ## Get Supabase URL from environment variable
key: str = os.environ.get("SUPABASE_KEY") ## Get Supabase Key from environment variable

##  Check so that supabase doesn't attempt to conenct to a non-existent database
if not url or not key:
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
templates = Jinja2Templates(directory=os.path.join(base_path, "templates"))

##  Mount the static files directory to serve CSS and other static assets
app.mount("/static", StaticFiles(directory=os.path.join(base_path, "static")), name="static")


##  Helper to record a user's attendance for the event currently stored in the session.
##  Used by /scan, /onsite_form and /onsite_cin so check-in logic only lives in one place.
##  Returns one of:
##      "recorded"  - a new attendance row was written
##      "duplicate" - this member was already logged for this event, nothing written
##      "no_event"  - no event is running, nothing written
##      "error"     - the database could not be reached, nothing written
def log_attendance(request: Request, user_id: str) -> str:

    event_name = request.session.get("event_name")

    ##  No event set means there is nothing to attach attendance to.
    ##  The caller still succeeds, it just tells the user attendance wasn't recorded.
    if not event_name:
        return "no_event"

    ##  When this event was started. Used as the lower bound so that re-running an
    ##  event under the same name later is treated as a separate occasion.
    started_at = request.session.get("event_started_at")

    try:
        ##  Has this member already been logged for this event?
        already = supabase.table('attendance_log').select('log_id').eq('user_id', user_id).eq('event_name', event_name)

        if started_at:
            already = already.gte('scan_time', started_at)

        if already.execute().data:
            return "duplicate"

        supabase.table('attendance_log').insert({"event_name": event_name, "user_id": user_id}).execute()

    except Exception as error:
        print(f"[attendance] could not log user '{user_id}' for '{event_name}': {error}")
        return "error"

    return "recorded"


##  Helper to look a member up by the details they can be expected to know.
##  Email is the near-unique key, so we search on that and then confirm the name.
##  Returns (user_row_or_None, name_matched) so the caller can tell the difference
##  between "confirmed this person" and "that email belongs to somebody else".
def find_member(first: str, last: str, email: str):

    ##  ilike gives us a case-insensitive match on the email
    result = supabase.table('users').select('*').ilike('email', email.strip()).execute()

    if not result.data:
        return None, False

    ##  Look for a row where the typed name also lines up (ignoring case/extra spaces)
    for row in result.data:
        if (str(row.get('first_name', '')).strip().lower() == first.strip().lower()
                and str(row.get('last_name', '')).strip().lower() == last.strip().lower()):
            return row, True

    ##  Email is on file but under a different name, let the caller refuse the request
    return result.data[0], False


##  Helper to pull the attendance feed for a single event.
##  Every analytics view needs the same join, so it only lives here.
##  Returns (rows, error_message). error_message is None on success, otherwise the
##  caller renders it instead of the feed rather than dying with a 500.
def fetch_attendance(event_name: str):

    try:
        ## Grab attendance data using a 'join'
        raw = supabase.table('attendance_log').select('scan_time, users(first_name, last_name)').eq('event_name', event_name).execute()

    except Exception as error:
        ##  Most likely cause is a database that is missing the attendance_log -> users
        ##  foreign key, which PostgREST needs before it will build the join at all.
        ##  See the "Upgrading an existing database" section of the README.
        print(f"[analytics] attendance lookup failed for '{event_name}': {error}")
        return [], "Attendance data is unavailable. The database may be misconfigured - see an officer."

    rows = []

    for data in raw.data:
        ##  Skip any log entry whose member record no longer exists so one bad
        ##  row can't take down the whole feed
        member = data.get('users')

        if not member:
            continue

        rows.append({'time': data['scan_time'],
                     'name': f"{member['first_name']} {member['last_name']}"})

    return rows, None


##  Helper to build the dropdown of past events, excluding whichever event is live.
##  Returns (sorted_names, error_message) using the same convention as fetch_attendance.
def past_event_names(current_event: str):

    try:
        ##  Grab previous event names for dropdown menu
        events = supabase.table('attendance_log').select('event_name').execute()

    except Exception as error:
        print(f"[history] event list lookup failed: {error}")
        return [], "Past events could not be loaded. The database may be misconfigured - see an officer."

    ##  Set to hold event names
    event_set = set()

    for event in events.data:
        if event.get('event_name') and event['event_name'] != current_event:
            event_set.add(event['event_name'])

    return sorted(event_set), None


##  Decorator for the root endpoint and then define
##  the function that will be called when the root endpoint is accessed
@app.get("/")
def read_root(request: Request):
    ##  Root endpoint... works as "landing page" for program start-up

    ##  Ensures previous session's cookies (passwords, event names, etc) have been cleared for new session
    request.session.clear()

    if not os.path.exists(".env"):
        ##  Create security flag so malicious users don't gain unwarranted access
        request.session["is_setup"] = True

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
                                      context={"status": current_status, "message": err_msg, "club": CLUB_NAME})

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
        ##  Stamp when this event began. Duplicate detection looks for a previous scan
        ##  *since this moment*, so reusing an event name (a weekly meeting, say) starts
        ##  a fresh window instead of permanently blocking everyone who ever attended.
        request.session["event_started_at"] = datetime.now(timezone.utc).isoformat()

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

    ##  An enrollment that started from this screen redirects back here with a result
    ##  to show. index.html reverts itself to the scanning prompt after a few seconds.
    flash_msg = request.session.pop("flash_msg", "")

    if flash_msg:
        return templates.TemplateResponse(request=request,
                                          name="index.html",
                                          context={"status": request.session.pop("status", "success"),
                                                   "message": flash_msg,
                                                   "event_name": request.session.get("event_name")})

    return templates.TemplateResponse(request=request,
                                      name="index.html",
                                      context={"status": "default", "message": f"Scanning for..... \n{request.session.get('event_name')}"})

@app.post("/scan")
def scan(request: Request, scanned_id: str = Form(...)):

    ## First check to see if user is admin (security measure to prevent malicious users 
    ## from accessing this page and changing the event name without permission)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303) ##   Redirects back to login page if user is not admin

    ##  Every database call in the scan loop is wrapped together. A failure here must
    ##  never strand the terminal on an error page, so we fall through to the scanning
    ##  screen with a message and the input box still live for the next member.
    try:
        admin = supabase.table('admin').select('*').eq('nfc_id', scanned_id).execute()

        ##  Check to make sure escape password wasn't inputted
        if scanned_id == ESCAPE_PASSWORD or admin.data:
            ##  Redirect to dashboard to use other admin functions
            return RedirectResponse(url="/dashboard", status_code=303)

        ##  Checking to make sure the scanned ID is in the database already
        check = supabase.table('users').select('*').eq('card_id', scanned_id).execute()

        if check.data:
            ##  Record the attendance against the event held in the session
            recorded = log_attendance(request, check.data[0]['user_id'])

    except Exception as error:
        print(f"[scan] check-in failed for card '{scanned_id}': {error}")

        return templates.TemplateResponse(request=request,
                                          name="index.html",
                                          context={"status": "error",
                                                   "message": "Could not reach the database. Please scan again or see an officer.",
                                                   "event_name": request.session.get("event_name")})

    if check.data:

        member_name = f"{check.data[0]['first_name']} {check.data[0]['last_name']}"

        ##  Tailor the screen to what actually happened to their attendance
        if recorded == "duplicate":
            ##  Not a failure - they simply tapped twice, or were checked in while
            ##  being added. Amber rather than red so officers can tell at a glance.
            status = "warning"
            greeting = f"You're already checked in, {member_name}."

        elif recorded == "no_event":
            status = "success"
            greeting = f"Welcome, {member_name}! (No active event - attendance not recorded.)"

        elif recorded == "error":
            status = "error"
            greeting = f"Welcome, {member_name}! (Attendance could not be saved - see an officer.)"

        else:
            status = "success"
            greeting = f"Welcome, {member_name}!"

        return templates.TemplateResponse(request=request,
                                          name="index.html",
                                          context={"status": status,
                                                   "message": greeting,
                                                   "event_name": request.session.get("event_name")})

    else:
        ##  Card isn't on file. Rather than dead-ending, offer to enroll them here and
        ##  now. The card is held aside until an officer confirms, so a stray tap
        ##  (building access card, bus pass) can be waved off without touching the database.
        request.session["unknown_card"] = scanned_id

        ##  Set the return destination now rather than on confirmation, so that
        ##  cancelling the prompt also comes back to the scanning terminal
        request.session["enroll_origin"] = "/scan"

        return RedirectResponse(url="/confirm_add", status_code=303)

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

    ##  Clear the start stamp too, so the next event gets a fresh duplicate window
    request.session.pop("event_started_at", None)

    return templates.TemplateResponse(request=request,
                                      name="end.html",
                                      context={"message": "Ending Event ...."})

@app.get("/add_users")
def add_users(request: Request):
    return templates.TemplateResponse(request=request,
                                      name="add_users.html",
                                      context={})

@app.get("/confirm_add")
def confirm_add_get(request: Request):
    ##  Check to see if user is admin (security measure to prevent malicious users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303)

    ##  Nothing pending means somebody navigated here directly
    if not request.session.get("unknown_card"):
        return RedirectResponse(url="/scan", status_code=303)

    return templates.TemplateResponse(request=request,
                                      name="confirm_add.html",
                                      context={"status": "warning",
                                               "message": "Card not recognized."})

@app.post("/confirm_add")
def confirm_add_post(request: Request):
    ##  Check to see if user is admin (security measure to prevent malicious users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303)

    card_id = request.session.pop("unknown_card", None)

    if not card_id:
        return RedirectResponse(url="/scan", status_code=303)

    ##  Officer confirmed, so promote the held card into the enrollment flow.
    ##  enroll_origin was already set to /scan when the card was held aside.
    request.session["card_id"] = card_id

    return RedirectResponse(url="/onsite_form", status_code=303)

@app.get("/cancel_enroll")
def cancel_enroll(request: Request):
    ##  Check to see if user is admin (security measure to prevent malicious users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303)

    ##  Abandon any half-finished enrollment. Reached by the Cancel button and by the
    ##  inactivity timeout, so a member who walks away can't leave the kiosk stranded.
    request.session.pop("unknown_card", None)
    request.session.pop("card_id", None)
    request.session.pop("pending_first", None)
    request.session.pop("pending_last", None)
    request.session.pop("pending_email", None)

    return RedirectResponse(url=request.session.pop("enroll_origin", "/add_onsite"), status_code=303)

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

    admin = supabase.table('admin').select('*').eq('nfc_id', scanned_id).execute()

    ##  Check to make sure escape password wasn't inputted
    if scanned_id == ESCAPE_PASSWORD or admin.data:
        return RedirectResponse(url="/add_users", status_code = 303)

    ##  Check to see if card id is already in the database
    checked = supabase.table('users').select('*').eq('card_id', scanned_id).execute()
    
    if checked.data:
        return templates.TemplateResponse(request=request,
                                          name="add_onsite.html",
                                          context={"status": "error", "message": "Card id already exists ... Please scan another."})
    ##  If card id is not in the database
    request.session["card_id"] = scanned_id

    ##  This enrollment belongs to the add-users terminal, so drop any leftover
    ##  destination from an earlier enrollment that began at the scanning screen
    request.session.pop("enroll_origin", None)

    return RedirectResponse(url="/onsite_form", status_code = 303)

@app.get("/onsite_form")
def onsite_form_get(request: Request):
    ##  Check to see if user is admin (security measure to prevent malicious users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code = 303)

    ##  Unpack .session variables (if populated)
    first = request.session.pop("first", "")
    last = request.session.pop("last", "")
    email = request.session.pop("email", "")
    message = request.session.pop("flash_msg", "")
    status = request.session.pop("status", "")

    ##  Return variables so fields can be filled out
    ##  Makes it look like nothing happened
    return templates.TemplateResponse(request=request,
                                        name="onsite_form.html",
                                        context={'first': first, 'last': last,
                                                'email': email,
                                                'status': status, 'message': message})

##  Where an in-progress enrollment should return to once it finishes or is abandoned.
##  Defaults to the add-users terminal, but becomes /scan when the flow was entered by
##  tapping an unrecognized card at check-in.
def enroll_return(request: Request) -> str:
    return request.session.pop("enroll_origin", "/add_onsite")

@app.post("/onsite_form")
def onsite_form_post(request: Request, first: str = Form(...), last: str = Form(...), email: str = Form(...)):
    ##  Check to see if user is admin (security measure to prevent malicious users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code = 303)


    ##  Just in case "somehow" a card wasn't scanned/stored
    card_id = request.session.get("card_id")

    if not card_id:
        return RedirectResponse(url="/add_onsite", status_code = 303)

    ##  Use the details the member typed to see if we already have them on file
    member, name_matched = find_member(first, last, email)

    ##  Email belongs to somebody with a different name.
    ##  Refuse rather than risk attaching this card to the wrong person.
    if member and not name_matched:
        request.session["flash_msg"] = "Those details don't match our records. Please check your spelling."
        request.session["status"] = "error"

        ##  Prepare valid data to be retransmitted without user having to do it
        request.session['first'] = first
        request.session['last'] = last
        request.session['email'] = email

        return RedirectResponse(url="/onsite_form", status_code=303)

    ##  We don't know this person yet, so send them on to collect CIN and major
    if not member:
        request.session['pending_first'] = first
        request.session['pending_last'] = last
        request.session['pending_email'] = email

        return RedirectResponse(url="/onsite_cin", status_code=303)

    ##  From here we have confirmed the member. Attach the card only if they don't
    ##  already have one on file (a card already registered stays untouched).
    if not member.get('card_id'):
        supabase.table('users').update({'card_id': card_id}).eq('user_id', member['user_id']).execute()
        flash = f"Welcome, {member['first_name']}! Card registered"

    else:
        flash = f"{member['first_name']}, a card is already registered to you"

    ##  Enrolling doubles as a check-in for the running event
    recorded = log_attendance(request, member['user_id'])

    if recorded == "recorded":
        flash += " and you're checked in!"

    elif recorded == "duplicate":
        flash += " - you were already checked in."

    elif recorded == "error":
        flash += " (attendance could not be saved - see an officer)."

    else:
        flash += " (no active event - attendance not recorded)."

    ##  Card has been dealt with, clear it so the next member starts fresh
    request.session.pop("card_id", None)
    request.session["flash_msg"] = flash

    ## redirect back to whichever terminal started this enrollment
    return RedirectResponse(url=enroll_return(request), status_code = 303)

@app.get("/onsite_cin")
def onsite_cin_get(request: Request):
    ##  Check to see if user is admin (security measure to prevent malicious users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code = 303)

    ##  Block direct navigation, this page only makes sense mid-flow
    if not request.session.get("card_id") or not request.session.get("pending_first"):
        return RedirectResponse(url="/add_onsite", status_code = 303)

    ##  Unpack .session variables (if populated)
    major = request.session.pop("major", "")
    message = request.session.pop("flash_msg", "")
    status = request.session.pop("status", "")

    return templates.TemplateResponse(request=request,
                                      name="onsite_cin.html",
                                      context={'first': request.session.get("pending_first"),
                                               'major': major,
                                               'status': status, 'message': message})

@app.post("/onsite_cin")
def onsite_cin_post(request: Request, cin: str = Form(...), major: str = Form(...)):
    ##  Check to see if user is admin (security measure to prevent malicious users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code = 303)

    card_id = request.session.get("card_id")

    ##  Block direct navigation, this page only makes sense mid-flow
    if not card_id or not request.session.get("pending_first"):
        return RedirectResponse(url="/add_onsite", status_code = 303)

    ##  Security check to ensure CIN, which needs to be unique, hasn't already been used
    cin_exists = supabase.table('users').select('*').eq('cin', cin).execute()

    if cin_exists.data:
        ##  Their record exists but under a name/email that doesn't match what they typed,
        ##  so we can't safely attach the card. Hand it off to a person.
        request.session["flash_msg"] = "That CIN is already registered under a different name or email. Please see an officer."
        request.session["status"] = "error"

        ##  Prepare valid data to be retransmitted without user having to do it
        request.session['major'] = major

        return RedirectResponse(url="/onsite_cin", status_code=303)

    ##  Add form values to update dictionary
    new_user = {"card_id": card_id,
                "first_name": request.session.get("pending_first"),
                "last_name": request.session.get("pending_last"),
                "cin": cin, "major": major,
                "email": request.session.get("pending_email")}

    ##  Wrapped so a race on the unique constraints shows an error instead of a 500
    try:
        inserted = supabase.table('users').insert(new_user).execute()

    except Exception:
        request.session["flash_msg"] = "Could not add you to the database. Please see an officer."
        request.session["status"] = "error"
        request.session['major'] = major

        return RedirectResponse(url="/onsite_cin", status_code=303)

    ##  Enrolling doubles as a check-in for the running event
    recorded = log_attendance(request, inserted.data[0]['user_id'])

    flash = f"{new_user['first_name']} {new_user['last_name']} has been successfully added to the database"

    if recorded == "recorded":
        flash += "\nand checked in!"

    elif recorded == "error":
        flash += " (attendance could not be saved - see an officer)."

    else:
        ##  A brand new member cannot already be checked in, so anything other than a
        ##  successful write means there was no event running
        flash += " (no active event, attendance not recorded)."

    ##  Everything is written, clear the in-progress details for the next member
    request.session.pop("card_id", None)
    request.session.pop("pending_first", None)
    request.session.pop("pending_last", None)
    request.session.pop("pending_email", None)
    request.session["flash_msg"] = flash

    ## redirect back to whichever terminal started this enrollment
    return RedirectResponse(url=enroll_return(request), status_code = 303)

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
        return RedirectResponse(url="/admin", status_code=303)
    
    ##  Retrieve unique "tag"/identifier to keep track of which users were recently uploaded
    batch_tag = request.session.get('batch_tag')

    ##  Pull out 1 row of data (essentially 1 users' information)
    current_user = supabase.table('users').select('*').eq('upload_tag', batch_tag).is_('card_id', 'null').limit(1).execute()

    if not current_user.data:
        ##  If all users have been updated
        request.session.pop('batch_tag', None)
        return RedirectResponse(url="/add_users", status_code=303)


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
        return RedirectResponse(url="/admin", status_code=303)

    admin = supabase.table('admin').select('*').eq('nfc_id', scanned_id).execute()

    if scanned_id == ESCAPE_PASSWORD or admin.data:
        return RedirectResponse(url="/add_users", status_code=303)

    ##  Check to see if card has already been assigned
    check = supabase.table('users').select('*').eq('card_id', scanned_id).execute()

    if check.data:
        request.session["flash_msg"] = "Card already assigned. Try another card"
        request.session["status"] = "error"
        return RedirectResponse(url="/batch_scan", status_code=303)

    ##  Update database with card_id (scanned_id) using CIN as a reference
    supabase.table('users').update({'card_id': scanned_id}).eq('cin', cin).execute()

    request.session["flash_msg"] = "Card Assigned"
    request.session["status"] = "success"

    return RedirectResponse(url="/batch_scan", status_code=303)

@app.get("/lost_found")
def lost_found_get(request: Request):
    ##  Check to see if user is admin (security measure to prevent malicisous users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303)

    message = request.session.pop("flash_msg", "")
    status = request.session.pop("status", "")

    return templates.TemplateResponse(request=request,
                                      name="lost_found.html",
                                      context={"status": status, "message": message})

@app.post("/lost_found")
def lost_found_post(request: Request, scanned_id: str = Form(...)):
    ##  Check to see if user is admin (security measure to prevent malicisous users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303)

    admin = supabase.table('admin').select('*').eq('nfc_id', scanned_id).execute()

    ##  Escape check
    if scanned_id == ESCAPE_PASSWORD or admin.data:
        return RedirectResponse(url="/admin_tools", status_code=303)

    card = supabase.table('users').select('*').eq('card_id', scanned_id).execute()


    ##  If card isn't found in database (i.e. not assigned)
    if not card.data:
        request.session["flash_msg"] = "Card not found in database."
        request.session["status"] = "error"

        return RedirectResponse(url="/lost_found", status_code=303)

    request.session["flash_msg"] = f"Card belongs to {card.data[0]['first_name']} {card.data[0]['last_name']}"
    request.session["status"] = "success"

    return RedirectResponse(url="/lost_found", status_code=303)


@app.post("/shutdown_kiosk")
def shutdown(request: Request, admin_pass: str = Form(...)):
    ##  Check to see if user is admin (security measure to prevent malicisous users)
    if admin_pass == ADMIN_PASSWORD:

        ##  Clear session data (security measure)
        request.session.clear()

        return {"status": "Terminal Closed"}
    else:
        return RedirectResponse(url="/sign_out?error=invalid", status_code=303)

##  Function to execute shutdown mechanics
@app.post("/execute_shutdown")
def execute_shutdown():
    
    ##  Command to "kill" current chrome process
    os.system("taskkill /IM chrome.exe /F")

    ##  Get current process id
    current_pid = os.getpid()

    ##  Send kill signal for backend to stop
    os.kill(current_pid, signal.SIGTERM)

    return {"status": "Kiosk Closed"}

@app.get("/setup")
def get_setup(request: Request):
    ##  Security check to prevent malicious users from accessing setup page
    if not request.session.get("is_setup"):
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse(request=request,
                                      name="setup.html",
                                      context={})


@app.post("/setup")
def setup(request: Request, background_tasks: BackgroundTasks, name: str = Form(...), url: str = Form(...), key: str = Form(...),
          admin: str = Form(...), escape: str = Form(...)):
    ##  Check to see if user is admin (security measure to prevent malicisous users)
    if not request.session.get("is_setup"):
        return RedirectResponse(url="/admin", status_code=303)

    ##  Create hash to be written as SESSION_SECRET_KEY
    session_secret = secrets.token_hex(32)
    
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
    supabase = create_client(db_url, db_key)

    ##  Clear .session variables (security check)
    request.session.clear()

    background_tasks.add_task(phoenix)
    return RedirectResponse(url="/initialization", status_code=303)

def phoenix():
    ##  Function to restart the app after setup so that new .env variables can be used without user having to manually restart
    
    time.sleep(1) ##  Delay to ensure response is sent before restart occurs

    os.execv(sys.executable, [sys.executable] + sys.argv) ##  Restart the app using the same command that was used to start it originally

@app.get("/sign_out")
def sign_out(request: Request):
    error_flag = request.query_params.get("error")

    err_msg = ""
    if error_flag == "invalid":
        err_msg = "Incorrect Admin Password"
    return templates.TemplateResponse(request=request,
                                      name="sign_out.html",
                                      context={"message": err_msg})

@app.get("/initialization")
def initialization(request: Request):
    ##  Page to show while app is restarting after setup
    return templates.TemplateResponse(request=request,
                                      name="initialization.html",
                                      context={"message": "Saving Credentials...."})

@app.get("/admin_tools")
def admin_tools(request: Request):
    ##  Check to see if user is admin (security measure to prevent malicisous users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse(request=request,
                                      name="admin_tools.html",
                                      context={})

@app.get("/add_admin")
def get_add_admin(request: Request):
    ##  Check to see if user is admin (security measure to prevent malicisous users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303)

    message = request.session.pop("flash_msg", "")
    status = request.session.pop("status", "")
    first = request.session.pop("first", "")
    last = request.session.pop("last", "")
    role = request.session.pop("role", "")
    
    return templates.TemplateResponse(request=request,
                                      name="add_admin.html",
                                      context={"message": message,
                                               "status": status,
                                               "first": first,
                                               "last": last,
                                               "role": role})

@app.post("/add_admin")
def post_add_admin(request: Request, first: str = Form(...), last: str = Form(...), role: str = Form(...), scanned_id: str = Form()):
    ##  Check to see if user is admin (security measure to prevent malicisous users)
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303)
    
    ##  Error checks
    if not first or not last or not role or not scanned_id:
        request.session["flash_msg"] = "Please fill out all fields."
        request.session["status"] = "error"

        ##  Store form data so user doesn't have to retype everything after error
        request.session["first"] = first
        request.session['last'] = last
        request.session['role'] = role
        request.session['scanned_id'] = scanned_id

        return RedirectResponse(url="/add_admin", status_code=303)

    check = supabase.table('admin').select('*').eq('nfc_id', scanned_id).execute()

    if check.data:
        request.session["flash_msg"] = "NFC already assigned to another admin."
        request.session["status"] = "error"

        ##  Store form data so user doesn't have to retype everything after error (except the scanned id which is the issue)
        request.session["first"] = first
        request.session['last'] = last
        request.session['role'] = role

        return RedirectResponse(url="/add_admin", status_code=303)

    ##  Add new admin to database (after passing error checks)
    ##  First create a dictionary to hold new admin information, then insert into database
    ##  ****Insert can only take 1 parameter, thus we have to create a dictionary
    new_admin = {'first': first, 'last': last, 'role': role, 'nfc_id': scanned_id}

    supabase.table('admin').insert(new_admin).execute()
    
    request.session["flash_msg"] = f"{first} {last} has been successfully added as an admin."
    request.session["status"] = "success"
    
    return RedirectResponse(url="/add_admin", status_code=303)

@app.get("/analytics")
def get_analytics(request:Request):
    ## Security check to prevent malicious users from accessing analytics page
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303)

    ##  Logic for real time attendance tracking

    ##  Grab data into a list of dictionaries
    current_data = []

    if not request.session.get("event_name"):
        # returns empty list in event variable to prevent errors in template
        return templates.TemplateResponse(request=request,
                                          name="analytics.html",
                                          context={'current_data': current_data})

    ##  Store current events name in a variable for comparison
    current_event = request.session.get("event_name")

    ## Grab attendance data using a 'join'
    current_data, error = fetch_attendance(current_event)

    return templates.TemplateResponse(request=request,
                                      name="analytics.html",
                                      context={'current_data': current_data,
                                               'ev_name': current_event,
                                               'error': error,
                                               'attendance_count': len(current_data)})

##  API route to grab current event attendance data for analytics page
@app.get("/api/live-attendance")
def get_live_attendance(request: Request):
    ## Security check to prevent malicious users from accessing analytics page
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303)

    ##  Logic for real time attendance tracking

    ##  Grab data into a list of dictionaries
    current_data = []

    if not request.session.get("event_name"):
        # returns empty list in event variable to prevent errors in template
        return current_data

    ##  Store current events name in a variable for comparison
    current_event = request.session.get("event_name")

    ## Grab attendance data using a 'join'
    ##  On failure this returns an empty list, so the polling JavaScript simply
    ##  leaves the last known feed on screen instead of erroring out
    current_data, error = fetch_attendance(current_event)

    return current_data

@app.get("/history")
def get_history(request: Request):
    ## Security check to prevent malicious users from accessing analytics page
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303)

    current_event = request.session.get("event_name")

    ##  Grab previous event names for dropdown menu
    events, error = past_event_names(current_event)

    return templates.TemplateResponse(request=request,
                                      name="history.html",
                                      context={'events': events,
                                               'error': error})

@app.post("/history")
def post_history(request:Request, event: str = Form(...)):
    ## Security check to prevent malicious users from accessing analytics page
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=303)

    ##  Pull the attendance for the chosen event
    event_data, error = fetch_attendance(event)

    current_event = request.session.get("event_name")

    ##  Grab previous event names for dropdown menu
    events, list_error = past_event_names(current_event)

    return templates.TemplateResponse(request=request,
                                      name="history.html",
                                      context={'events': events,
                                               'selected_event': event_data,
                                               'event_name': event,
                                               'error': error or list_error,
                                               'attendance_count': len(event_data)})

