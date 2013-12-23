# API-like access to St Andrews MMS.
# Useful for things like grade scrapers and so on.
# I realised my old was dated, unpythonic, and according to Lenary "horrible",
# so it was probably best to start again.
# Also, interesting to get my head out of functional-land every once in a while :)
from bs4 import BeautifulSoup
import re
import requests

# Exceptions:
# ImproperUseError is thrown when the library isn't used properly.
class ImproperUseError(Exception):
    def __init__(self, msg):
        self.msg = msg
    def __repr__(self):
        return self.msg

# AuthenticationError is thrown when there is a problem with the given
# credentials.
class AuthenticationError(Exception):
    def __init__(self):
        Exception.__init__(self)
    def __repr__(self):
        return "The given username or password was incorrect."

# MMS Tools (at least the student ones. I'm not staff. If you're reading this,
# Tristan, patches welcome ;))
# TODO: Python 2 doesn't have enums... There must be a nicer way of doing this
class MMSToolType(object):
    Attendance, Content, Coursework, Enrollment, Moodle, \
      Signup, URL, Invalid = range(8)

    @staticmethod
    def from_string(tool_str):
        if tool_str == "coursework":
            return MMSToolType.Coursework
        elif tool_str == "tas":
            return MMSToolType.Attendance
        elif tool_str == "Enrollment":
            return MMSToolType.Enrollment
        elif tool_str == "URL":
            return MMSToolType.URL
        elif tool_str == "content":
            return MMSToolType.Content
        elif tool_str == "signup":
            return MMSToolType.Signup
        elif tool_str == "moodlelink":
            return MMSToolType.Moodle
        else: 
            return MMSToolType.Invalid

    @staticmethod
    def show_string(tool_type):
        if tool_type == MMSToolType.Attendance:
            return "Attendance"
        elif tool_type == MMSToolType.Content:
            return "Content"
        elif tool_type == MMSToolType.Coursework:
            return "Coursework"
        elif tool_type == MMSToolType.Enrollment:
            return "Enrollment"
        elif tool_type == MMSToolType.Moodle:
            return "Moodle Link"
        elif tool_type == MMSToolType.Signup:
            return "Signup"
        elif tool_type == MMSToolType.URL:
            return "URL"
        else: 
            return "Invalid Tool"



class MMSTool(object):
    def __init__(self, name, tool_type, url):
        self.name = name
        self.tool_type = tool_type
        self.url = url

# Representation of an MMS Module
class MMSModule(object):
    def __init__(self, module_code, module_name, semester, tools):
        self.module_code = module_code
        self.module_name = module_name
        self.semester = semester
        self.tools = tools

# Accesses are stateful, so we need a class to encapsulate this
class MMSLib(object):
    # All URLs in MMS are relative, which isn't much use to us!
    BASE_URL = "https://mms.st-andrews.ac.uk"
    LOGIN_URL = "https://login.st-andrews.ac.uk"
    INCORRECT_TEXT = "cannot be determined to be authentic"
    NOT_LOGGED_IN_TEXT = "Log in here with your"

    def __init__(self, user, passwd):
        # When creating object, try to login, and populate
        # cookies.
        self.user = user
        self.passwd = passwd
        self.sess = requests.Session()
        user_home = MMSLib.BASE_URL + "/mms/user/me/Modules"
        self._mms_get(user_home)

    # Attempts to log in. Throws an AuthenticationError if incorrect,
    # otherwise returns page shown upon successful login
    def _login(self, login_page):
        print "logging in"
        # Get the required hidden metadata for the SSO system
        parsed_login = _parse_login(login_page)
        args = { "username" : self.user, "password": self.passwd, 
                 "lt" : parsed_login["lt"], "_eventId" : parsed_login["eventid"] }

        # Make the login request
        req_url = MMSLib.LOGIN_URL + "/" + parsed_login["dest"]
        resp = self.sess.post(req_url, data=args)
        
        # If login failure, then throw an error
        if MMSLib.INCORRECT_TEXT in resp.text:
            raise AuthenticationError()
        
        return resp.text

    # Stateful get access, handles login if necessary
    def _mms_get(self, req_url):
        #print "URL", req_url
        resp = self.sess.get(req_url)
        if MMSLib.NOT_LOGGED_IN_TEXT in resp.text:
            return self._login(resp.text)
        return resp.text
        

    # Gets a list of MMSModules.
    # If academic_year is None, the current year is fetched.
    def get_modules(self, academic_year=None):
        # https://mms.st-andrews.ac.uk/mms/user/me/Modules?academic_year=2011%2F2
        req_url = MMSLib.BASE_URL + "/mms/user/me/Modules" 
        if academic_year:
            req_url = req_url + "?academic_year=" + academic_year
        res = self._mms_get(req_url)
        modules = _parse_modules_list(res)
        return modules
        
    def get_module(self, academic_year, module_code):
        pass


