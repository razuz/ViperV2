# This file is part of Viper - https://github.com/viper-framework/viper
# See the file 'LICENSE' for copying permission.

import re
import json
import getpass

try:
    import requests
    HAVE_REQUESTS = True
except ImportError:
    HAVE_REQUESTS = False

try:
    from bs4 import BeautifulSoup
    HAVE_BS4 = True
except ImportError:
    HAVE_BS4 = False

from viper.common.utils import string_clean
from viper.common.abstracts import Module
from viper.core.session import __sessions__
from viper.core.config import Config

cfg = Config()

class Reports(Module):
    cmd = 'reports'
    description = 'Online Sandboxes Reports'
    authors = ['emdel', 'nex', 'deralexxx']

    def __init__(self):
        super(Reports, self).__init__()
        self.parser.add_argument('--malwr', action='store_true', help='Find reports on Malwr')
        self.parser.add_argument('--anubis', action='store_true', help='Find reports on Anubis')
        self.parser.add_argument('--threat', action='store_true', help='Find reports on ThreatExchange')
        self.parser.add_argument('--joe', action='store_true', help='Find reports on Joe Sandbox')
        self.parser.add_argument('--meta', action='store_true', help='Find reports on metascan')

    def authenticate(self):
        username = raw_input('Username: ')
        password = getpass.getpass('Password: ')

        return (username, password)

    def malwr_parse(self, page):
        reports = []
        soup = BeautifulSoup(page)
        tables = soup.findAll('table')
        if len(tables) > 1:
            table = tables[1]
            rows = table.findAll('tr')
            for row in rows:
                cols = row.findAll('td')
                if cols:
                    time = str(cols[0].string)
                    link = cols[1].find('a')
                    url = '{0}{1}'.format(cfg.reports.malwr_prefix, link.get("href"))
                    reports.append([time, url])

            return reports

    def malwr(self):
        if not cfg.reports.malwr_user or not cfg.reports.malwr_pass:
            choice = raw_input("You need to specify a valid username/password, login now? [y/N] ")
            if choice == 'y':
                username, password = self.authenticate()
            else:
                return
        else:
            username = cfg.reports.malwr_user
            password = cfg.reports.malwr_pass
        try:
            sess = requests.Session()
            sess.auth = (username, password)

            sess.get(cfg.reports.malwr_login, verify=False)
            csrf = sess.cookies['csrftoken']

            sess.post(
                cfg.reports.malwr_login,
                {'username': username, 'password': password, 'csrfmiddlewaretoken': csrf},
                headers=dict(Referer=cfg.reports.malwr_login),
                verify=False,
                timeout=60
                )
        except:
            self.log('info', "Error while connecting to malwr")
            return
        payload = {'search': __sessions__.current.file.sha256, 'csrfmiddlewaretoken': csrf}
        headers = {"Referer": cfg.reports.malwr_search}
        p = sess.post(
            cfg.reports.malwr_search,
            payload,
            headers=headers,
            timeout=60,
            verify=False
        )

        reports = self.malwr_parse(p.text)
        if not reports:
            self.log('info', "No reports for opened file")
            return

        self.log('table', dict(header=['Time', 'URL'], rows=reports))

    def anubis_parse(self, page):
        reports = []
        soup = BeautifulSoup(page)
        tables = soup.findAll('table')

        if len(tables) >= 5:
            table = tables[4]
            cols = table.findAll('td')
            time = cols[1].string.strip()
            link = cols[4].find('a')
            url = '{0}{1}'.format(cfg.reports.anubis_prefix, link.get('href'))
            reports.append([time, url])
            return reports

    def anubis(self):
        if not cfg.reports.anubis_user or not cfg.reports.anubis_pass:
            choice = raw_input("You need to specify a valid username/password, login now? [y/N] ")
            if choice == 'y':
                username, password = self.authenticate()
            else:
                return
        else:
            username = cfg.reports.anubis_user
            password = cfg.reports.anubis_pass

        sess = requests.Session()
        sess.auth = (username, password)

        res = sess.post(
            cfg.reports.anubis_login,
            {'username': username, 'password': password},
            verify=False
        )
        res = sess.post(
            cfg.reports.anubis_search,
            {'hashlist': __sessions__.current.file.sha256},
            verify=False
        )

        reports = self.anubis_parse(res.text)
        if not reports:
            self.log('info', "No reports for opened file")
            return

        self.log('table', dict(header=['Time', 'URL'], rows=reports))

    def threat(self):
        # need the URL and the date
        url = 'http://www.threatexpert.com/report.aspx?md5={0}'.format(__sessions__.current.file.md5)
        page = requests.get(url)
        reports = []
        soup = BeautifulSoup(page.text)
        if soup.title.text.startswith('ThreatExpert Report'):
            lists = soup.findAll('li')
            if len(lists) > 0:
                time = lists[1].text[21:]
                reports.append([time, url])
                self.log('table', dict(header=['Time', 'URL'], rows=reports))
        else:
            self.log('info', "No reports for opened file")

    def joe(self):
        url = 'http://www.joesecurity.org/reports/report-{0}.html'.format(__sessions__.current.file.md5)
        page = requests.get(url)
        if '<h2>404 - File Not Found</h2>' in page.text or 'Apparently the requested URL could not be found' in page.text:
            self.log('info', "No reports for opened file")
	elif '403 Forbidden' in page.text:
	    self.log('info', "Permission to joe denied")
        else:
            self.log('info', "Report found at {0}".format(url))

    def meta(self):
        url = 'https://www.metascan-online.com/en/scanresult/file/{0}'.format(__sessions__.current.file.md5)
        page = requests.get(url)
        reports = []
        if '<title>Error</title>' in page.text:
            self.log('info', "No reports for opened file")
            return
        pattern = 'scanResult = (.*)};'
        match = re.search(pattern, page.text)
        raw_results = match.group(0)[13:-1]
        json_results = json.loads(raw_results)
        unprocessed = json_results['scan_results']['scan_details']
        for vendor, results in unprocessed.iteritems():
            if results['scan_result_i'] == 1:
                reports.append([vendor, string_clean(results['threat_found']), results['def_time']])
                self.log('table', dict(header=['Vendor', 'Result', 'Time'], rows=reports))
                return

    def usage(self):
        self.log('', "Usage: reports <malwr|anubis|threat|joe|meta>")

    def run(self):
        super(Reports, self).run()
        if self.args is None:
            return

        if not HAVE_REQUESTS and not HAVE_BS4:
            self.log('error', "Missing dependencies (`pip install requests beautifulsoup4`)")
            return

        if not __sessions__.is_set():
            self.log('error', "No session opened")
            return

        if self.args.malwr:
            self.malwr()
        elif self.args.anubis:
            self.anubis()
        elif self.args.threat:
            self.threat()
        elif self.args.joe:
            self.joe()
        elif self.args.meta:
            self.meta()
        else:
            self.log('error', 'At least one of the parameters is required')
            self.usage()
