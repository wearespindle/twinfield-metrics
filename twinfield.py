import logging
import pprint
import requests
from requests_xml import XMLSession
import socket
from string import Template
import time
import xmltodict
from xml.dom.minidom import parseString

logger = logging.getLogger(__name__)
pp = pprint.PrettyPrinter(indent=4)

class TwinfieldApi(object):
    """
    TwinfieldConnector supplies connection to Twinfield.

    This class uses the Twinfield __credentials from a partner to make a
    connection. Verify whether the partner uses Twinfield and has
    twinfield__credentials, before initializing this class. Between
    start_session and end_session xml can be sent and received by the send
    function. The functions in this file utilize the connector.
    """
    __wsdl_url = 'https://login.twinfield.com/webservices/session.asmx?wsdl'
    __sessionid = None
    __credentials = {}

    # Twinfield supplied URL to do requests to for the current session.
    _root_url = None

    # Some, but not all requests require an updated office action.
    # 'updated_office' reflects whether this action has been performed.
    updated_office = False
    office = None

    def __init__(self, credentials):
        """
        Initializes the TwinfieldConnector.

        Can be used with a 'with' construction.
        """
        self.__credentials = credentials
        self.office = credentials['office']

    def __enter__(self):
        self.start_session()
        return self

    def __exit__(self, type, value, traceback):
        self.end_session()

    def start_session(self):
        """
        Starts the twinfield session. Not needed when using the 'with' construction.
        """
        xml = render_to_string(
            'twinfield/xml/logon.xml',
            context=self.__credentials,
        )
        headers = {'content-type': 'text/xml'}        
        response = requests.post(self.__wsdl_url, data = xml, headers=headers)        
        response = xmltodict.parse(response.text)

        # Session ID and root are needed for further requests.
        self.__sessionid = response['soap:Envelope']['soap:Header']['Header']['SessionID']
        self._root_url = response['soap:Envelope']['soap:Body']['LogonResponse']['cluster']
        return self

    def end_session(self):
        """
        Ends the twinfield session. Automatically called in `__exit__` when
        using the 'with' construction.
        """
        if (not self.has_session()):
            return

        xml = render_to_string('twinfield/xml/abandon.xml', context={'sessionid': self.__sessionid})
        headers = {'content-type': 'text/xml'}
        response = requests.post(self._root_url, data = xml, headers=headers)
        if response.status_code != 200:
            raise TwinfieldError(
                'TwinfieldError, Response code was: %s\n\nFull response was: %s' % (response.code, response.text))

        self.__sessionid = None
        self.office = None
        self.updated_office = False

    def has_session(self):
        """
        Determine whether this instance has a Twinfield session.
        """
        return self.__sessionid is not None

    def change_office(self):
        """
        Changes the Twinfield office for the current session.
        """
        xml = render_to_string('twinfield/xml/office.xml', context={'office': self.office})
        url = '%s/webservices/session.asmx?wsdl' % self._root_url
        response = self.send(xml, url, 'http://www.twinfield.com/SelectCompany')
        real_xml = parseString(response.text)
        if real_xml.getElementsByTagName('SelectCompanyResult')[0].firstChild.nodeValue != 'Ok':
            raise TwinfieldError(
                'Could not change to office: %s \nResponse code was: %s\n\nFull response was: %s' % (self.office, response.code, response.text))

    def send(self, xml, url = None, soapaction='http://www.twinfield.com/ProcessXmlString'):
        if soapaction == 'http://www.twinfield.com/ProcessXmlString':
            xml = render_to_string('twinfield/xml/proces.xml', context={'xml': xml})
        data = render_to_string('twinfield/xml/send.xml', context={'sessionid': self.__sessionid, 'xml': xml})
        if not url:
            url = '%s/webservices/processxml.asmx?wsdl' % self._root_url
        headers = {'content-type': 'text/xml'}
        response = requests.post(url, data = data, headers=headers)
        return response


def render_to_string(xmlpath, context=None):
    """
    Renders an xml file to string and substitutes the variables from `context`
    when when `context` is not empty.
    """
    
    xmlfile = open('templates/%s' % xmlpath)
    if context:
        xml = Template(xmlfile.read()).substitute(context)
    else:
        xml = xmlfile.read()
    return xml


class TwinfieldError(Exception):
    """
    General Twinfield error.
    """
    pass


class TwinfieldLogonError(TwinfieldError):
    """
    Raised when Twinfield logon fails for some reason.
    """
    pass
