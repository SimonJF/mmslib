# API-like access to St Andrews MMS.
# Useful for things like grade scrapers and so on.
# I realised my old code was dated, unpythonic, and according to Lenary "horrible",
# so it was probably best to start again.
# Also, interesting to get my head out of functional-land every once in a while :)
from bs4 import BeautifulSoup
import re
import requests
import time

# Exceptions:
# ImproperUseError is thrown when the library isn't used properly.
class ImproperUseError(Exception):
    def __init__(self, msg):
        Exception.__init__(self)
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

class ToolNotAvailableError(Exception):
    def __init__(self, msg):
        Exception.__init__(self)
        self.msg = msg
    def __repr__(self):
        return self.msg

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
    def __init__(self, name, tool_type, url, lib):
        self.name = name
        self.tool_type = tool_type
        self.url = url
        self.lib = lib

class MMSCourseworkTool(MMSTool):
    def __init__(self, name, url, lib):
        MMSTool.__init__(self, name, MMSToolType.Coursework, url, lib)

    def get_assignments(self):
        cwk_page = self.lib._mms_get(self.url)
        assignments = _parse_cwk(cwk_page, self.lib)
        return assignments

# Representation of an MMS Module
class MMSModule(object):
    def __init__(self, module_code, module_name, semester, tools):
        self.module_code = module_code
        self.module_name = module_name
        self.semester = semester
        self.tools = tools

    def get_tools(self, tool_ty=None):
        if tool_ty == None:
            return self.tools
        return filter(lambda tool: tool.tool_type == tool_ty, self.tools)

class MMSAssignment(object):
    def __init__(self, name, due_date, feedback_date, submitted_date, 
            uploaded_file, comments, grade, weighting, chart_link):
        self.name = name
        self.due_date = due_date
        self.feedback_date = feedback_date
        self.submitted_date = submitted_date
        self.uploaded_file = uploaded_file
        self.comments = comments
        self.grade = grade
        self.weighting = weighting

    def __repr__(self):
        ret = ["------ Assignment %s -------" % self.name,
        "Due date: %s" % time.strftime("%d %b %y, %H:%M", self.due_date),
        "Feedback date: %s" % time.strftime("%d %b %y", self.feedback_date)]

        if self.submitted_date != None:
            ret.append( "Submitted date: %s" % \
                    time.strftime("%d %b %y, %H:%M", self.submitted_date))
            ret.append("Uploaded file URL: %s" % self.uploaded_file)
        else:
            ret.append("Not submitted")
        ret.append("Comments: ")
        for comment in self.comments:
            ret.append("  %s" % comment)
        if self.grade != None:
            ret.append("Grade: %f" % self.grade)
        else:
            ret.append("No grade recorded")
        if self.weighting != None:
            ret.append("Weighting: %f" % self.weighting)
        else:
            ret.append("Not weighted")

        return "\n".encode("utf_8", "ignore").join(ret)
        

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
        modules = _parse_modules_list(res, self)
        return modules
        
    def get_module(self, academic_year, module_code):
        # TODO. Will require going to module page, and translating
        # from textual reps of tools to actual tools, parsing a different table 
        pass

    

def _parse_modules_list(html, lib):
    """ Given a module overview page, parses the page into a list of MMSModules """
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
            tools = _parse_module_tools(entry, lib)

            mms_module = MMSModule(code, name, semester, tools)
            ret.append(mms_module)
    return ret

def _parse_module_tools(dom_entry, lib):
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
            # TODO: Once we add support for more tools, it's likely that it'd be
            # best to have subclasses for each tool, like this. For now, this will do...
            if tool_type == MMSToolType.Coursework:
                tool = MMSCourseworkTool(tool_name, link, lib)
            else:
                tool = MMSTool(tool_name, tool_type, link, lib)
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
    eid_hidden = \
      form.find("input", { "type" : "hidden", "name" : "_eventId" })["value"]
    return { "id" : id, "dest" : action_url, "lt" : lt_hidden, \
             "eventid" : eid_hidden }

def is_float(test_str):
    try:
        float(test_str)
        return True
    except ValueError:
        return False

def _parse_cwk(html, lib):
    html = html.replace("&#160;", "")
    ret = []
    parser = BeautifulSoup(html)
    
    table = parser.find("tbody")
    entries = table.findAll("tr") # finds a list of all coursework elements
#0   			<td >cw1</td>
#1	due		<td >14 Mar 14, 23:59</td>
#2  fdb		<td >28 Mar 14</td>
#3	file	<td ><input type="file" name="file_156081" id="file_156081" />
#
#4	sub		<td >&#160;</td>
#5	fdb		<td >
#6	grd		<td >&#160;</td>
#7	wgt		<td >50 %</td>
#8	cht		<td ><a href="Graph?assignment=156081">Chart</a></td>
#	chk		<td ><input type="checkbox" name="assignment" value="156081" /> 
    for entry in entries:
        children = entry.findAll("td") # enumerates all attributes
        name = children[0].contents[0]
        # 30 Sep 10, 23:59
        due_date_str = children[1].contents[0]
        due_date = time.strptime(due_date_str, "%d %b %y, %H:%M")
 
        # 07 Oct 10
        # Parse feedback date
        feedback_date_str = children[2].contents[0]
        feedback_date = time.strptime(feedback_date_str, "%d %b %y")
        file_url = None  # children[3].contents[0]
        # 30 Sep 10, 23:59
        # Parse submission date. Not always present...
        if len(children[4].contents) > 0:
            submitted_date_str = children[4].contents[0]
            try:
                submitted_date = time.strptime(submitted_date_str, "%d %b %y, %H:%M")
            except ValueError: # Generally happens if not submitted
                submitted_date = None
        else:
            submitted_date = None

        feedback = _parse_cwk_feedback_field(children[5])
        
        # Parse grade
        grade = None
        if len(children[6].contents) > 0:
            grade_str = children[6].contents[0]
            if is_float(grade_str):
                grade = float(grade_str)
        
        # Parse weighting
        weighting_str = children[7].contents[0]
        weighting = None
        try:
            weighting_regex = "(\d*) %"
            match = re.search(weighting_regex, weighting_str)
            if match:
                weighting = float(match.group(1))
        except ValueError:
            weighting = None

        chart_link = children[8].a["href"]
        assignment = MMSAssignment(name, due_date, feedback_date, \
                        submitted_date, file_url, feedback, grade, weighting, chart_link)
        ret.append(assignment)
    return ret

# TODO: Really, should evaluate this eagerly and fetch feedback
def _parse_cwk_feedback_field(dom_element):
    feedback_entries = []
    ul_element = dom_element.find("ul", {"class" : "horizontal"})
    for feedback_element in ul_element.find_all("li"):
#        print "feedback elem", feedback_element.contents[0]
        feedback_entries.append(feedback_element.contents[0])
    return feedback_entries

