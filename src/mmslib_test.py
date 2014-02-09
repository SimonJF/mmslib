#!/usr/bin/env python
from mmslib import MMSLib, MMSToolType
import sys

def main():
    if len(sys.argv) < 3:
        print "Usage: mmslib_test.py <user> <password>"
        sys.exit(-1)

    print_modules(sys.argv[1], sys.argv[2])

def print_modules(user, passwd):
    mms = MMSLib(user, passwd)
    modules = mms.get_modules()
    for module in modules:
        print "Module name: %s, code: %s, semester: %s" % (module.module_name, \
                module.module_code, module.semester)

        cwk_tools = module.get_tools(MMSToolType.Coursework)
        for cwk_tool in cwk_tools:
            assignments = cwk_tool.get_assignments()
            for assignment in assignments:
                print assignment 

        print "Tools:"
        for tool in module.tools:
            print "Tool name: %s, Tool Type: %s, Tool URL: %s" % (tool.name, \
                    MMSToolType.show_string(tool.tool_type), tool.url)

if __name__ == "__main__":
    main()
