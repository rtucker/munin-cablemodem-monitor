#!/usr/bin/python

# Checks status of cable modem at 192.168.100.1
# Assumes the Ambit modem that is in my wiring closet right now.
# Ryan Tucker <rtucker@gmail.com>, Jun 10 2009

# To use with munin, symlink in /etc/munin/plugins like:
# cablemodem_Downstream.Frequency

import os
import string
import sys
import urllib

def parsePageContents(html):
        # iterate through the returned crap
        returndict = {}
        for i in html:
                if i[0:3] == '<tr':
                        # this is horrible code
                        try:
                                tmp1 = string.split(i, '<font size=2>')[1]
                                fieldname = string.split(tmp1, ':')[0].strip()
                                tmp2 = string.split(tmp1, ':')[1]
                                value = string.split(string.split(tmp2, '<td>')[1], '</td>')[0]
                                returndict[fieldname] = value
                        except IndexError:
                                pass
        return returndict

def getPageContents(pagename, ip='192.168.100.1', username='user', password='user'):
	# make a URL
	url = 'http://%s:%s@%s/%s.asp' % (username, password, ip, pagename)
	# retrieve it
	fetched = urllib.urlretrieve(url)
	# load the html stuff in
	htmldata = open(fetched[0], 'r').readlines()
	# return!
	return htmldata

def buildModemDetails():
        returndict = {}
        returndict['Downstream'] = (parsePageContents(getPageContents('CmDnstream')))
        returndict['Upstream'] = (parsePageContents(getPageContents('CmUpstream')))
        return returndict

def getMuninData(type):
        if string.split(type,' ')[0] == 'Downstream':
                return parsePageContents(getPageContents('CmDnstream'))[type]
        else:
                return parsePageContents(getPageContents('CmUpstream'))[type]

def printMuninConfig(type):
        # prints config for a given type
	value = getMuninData(type)
	units = value.split(' ')[1]

	return 'graph_title %s\ngraph_vlabel %s\ngraph_category DOCSIS\ngraph_info %s (%s)\ndata.label %s\ndata.info %s\n' % (type, units, type, units, type, type)

def printMuninOutput(type):
	# prints output for a given type
	value = getMuninData(type)

	return 'data.value %s\n' % value.split(' ')[0]

if __name__ == '__main__':
        if os.path.dirname(sys.argv[0]) == '/etc/munin/plugins':
                # we're running as a munin plugin!
                executetype = os.path.basename(sys.argv[0]).split('_')[1].replace('.', ' ')
                if len(sys.argv) > 1 and sys.argv[1] == 'config':
                        sys.stdout.write(printMuninConfig(executetype))
                else:
                        sys.stdout.write(printMuninOutput(executetype))
        else:
                print `buildModemDetails()`
		print `printMuninConfig('Downstream Receive Power Level')`
		print `printMuninOutput('Downstream Receive Power Level')`

