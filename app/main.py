from re import M
from urllib import request
from fastapi import FastAPI
from fastapi.templating import Jinja2Templates ## For reading HTML templates

## Create FastAPI app
app = FastAPI()

## Point Jinja to correct directory holding templates
templates = Jinja2Templates(directory="templates")


##  Decorator for the root endpoint and then define 
##  the function that will be called when the root endpoint is accessed
@app.get("/")
def read_root():
    """
        Root endpoint function
        name => Name of the HTML template to render
        context => Context to pass to the template, including a welcome message
    """
    name = "index.html"
    context ={"request": request, "message": "Welcome to the Kiosk"}
    return templates.TemplateResponse(name, context) ## Render the template with the provided context