#<h3 class="module_heading">
#  <a href="/mms/module/2013_4/Y1/CS4099/">CS4099 (Y1): Major Software Project</a>
#</h3>
#<div id="module_2013%2F4_Y1_CS4099">
#  <p>
#    <a href="/mms/module/2013_4/Y1/CS4099/">CS4099 (Y1): Major Software Project</a>
#  </p>
#  <ul class="module_resources">
#    <li class="coursework">
#      <a class="coursework" href="/mms/module/2013_4/Y1/CS4099/CS4099+Coursework/">CS4099 Coursework</a>
#    </li>
#    <li class="tas">
#      <a class="tas" href="/mms/module/2013_4/Y1/CS4099/Supervisor+Meeting/">Supervisor Meeting</a>
#    </li>
#  </ul>
#</div>

def _parse_modules_list(html):
    ret = []
    parser = BeautifulSoup(html)
    
    modules_entries = parser.findAll("h3", { "class" : "module_heading" })
    for entry in modules_entries: # enumerates all modules
        # Get link, which gives us easy access to reasonably juicy info
        link = entry.a["href"]
        # /mms/module/2013_4/Y1/CS4099/
        regex = "/mms/module/(.+)/(.+)/(.+)/"
        match = re.search(regex, link)
        if match:
            # If we've got a module match, process the subgroups to get metadata
            academic_year = match.group(1)
            semester = match.group(2)
            code = match.group(3)
            name = entry.a.contents[0]

            # Then parse the tools
            tools = _parse_module_tools(entry)

            mms_module = MMSModule(code, name, semester, tools)
            ret.append(mms_module)
    return ret

def _parse_module_tools(dom_entry):
    tools = []
    section = dom_entry.next_sibling.next_sibling # 2x nextSibling. why? beats me.
    tool_section = section.find("ul", { "class", "module_resources"})
    if tool_section:
        tool_links = tool_section.find_all("a")
        for tool_link in tool_links:
            #print "tl", tool_link
            tool_class = tool_link["class"][1]
            # Get the data we need, create an MMSTool instance
            tool_type = MMSToolType.from_string(tool_class)
            link = MMSLib.BASE_URL + tool_link["href"]
            tool_name = tool_link.contents[0]
            tool = MMSTool(tool_name, tool_type, link)
            tools.append(tool)

    return tools

def _parse_login(html):
    """Parses the login page. Returns a dictionary of the form { id : form id, 
    dest : destination url, lt : lt hidden value, eventid : eventId hidden value}."""
    parser = BeautifulSoup(html)
     
    # Extracts required information from the page
    form = parser.find("form")
    id = form["id"]
    action_url = form["action"]
    lt_hidden = form.find("input", { "type" : "hidden", "name" : "lt" })["value"]
    eid_hidden = form.find("input", { "type" : "hidden", "name" : "_eventId" })["value"]
    return { "id" : id, "dest" : action_url, "lt" : lt_hidden, "eventid" : eid_hidden }
