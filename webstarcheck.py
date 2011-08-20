#!/usr/bin/python

# Checks status of cable modem at 192.168.100.1
# Assumes the WebSTAR modem that is in my wiring closet right now.
# Ryan Tucker <rtucker@gmail.com>, 2011 August 19

# To use with munin, symlink in /etc/munin/plugins like:
# cablemodem_Downstream.Frequency

from BeautifulSoup import BeautifulSoup
from contextlib import contextmanager
import os
import string
import sys
import urllib
import urllib2

TIMEOUT=10

class WebSTAR(object):
    def __init__(self, ip='192.168.100.1', password='W2402'):
        self.ip = ip
        self.password = password
        self._escalated = False
        self._details = {}
        self._contents_cache = {}

    @staticmethod
    def clean(string):
        return ' '.join(string.strip(u'\xa0').replace('\n', '').split()).strip()

    def parsePageContents(self, content):
        # Given a list of strings, returns a dict of key-value pairs scraped
        # from it.
        soup = BeautifulSoup(''.join(content), convertEntities='html')
        datadict = {}
        counter0 = 0
        for table in soup('table'):
            tabledict = {}
            counter1 = 0
            for row in table('tr'):
                if len(row('td')) == 1:
                    continue
                elif len(row('td')) > 2:
                    tabledict['TYPE'] = 'ordered'
                    leftside = counter1
                    counter1 += 1
                    rightside = [self.clean(d.findAll(text=True)[-1:][0]) for d in row('td')]
                else:
                    tabledict['TYPE'] = 'keyvalue'
                    leftside = self.clean(row('td')[0].findAll(text=True)[-1:][0])
                    rightside = self.clean(row('td')[1].findAll(text=True)[-1:][0])

                tabledict[leftside] = rightside
            datadict[counter0] = tabledict
            counter0 += 1

        # Reorganize it a bit
        returndict = {}
        for counter, data in datadict.items():
            if data['TYPE'] == 'keyvalue':
                for key, value in data.items():
                    if key == 'TYPE': continue
                    returndict['%s_%i' % (key, counter)] = value
            elif data['TYPE'] == 'ordered':
                tmp = data.copy()
                tmp.pop('TYPE')
                returndict[data[0][0] + '_list'] = tmp

        return returndict

    @contextmanager
    def escalatedPrivileges(self):
        # Logs into the modem, so that the "hidden pages" can be accessed
        if self._escalated:
            yield True
        else:
            payload = {
                'SAAccessLevel': 2,
                'SAPassword': self.password,
                'submit': 'Submit',
            }
            data = urllib.urlencode(payload)
            result = urllib2.urlopen('http://%s/goform/_aslvl' % (self.ip), data, TIMEOUT)

            self._escalated = False
            for line in result.readlines():
                if line.find('Success'):
                    self._escalated = True

            yield self._escalated

    def getPageContents(self, pagename):
        # Returns a list of strings for a given page.
        if pagename in self._contents_cache:
            return self._contents_cache[pagename]

        with self.escalatedPrivileges():
            result = urllib2.urlopen('http://%s/%s' % (self.ip, pagename), None, TIMEOUT)
            self._contents_cache[pagename] = result.readlines()
            return self._contents_cache[pagename]

    def get_details(self, key):
        if key not in ['signal', 'status', 'log']:
            return {}
        if key not in self._details:
            self._details[key] = self.parsePageContents(self.getPageContents('%s.asp' % key))
        return self._details[key]

    @property
    def signal(self):
        return self.get_details('signal')

    @property
    def status(self):
        return self.get_details('status')

    @property
    def log(self):
        return self.get_details('log')

    @property
    def downstream(self):
        result = {}
        suffix = ''

        for candidate in self.signal.keys():
            if candidate.startswith('Downstream'):
                suffix = candidate[-2:]

        result['bitrate'] = self.signal['Bit Rate' + suffix]
        result['channel'] = self.signal['Channel ID' + suffix]
        result['frequency'] = self.signal['Downstream Frequency' + suffix]
        result['modulation'] = self.signal['Modulation' + suffix]
        result['power'] = self.signal['Power Level' + suffix]
        result['snr'] = self.signal['Signal to Noise Ratio' + suffix]
        result['status'] = self.signal['Downstream Status' + suffix]

        result['bitrate_int'] = int(result['bitrate'].split()[0])
        result['channel_int'] = int(result['channel'].split()[0])
        result['frequency_int'] = int(result['frequency'].split()[0])
        result['power_float'] = float(result['power'].split()[0])
        result['snr_float'] = float(result['snr'].split()[0])

        return result

    @property
    def upstream(self):
        result = {}
        suffix = ''

        for candidate in self.signal.keys():
            if candidate.startswith('Upstream'):
                suffix = candidate[-2:]

        result['bitrate'] = self.signal['Bit Rate' + suffix]
        result['channel'] = self.signal['Channel ID' + suffix]
        result['frequency'] = self.signal['Upstream Frequency' + suffix]
        result['modulation'] = self.signal['Modulation' + suffix]
        result['power'] = self.signal['Power Level' + suffix]
        result['status'] = self.signal['Upstream Status' + suffix]

        result['bitrate_int'] = int(result['bitrate'].split()[0])
        result['channel_int'] = int(result['channel'].split()[0])
        result['frequency_int'] = int(result['frequency'].split()[0])
        result['power_float'] = float(result['power'].split()[0])

        return result

    @property
    def modem(self):
        result = {}

        result['cable_ip'] = self.status['IP Address_0']
        result['certificate'] = self.status['Cable Modem Certificate_0']
        result['current_time'] = self.status['Current Time_0']
        result['status'] = self.status['Cable Modem Status_0']
        result['uptime'] = self.status['Time Since Last Reset_0']

        secs = 0
        for chunk in result['uptime'].split(':'):
            if chunk.endswith('s'):
                secs += int(chunk.strip('s'))
            elif chunk.endswith('m'):
                secs += int(chunk.strip('m'))*60
            elif chunk.endswith('h'):
                days, word, hours = chunk.split()
                secs += int(hours.strip('h'))*60*60
                secs += int(days)*24*60*60

        result['uptime_seconds'] = secs

        return result

    @property
    def clients(self):
        table = self.status['Connected to_list']
        table.pop(0)

        for key, row in table.items():
            yield {
                'interface': row[0],
                'mac': row[1],
                'ip': row[2],
            }

    @property
    def messages(self):
        table = self.log['Time_list']
        table.pop(0)

        for key, row in table.items():
            yield {
                'time': row[0],
                'level': row[1],
                'message': row[2],
            }

    def printPrettyStatus(self):
        print "Modem Status"
        for key, value in self.modem.items():
            print "    %s: %s" % (key, value)

        print ""
        print "Downstream Signal"
        for key, value in self.downstream.items():
            print "    %s: %s" % (key, value)

        print ""
        print "Upstream Signal"
        for key, value in self.upstream.items():
            print "    %s: %s" % (key, value)

        print ""
        print "Connected Clients"
        for row in self.clients:
            print "    %(ip)s (MAC %(mac)s, via %(interface)s)" % row

        print ""
        print "Log Messages"
        for row in self.messages:
            print "    %(time)s [%(level)s]:" % row
            print "     * %(message)s" % row

    def getMuninData(self, type):
        if string.split(type,' ')[0] == 'Downstream':
            return parsePageContents(getPageContents('CmDnstream'))[type]
        else:
            return parsePageContents(getPageContents('CmUpstream'))[type]

    def printMuninConfig(self, type):
        # prints config for a given type
        value = getMuninData(type)
        units = value.split(' ')[1]

        return 'graph_title %s\ngraph_vlabel %s\ngraph_category DOCSIS\ngraph_info %s (%s)\ndata.label %s\ndata.info %s\n' % (type, units, type, units, type, type)

    def printMuninOutput(self, type):
        # prints output for a given type
        value = getMuninData(type)

        return 'data.value %s\n' % value.split(' ')[0]

if __name__ == '__main__':
    obj = WebSTAR()
    obj.printPrettyStatus()

#    if os.path.dirname(sys.argv[0]) == '/etc/munin/plugins':
#        # we're running as a munin plugin!
#        executetype = os.path.basename(sys.argv[0]).split('_')[1].replace('.', ' ')
#        if len(sys.argv) > 1 and sys.argv[1] == 'config':
#            sys.stdout.write(printMuninConfig(executetype))
#        else:
#            sys.stdout.write(printMuninOutput(executetype))
#    else:
#        print `buildModemDetails()`
#    print `printMuninConfig('Downstream Receive Power Level')`
#    print `printMuninOutput('Downstream Receive Power Level')`

# vim: et:ts=4:sw=4
