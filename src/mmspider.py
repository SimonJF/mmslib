#!/usr/bin/env python
import ConfigParser
from mmslib import *
import hashlib
import shelve
import smtplib
import os
import os.path

CONF_FILE = "mmspider.conf"
STORE_NAME = "mmspider.dat"
SUBJECT_LINE = "MMSpider Alert: Coursework has changed"
MSG_TEXT = "MMSpider has detected a change for some elements of coursework. " + \
        "These are detailed below."

class PersistentCoursework(object):
    def __init__(self, id, name, due_date, feedback_date, feedback, grade):
        self.id = id
        self.name = name
        self.due_date = due_date
        self.feedback_date = feedback_date
        self.feedback = feedback
        self.grade = grade

    @staticmethod
    def create_from_assignment(mms_assignment):
        feedback = map(lambda x: str(x), mms_assignment.get_feedback())
        ret = PersistentCoursework(mms_assignment.id, mms_assignment.name, \
                mms_assignment.due_date, mms_assignment.feedback_date, \
                feedback, mms_assignment.grade)
        return ret

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.__dict__ == other.__dict__
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

def parse_config():
    config = ConfigParser.RawConfigParser()
    config.read(CONF_FILE)
    user = config.get("mmspider", "user")
    password = config.get("mmspider", "password")
    email = config.get("mmspider", "email")
    return (user, password, email)

# SHA256 hash of cwk tool URL
def get_persistent_key(cwk_tool):
    m = hashlib.sha256()
    m.update(cwk_tool.url)
    return m.hexdigest()

# Populates the store for a given tool
def populate_store(persistent_assignments, store, key):
    assignment_dict = {}
    for persistent_assignment in persistent_assignments:
        # Create a persistent assignment instance, and store it
        assignment_dict[str(persistent_assignment.id)] = persistent_assignment
    store[key] = assignment_dict


def check_cwk(lib, cwk_tool, store):
    # Firstly, check whether we have a copy of the coursework stored persistently
    # for this tool. Since we can have multiple cwk tools per module, it's best
    # to actually just index it by a hash of the tool URL.
    key = get_persistent_key(cwk_tool)
    assignments = cwk_tool.get_assignments()
    persistent_assignments = \
        [PersistentCoursework.create_from_assignment(x) for x in assignments]

    # If it's not in there, populate it, and don't notify the user.
    if key not in store:
        populate_store(persistent_assignments, store, key)
        return [] # Don't return anything, so the user's not notified on first run

    # If it is, we can get a list of diffs, and email them.
    diffs = []
    assignment_dict = store[key]
    for assignment in assignments:
        persistent_assignment = \
                PersistentCoursework.create_from_assignment(assignment)
        assignment_key = str(assignment.id)
        if assignment_key in assignment_dict:
            # Check whether they're the same, if not, add to diffs.
            if persistent_assignment != assignment_dict[assignment_key]:
                assignment_dict[assignment_key] = persistent_assignment
                diffs.append(assignment)
        else: # If the cwk isn't in there, add it. Also add to diffs.
            assignment_dict[assignment_key] = persistent_assignment
            diffs.append(assignment)
    # Finally, persist the updated assignment store and return diffs
    store[key] = assignment_dict
    return diffs

# Given an assignment, generates the string representation
# to put in the email
def generate_cwk_str(diff):
    ret = str(diff) + "\r\n"
    feedback = diff.get_feedback()
    for feedback_entry in feedback:
        ret = ret + str(feedback_entry) + "\r\n"
    return ret

def generate_msg_body(diffs):
    ret = MSG_TEXT + "\r\n"
    for module_code, module_diffs in diffs.iteritems():
        ret = ret + "Module " + module_code + ":\r\n"
        for cwk_toolname, cwk_diffs in module_diffs.iteritems():
            ret = ret + "Coursework tool name: " + cwk_toolname + "\r\n"
            for cwk_diff in cwk_diffs:
                ret = ret + generate_cwk_str(cwk_diff) + "\r\n"
    return ret

def email_diffs(diffs, email_address):
    msg_body = generate_msg_body(diffs)
    msg = ("From: %s\r\nTo: %s\r\nSubject: %s\r\n\r\n" % (email_address, \
            email_address, SUBJECT_LINE)) + msg_body
    s = smtplib.SMTP('localhost')
    s.sendmail(email_address, [email_address], msg)
    s.quit()

def main():
    # Firstly, parse the config file
    if not os.path.exists(CONF_FILE):
        print "Error: mmspider.conf does not exist!"
        sys.exit(-1)
    (user, passwd, email) = parse_config()

    # Secondly, create a library instance, and get all the coursework tools
    try:
        lib = MMSLib(user, passwd)
    except AuthenticationError:
        print "Error: Incorrect username or password."
        sys.exit(-1)

    store = shelve.open(STORE_NAME)
    modules = lib.get_modules(academic_year="2011_2")
    diffs = {}
    for module in modules:
        cwk_tools = module.get_tools(MMSToolType.Coursework)
        module_diffs = {}
        for cwk_tool in cwk_tools:
            cwk_diffs = check_cwk(lib, cwk_tool, store)
            if (len(cwk_diffs) > 0):
                module_diffs[cwk_tool.name] = cwk_diffs

        if (len(module_diffs) > 0):
            diffs[module.module_code] = module_diffs

    store.close()
    # Email the diffs if we need to, and we're done!
    if len(diffs) > 0:
        email_diffs(diffs, email)
        print "Email sent!"
    else:
        print "No changes!"

# Checks to see whether any coursework has been updated.

if __name__ == "__main__":
    main()
