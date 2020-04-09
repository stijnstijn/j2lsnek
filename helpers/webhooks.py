from logging.handlers import HTTPHandler

import json


class WebHookLogHandler(HTTPHandler):
    """
    Basic HTTPHandler for Discord and Slack webhooks via standard log handling
    """
    server_name = ""

    def __init__(self, url, server_name):
        """
        Initialise WebHook handler
        """
        host = url.split("/")[2]
        secure = url[0:5] == "https"

        super().__init__(host, url, method="POST", secure=secure)
        self.server_name = server_name

    def emit(self, record):
        """
        Emit a record.

        Send the record to the Web server as a percent-encoded dictionary

        This is the `emit()` method of the original HTTPHandler; the only
        change is that content is sent as JSON (which the webhooks expect)
        instead of urlencoded data
        """
        try:
            import http.client, urllib.parse
            host = self.host
            if self.secure:
                h = http.client.HTTPSConnection(host, context=self.context)
            else:
                h = http.client.HTTPConnection(host)
            url = self.url
            ############### CHANGED FROM ORIGINAL ###############
            data = json.dumps(self.mapLogRecord(record))
            #####################################################
            if self.method == "GET":
                if (url.find('?') >= 0):
                    sep = '&'
                else:
                    sep = '?'
                url = url + "%c%s" % (sep, data)
            h.putrequest(self.method, url)
            # support multiple hosts on one IP address...
            # need to strip optional :port from host, if present
            i = host.find(":")
            if i >= 0:
                host = host[:i]
            # See issue #30904: putrequest call above already adds this header
            # on Python 3.x.
            # h.putheader("Host", host)
            if self.method == "POST":
                ############### CHANGED FROM ORIGINAL ###############
                h.putheader("Content-type", "application/json")
                #####################################################
                h.putheader("Content-length", str(len(data)))
            if self.credentials:
                import base64
                s = ('%s:%s' % self.credentials).encode('utf-8')
                s = 'Basic ' + base64.b64encode(s).strip().decode('ascii')
                h.putheader('Authorization', s)
            h.endheaders()
            if self.method == "POST":
                h.send(data.encode('utf-8'))
            h.getresponse()  # can't do anything with the result
        except Exception:
            self.handleError(record)


class DiscordLogHandler(WebHookLogHandler):
    """
    Discord webhook log handler
    """

    def mapLogRecord(self, record):
        """
        Format log message so it is compatible with Discord webhooks
        """
        return {
            "content": ":bell: An alert was logged by j2lsnek:",
            "author": {
                "name": self.server_name
            },
            "embeds": [{
                "description": record.msg,
                "fields": [{
                    "name": "Server",
                    "value": self.server_name,
                    "inline": True
                }, {
                    "name": "Severity",
                    "value": record.levelname,
                    "inline": True
                }]
            }]
        }


class SlackLogHandler(WebHookLogHandler):
    """
    Slack webhook log handler
    """

    def mapLogRecord(self, record):
        """
        Format log message so it is compatible with Slack webhooks
        """
        return {
            "text": record.msg,
            "mrkdwn_in": ["text"],
            "attachments": [{
                "fields": [{
                    "title": "Server",
                    "value": self.server_name,
                    "short": True
                }, {
                    "title": "Severity",
                    "value": record.levelname,
                    "short": True
                }]
            }]
        }
