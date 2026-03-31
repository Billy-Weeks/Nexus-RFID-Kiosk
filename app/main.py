import os ## For accessing environment variables/reading computer files
from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates ## For reading HTML templates
from fastapi.staticfiles import StaticFiles ## For taking care of static files like CSS
from supabase import create_client, Client ## For connecting to Supabase
from dotenv import load_dotenv ## For loading environment variables from .env file


## Connecting to Supabase
load_dotenv() ## Load environment variables from .env file

url: str = os.environ.get("SUPABASE_URL") ## Get Supabase URL from environment variable
key: str = os.environ.get("SUPABASE_KEY") ## Get Supabase Key from environment variable"

supabase = create_client(url, key) ## Create Supabase client using the URL and Key

## Create FastAPI app
app = FastAPI()

## Point Jinja to correct directory holding templates
templates = Jinja2Templates(directory="templates")

## Mount the static files directory to serve CSS and other static assets
app.mount("/static", StaticFiles(directory="static"), name="static")


##  Decorator for the root endpoint and then define 
##  the function that will be called when the root endpoint is accessed
@app.get("/")
def read_root(request: Request):
    """
        Root endpoint function
        name => Name of the HTML template to render
        context => Context to pass to the template, including a welcome message
    """
    return templates.TemplateResponse(request=request,
                                      name="index.html",
                                      context={"status": "default","message": "Welcome to the Kiosk"}) 

@app.post("/scan")
def scan(request: Request, scanned_id: str = Form(...)):

    ##  Checking to make sure the scanned ID is in the database already
    check = supabase.table('users').select('*').eq('card_id', scanned_id).execute()

    if check.data:

        ##  Package data and update database: user_id
        update = {"event_name": "Test event", "user_id": check.data[0]['user_id']}
        supabase.table('attendance_log').insert(update).execute()

        return templates.TemplateResponse(request=request,
                                          name="index.html",
                                          context={"status": "success", "message": f"Welcome, {check.data[0]['first_name']} {check.data[0]['last_name']}!"})
    else:
        return templates.TemplateResponse(request=request, name="index.html", context={"status": "error", "message": "User not in database"})

##  Admin page information
@app.get("/admin")
def admin_logIn(request: Request):
    return templates.TemplateResponse(request=request,
                                      name="admin.html",
                                      contex={})