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

        self.groups = [
            ('modem', self.modem),
            ('downstream', self.downstream),
            ('upstream', self.upstream),
        ]

    # Low-level methods that talk to the cable modem and rip off its
    # delicious secrets.
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

    @staticmethod
    def clean(string):
        return ' '.join(string.strip(u'\xa0').replace('\n', '').split()).strip()

    def getPageContents(self, pagename):
        # Returns a list of strings for a given page.
        if pagename in self._contents_cache:
            return self._contents_cache[pagename]

        with self.escalatedPrivileges():
            result = urllib2.urlopen('http://%s/%s' % (self.ip, pagename), None, TIMEOUT)
            self._contents_cache[pagename] = result.readlines()
            return self._contents_cache[pagename]

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

    # Helper methods that provide interfaces to the data
    def get_details(self, key):
        if key not in ['log', 'signal', 'status', 'system']:
            return {}
        if key not in self._details:
            self._details[key] = self.parsePageContents(self.getPageContents('%s.asp' % key))
        return self._details[key]

    def metric(self, metric):
        # Pulls a metric, in group_key format
        group, key = metric.split('_', 1)
        return getattr(self, group)[key]

    # Properties that expose the data for easy accessibility
    @property
    def log(self):
        return self.get_details('log')

    @property
    def signal(self):
        return self.get_details('signal')

    @property
    def status(self):
        return self.get_details('status')

    @property
    def system(self):
        return self.get_details('system')

    @property
    def downstream(self):
        result = {}
        suffix = ''

        for candidate in self.signal.keys():
            if candidate.startswith('Downstream'):
                suffix = candidate[-2:]

        result['bitrate_str'] = self.signal['Bit Rate' + suffix]
        result['channel_str'] = self.signal['Channel ID' + suffix]
        result['frequency_str'] = self.signal['Downstream Frequency' + suffix]
        result['modulation'] = self.signal['Modulation' + suffix]
        result['power_str'] = self.signal['Power Level' + suffix]
        result['snr_str'] = self.signal['Signal to Noise Ratio' + suffix]
        result['status'] = self.signal['Downstream Status' + suffix]

        result['bitrate'] = int(result['bitrate_str'].split()[0])
        result['channel'] = int(result['channel_str'].split()[0])
        result['frequency'] = int(result['frequency_str'].split()[0])
        result['power'] = float(result['power_str'].split()[0])
        result['snr'] = float(result['snr_str'].split()[0])

        return result

    @property
    def upstream(self):
        result = {}
        suffix = ''

        for candidate in self.signal.keys():
            if candidate.startswith('Upstream'):
                suffix = candidate[-2:]

        result['bitrate_str'] = self.signal['Bit Rate' + suffix]
        result['channel_str'] = self.signal['Channel ID' + suffix]
        result['frequency_str'] = self.signal['Upstream Frequency' + suffix]
        result['modulation'] = self.signal['Modulation' + suffix]
        result['power_str'] = self.signal['Power Level' + suffix]
        result['status'] = self.signal['Upstream Status' + suffix]

        result['bitrate'] = int(result['bitrate_str'].split()[0])
        result['channel'] = int(result['channel_str'].split()[0])
        result['frequency'] = int(result['frequency_str'].split()[0])
        result['power'] = float(result['power_str'].split()[0])

        return result

    @property
    def modem(self):
        result = {}

        result['cable_ip'] = self.status['IP Address_0']
        result['certificate'] = self.status['Cable Modem Certificate_0']
        result['current_time'] = self.status['Current Time_0']
        result['status'] = self.status['Cable Modem Status_0']
        result['uptime_str'] = self.status['Time Since Last Reset_0']

        secs = 0
        for chunk in result['uptime_str'].split(':'):
            if chunk.endswith('s'):
                secs += int(chunk.strip('s'))
            elif chunk.endswith('m'):
                secs += int(chunk.strip('m'))*60
            elif chunk.endswith('h'):
                days, word, hours = chunk.split()
                secs += int(hours.strip('h'))*60*60
                secs += int(days)*24*60*60

        result['uptime'] = secs

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

    @property
    def metrics(self):
        # Prepares a list of useful metrics
        for group, mapping in self.groups:
            for key, value in mapping.items():
                yield '%s_%s' % (group, key)

    @property
    def numeric_metrics(self):
        # Prepares a list of numeric metrics
        for metric in self.metrics:
            if metric.endswith('_str'):
                continue

            value = self.metric(metric)
            try:
                candidate = float(value)
                yield metric
            except:
                continue

    # Pretty output methods
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

if __name__ == '__main__':
    obj = WebSTAR()

    if len(sys.argv) > 1 and sys.argv[1] == 'autoconf':
        if obj.status:
            print "yes"
            sys.exit(0)
        else:
            print "no (modem not found)"
            sys.exit(0)

    elif len(sys.argv) > 1 and sys.argv[1] == 'suggest':
        things = {}
        for thing in obj.numeric_metrics:
            subthing = thing.split('_', 1)[1]
            if subthing in things:
                things[subthing] += 1
            else:
                things[subthing] = 1
            print thing
        for thing, count in things.items():
            if count == 2:
                print 'combined_%s' % thing

    elif len(sys.argv) > 1 and sys.argv[1] in obj.metrics:
        print obj.metric(sys.argv[1])

    elif os.path.dirname(sys.argv[0]) == '/etc/munin/plugins':
        # we're running as a munin plugin!
        filename, group, metric = os.path.basename(sys.argv[0]).split('_', 2)
        if len(sys.argv) > 1 and sys.argv[1] == 'config':
            ref = '_'.join(['downstream' if group == 'combined' else group, metric, 'str'])
            units = obj.metric(ref).split()[-1:][0] if ref in obj.metrics else metric
            # special case
            if metric == 'uptime':
                units = 'seconds'
            name = obj.system['Name_0']

            print "graph_title %s %s - %s" % (group, metric, name)
            print "graph_vlabel %s" % units
            print "graph_category network"
            print "graph_info Shows %s %s for a %s cable modem." % (group, metric, name)

            if group == 'combined':
                print "up.label upstream_%s" % metric
                print "up.info Upstream %s in %s" % (metric, units)
                print "dn.label downstream_%s" % metric
                print "dn.info Downstream %s in %s" % (metric, units)
            else:
                print "data.label %s" % '_'.join([group, metric])
                print "data.info %s" % ' '.join([group, metric])

        else:
            if group == 'combined':
                print "up.value %s" % obj.metric('_'.join(['upstream', metric]))
                print "dn.value %s" % obj.metric('_'.join(['downstream', metric]))
            else:
                print "data.value %s" % obj.metric('_'.join([group, metric]))

    else:
        # Default to pretty status
        obj.printPrettyStatus()

# vim: et:ts=4:sw=4
