#!/usr/bin/env python2
# -*- coding: utf-8 -*-
'''
AceProxy: Ace Stream to HTTP Proxy

Website: https://github.com/ValdikSS/AceProxy
'''
import gevent
import gevent.monkey
# Monkeypatching and all the stuff
gevent.monkey.patch_all()
import glob
import os
import signal
import sys
import logging
import BaseHTTPServer
import SocketServer
from socket import error as SocketException
import urllib2
import hashlib
import aceclient
import aceconfig
from aceconfig import AceConfig
import vlcclient
import plugins.modules.ipaddr as ipaddr
from aceclient.clientcounter import ClientCounter
from plugins.modules.PluginInterface import AceProxyPlugin

#WebScraping
from bs4 import BeautifulSoup

try:
    import pwd
    import grp
except ImportError:
    # Windows
    pass

class HTTPHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    requestlist = []

    myServer = "http://185.53.131.158:8000"

    queryList = [
        'daddylive', 'morningstreams', 'overtakefans'
    ]

    channels = [
        ('DanishBay', '88994d418b6cf4b6052dce047abcb71110b0e7e7', 'http://185.53.131.158:8000/pid/88994d418b6cf4b6052dce047abcb71110b0e7e7/Danishbay.mp4')
    ]

    def findPIDList(self):
        for q in self.queryList:
            URL = "https://acestreamsearch.net/en/?q=" + str(q)
            page = urllib2.Request(URL)
            response = urllib2.urlopen(page)
            content = response.read()
            soup = BeautifulSoup(content, 'lxml')
            results = soup.find_all("li", class_="list-group-item")
            if results:
                for li in results:
                    pid = li.span.get("data-copy")
                    name = li.a.text
                    self.channels.append((str(name), str(pid), str(self.myServer) + "/pid/" + str(pid) + "/" + str(name.replace(" ", "")) + ".mp4"))

    def findPID(self, q):
        URL = 'https://acestreamsearch.net/en/?q=' + str(q)
        page = urllib2.Request(URL)
        response = urllib2.urlopen(page)
        content = response.read()
        soup = BeautifulSoup(content, 'lxml')
        span = soup.find_all("span", class_="pull-right glyphicon glyphicon-copy js-tooltip js-copy")
        if span:
            for pid in span:
                #Implement VLC check
                #self.vlcid = pid.get("data-copy")
                #AceConfig.vlcuse -...
                #self.proxyReadWrite()
                return "/pid/" + str(pid.get("data-copy")) + "/" + str(q) + ".mp4"

    def generateM3U(self):
        strPlaylist = "#EXTM3U \n"
        for channel in self.channels:
            strElement = "#EXTINF:0," + str(channel[0]) + ".mp4 \n"
            strElement += "#EXTVLCOPT:network-caching=1000 \n"
            strElement += str(channel[2]) + "\n"
            strPlaylist += strElement
        return strPlaylist


    def handle_one_request(self):
        '''
        Add request to requestlist, handle request and remove from the list
        '''
        HTTPHandler.requestlist.append(self)
        BaseHTTPServer.BaseHTTPRequestHandler.handle_one_request(self)
        HTTPHandler.requestlist.remove(self)

    def closeConnection(self):
        '''
        Disconnecting client
        '''
        if self.clientconnected:
            self.clientconnected = False
            try:
                self.wfile.close()
                self.rfile.close()
            except:
                pass

    def dieWithError(self, errorcode=500):
        '''
        Close connection with error
        '''
        logger.flush()
        logging.warning("Dying with error")
        if self.clientconnected:
            self.send_error(errorcode)
            self.end_headers()
            self.closeConnection()

    def proxyReadWrite(self):
        '''
        Read video stream and send it to client
        '''
        logger = logging.getLogger('http_proxyReadWrite')
        logger.debug("Started")

        self.vlcstate = True

        try:
            while True:
                if AceConfig.videoobey and not AceConfig.vlcuse:
                    # Wait for PlayEvent if videoobey is enabled. Not for VLC
                    self.ace.getPlayEvent()

                if AceConfig.videoobey and AceConfig.vlcuse:
                    # For VLC
                    try:
                        # Waiting 0.5 seconds. If timeout, there would be exception.
                        # Set vlcstate to False in the exception and pause the
                        # stream
                        # A bit ugly, huh?
                        self.ace.getPlayEvent(0.5)
                        if not self.vlcstate:
                            AceStuff.vlcclient.unPauseBroadcast(self.vlcid)
                            self.vlcstate = True
                    except gevent.Timeout:
                        if self.vlcstate:
                            AceStuff.vlcclient.pauseBroadcast(self.vlcid)
                            self.vlcstate = False

                if not self.clientconnected:
                    logger.debug("Client is not connected, terminating")
                    break

                data = self.video.read(4096)
                if data and self.clientconnected:
                    self.wfile.write(data)
                else:
                    logger.warning("Video connection closed")
                    break
        except SocketException:
            # Video connection dropped
            logger.warning("Video connection dropped")
        finally:
            self.video.close()
            self.closeConnection()

    def hangDetector(self):
        '''
        Detect client disconnection while in the middle of something
        or just normal connection close.
        '''
        logger = logging.getLogger('http_hangDetector')
        try:
            while True:
                if not self.rfile.read():
                    break
        except:
            pass
        finally:
            self.clientconnected = False
            logger.debug("Client disconnected")
            try:
                self.requestgreenlet.kill()
            except:
                pass
            finally:
                gevent.sleep()
            return

    def do_HEAD(self):
        return self.do_GET(headers_only=True)

    def do_GET(self, headers_only=False):
        '''
        GET request handler
        '''
        logger = logging.getLogger('http_HTTPHandler')
        self.clientconnected = True
        # Don't wait videodestroydelay if error happened
        self.errorhappened = True
        # Headers sent flag for fake headers UAs
        self.headerssent = False
        # Current greenlet
        self.requestgreenlet = gevent.getcurrent()
        # Connected client IP address
        self.clientip = self.request.getpeername()[0]

        if AceConfig.firewall:
            # If firewall enabled
            self.clientinrange = any(map(lambda i: ipaddr.IPAddress(self.clientip) \
                                in ipaddr.IPNetwork(i), AceConfig.firewallnetranges))

            if (AceConfig.firewallblacklistmode and self.clientinrange) or \
                (not AceConfig.firewallblacklistmode and not self.clientinrange):
                    logger.info('Dropping connection from ' + self.clientip + ' due to ' + \
                                'firewall rules')
                    self.dieWithError(403)  # 403 Forbidden
                    return

        logger.info("Accepted connection from " + self.clientip + " path " + self.path)

        try:
            self.splittedpath = self.path.split('/')
            self.reqtype = self.splittedpath[1].lower()
        except IndexError:
            self.dieWithError(400)  # 400 Bad Request
            return

        logger.info(self.splittedpath)
        # Serve m3u file
        if self.reqtype == 'm3u':
            try:
                if len(self.splittedpath) > 2:
                    self.path = self.findPID(self.splittedpath[2].lower())
                    #self.send_response(200)
                    #self.send_header('Content-type', 'html')
                    #self.end_headers()
                    #self.wfile.write(self.path)
                else:
                    self.findPIDList()
                    m3u = self.generateM3U()
                    self.send_response(200)
                    self.send_header('Content-type', 'audio/x-mpegurl')
                    self.end_headers()
                    self.wfile.write(m3u)
                    return
            except Exception as e:
                logger.error(repr(e))
                logger.info("If fail")
                self.dieWithError(400)
                return

        try:
            self.splittedpath = self.path.split('/')
            self.reqtype = self.splittedpath[1].lower()
            # If first parameter is 'pid' or 'torrent' or it should be handled
            # by plugin
            if not (self.reqtype in ('pid', 'torrent') or self.reqtype in AceStuff.pluginshandlers):
                logger.info(self.splittedpath)
                self.dieWithError(400)  # 400 Bad Request
                return
        except IndexError:
            self.dieWithError(400)  # 400 Bad Request
            return

        # Handle request with plugin handler
        if self.reqtype in AceStuff.pluginshandlers:
            try:
                AceStuff.pluginshandlers.get(self.reqtype).handle(self)
            except Exception as e:
                logger.error('Plugin exception: ' + repr(e))
                self.dieWithError()
            finally:
                self.closeConnection()
                return

        # Check if third parameter exists
        # …/pid/blablablablabla/video.mpg
        #                      |_________|
        # And if it ends with regular video extension

        try:
            if not self.path.endswith(('.3gp', '.avi', '.flv', '.mkv', '.mov', '.mp4', '.mpeg', '.mpg', '.ogv', '.ts')):
                logger.error("Request seems like valid but no valid video extension was provided")
                self.dieWithError(400)
                return
        except IndexError:
            self.dieWithError(400)  # 400 Bad Request
            return

        # Limit concurrent connections
        if AceConfig.maxconns > 0 and AceStuff.clientcounter.total >= AceConfig.maxconns:
            logger.debug("Maximum connections reached, can't serve this")
            self.dieWithError(503)  # 503 Service Unavailable
            return

        # Pretend to work fine with Fake UAs or HEAD request.
        useragent = self.headers.get('User-Agent')
        fakeua = useragent and useragent in AceConfig.fakeuas
        if headers_only or fakeua:
            if fakeua:
                logger.debug("Got fake UA: " + self.headers.get('User-Agent'))
            # Return 200 and exit
            self.send_response(200)
            self.send_header("Content-Type", "video/mpeg")
            self.end_headers()
            self.closeConnection()
            return

        self.path_unquoted = urllib2.unquote(self.splittedpath[2])
        # Make list with parameters
        self.params = list()
        for i in xrange(3, 8):
            try:
                self.params.append(int(self.splittedpath[i]))
            except (IndexError, ValueError):
                self.params.append('0')

        # Adding client to clientcounter
        clients = AceStuff.clientcounter.add(self.path_unquoted, self.clientip)
        # If we are the one client, but sucessfully got ace from clientcounter,
        # then somebody is waiting in the videodestroydelay state
        self.ace = AceStuff.clientcounter.getAce(self.path_unquoted)
        if not self.ace:
            shouldcreateace = True
        else:
            shouldcreateace = False

        # Use PID as VLC ID if PID requested
        # Or torrent url MD5 hash if torrent requested
        if self.reqtype == 'pid':
            self.vlcid = self.path_unquoted
        else:
            self.vlcid = hashlib.md5(self.path_unquoted).hexdigest()

        # If we don't use VLC and we're not the first client
        if clients != 1 and not AceConfig.vlcuse:
            AceStuff.clientcounter.delete(self.path_unquoted, self.clientip)
            logger.error(
                "Not the first client, cannot continue in non-VLC mode")
            self.dieWithError(503)  # 503 Service Unavailable
            return

        if shouldcreateace:
        # If we are the only client, create AceClient
            try:
                self.ace = aceclient.AceClient(
                    AceConfig.acehost, AceConfig.aceport, connect_timeout=AceConfig.aceconntimeout,
                    result_timeout=AceConfig.aceresulttimeout)
                # Adding AceClient instance to pool
                AceStuff.clientcounter.addAce(self.path_unquoted, self.ace)
                logger.debug("AceClient created")
            except aceclient.AceException as e:
                logger.error("AceClient create exception: " + repr(e))
                AceStuff.clientcounter.delete(
                    self.path_unquoted, self.clientip)
                self.dieWithError(502)  # 502 Bad Gateway
                return

        # Send fake headers if this User-Agent is in fakeheaderuas tuple
        if fakeua:
            logger.debug(
                "Sending fake headers for " + useragent)
            self.send_response(200)
            self.send_header("Content-Type", "video/mpeg")
            self.end_headers()
            # Do not send real headers at all
            self.headerssent = True

        try:
            self.hanggreenlet = gevent.spawn(self.hangDetector)
            logger.debug("hangDetector spawned")
            gevent.sleep()

            # Initializing AceClient
            if shouldcreateace:
                self.ace.aceInit(
                    gender=AceConfig.acesex, age=AceConfig.aceage,
                    product_key=AceConfig.acekey, pause_delay=AceConfig.videopausedelay)
                logger.debug("AceClient inited")
                if self.reqtype == 'pid':
                    contentinfo = self.ace.START(
                        self.reqtype, {'content_id': self.path_unquoted, 'file_indexes': self.params[0]})
                elif self.reqtype == 'torrent':
                    self.paramsdict = dict(
                        zip(aceclient.acemessages.AceConst.START_TORRENT, self.params))
                    self.paramsdict['url'] = self.path_unquoted
                    contentinfo = self.ace.START(self.reqtype, self.paramsdict)
                logger.debug("START done")

            # Getting URL
            self.url = self.ace.getUrl(AceConfig.videotimeout)
            # Rewriting host for remote Ace Stream Engine
            self.url = self.url.replace('127.0.0.1', AceConfig.acehost)
            self.errorhappened = False

            if shouldcreateace:
                logger.debug("Got url " + self.url)
                # If using VLC, add this url to VLC
                if AceConfig.vlcuse:
                    # Force ffmpeg demuxing if set in config
                    if AceConfig.vlcforceffmpeg:
                        self.vlcprefix = 'http/ffmpeg://'
                    else:
                        self.vlcprefix = ''

                    # Sleeping videodelay
                    gevent.sleep(AceConfig.videodelay)

                    AceStuff.vlcclient.startBroadcast(
                        self.vlcid, self.vlcprefix + self.url, AceConfig.vlcmux, AceConfig.vlcpreaccess)
                    # Sleep a bit, because sometimes VLC doesn't open port in
                    # time
                    gevent.sleep(0.5)

            # Building new VLC url
            if AceConfig.vlcuse:
                self.url = 'http://' + AceConfig.vlchost + \
                    ':' + str(AceConfig.vlcoutport) + '/' + self.vlcid
                logger.debug("VLC url " + self.url)

            # Sending client headers to videostream
            self.video = urllib2.Request(self.url)
            for key in self.headers.dict:
                self.video.add_header(key, self.headers.dict[key])

            self.video = urllib2.urlopen(self.video)

            # Sending videostream headers to client
            if not self.headerssent:
                self.send_response(self.video.getcode())
                if self.video.info().dict.has_key('connection'):
                    del self.video.info().dict['connection']
                if self.video.info().dict.has_key('server'):
                    del self.video.info().dict['server']
                if self.video.info().dict.has_key('transfer-encoding'):
                    del self.video.info().dict['transfer-encoding']
                if self.video.info().dict.has_key('keep-alive'):
                    del self.video.info().dict['keep-alive']

                for key in self.video.info().dict:
                    self.send_header(key, self.video.info().dict[key])
                # End headers. Next goes video data
                self.end_headers()
                logger.debug("Headers sent")

            if not AceConfig.vlcuse:
                # Sleeping videodelay
                gevent.sleep(AceConfig.videodelay)

            # Run proxyReadWrite
            self.proxyReadWrite()

            # Waiting until hangDetector is joined
            self.hanggreenlet.join()
            logger.debug("Request handler finished")

        except (aceclient.AceException, vlcclient.VlcException, urllib2.URLError) as e:
            logger.error("Exception: " + repr(e))
            self.errorhappened = True
            self.dieWithError()
        except gevent.GreenletExit:
            # hangDetector told us about client disconnection
            pass
        except Exception as e:
            # Unknown exception
            logger.error("Unknown exception: " + repr(e))
            self.errorhappened = True
            self.dieWithError()
        finally:
            logger.debug("END REQUEST")
            AceStuff.clientcounter.delete(self.path_unquoted, self.clientip)
            if not self.errorhappened and not AceStuff.clientcounter.get(self.path_unquoted):
                # If no error happened and we are the only client
                logger.debug("Sleeping for " + str(
                    AceConfig.videodestroydelay) + " seconds")
                gevent.sleep(AceConfig.videodestroydelay)
            if not AceStuff.clientcounter.get(self.path_unquoted):
                logger.debug("That was the last client, destroying AceClient")
                if AceConfig.vlcuse:
                    try:
                        AceStuff.vlcclient.stopBroadcast(self.vlcid)
                    except:
                        pass
                self.ace.destroy()
                AceStuff.clientcounter.deleteAce(self.path_unquoted)


class HTTPServer(SocketServer.ThreadingMixIn, BaseHTTPServer.HTTPServer):

    def handle_error(self, request, client_address):
        # Do not print HTTP tracebacks
        pass


class AceStuff(object):
    '''
    Inter-class interaction class
    '''

# taken from http://stackoverflow.com/questions/2699907/dropping-root-permissions-in-python
def drop_privileges(uid_name, gid_name='nogroup'):

    # Get the uid/gid from the name
    running_uid = pwd.getpwnam(uid_name).pw_uid
    running_uid_home = pwd.getpwnam(uid_name).pw_dir
    running_gid = grp.getgrnam(gid_name).gr_gid

    # Remove group privileges
    os.setgroups([])

    # Try setting the new uid/gid
    os.setgid(running_gid)
    os.setuid(running_uid)

    # Ensure a very conservative umask
    old_umask = os.umask(077)

    if os.getuid() == running_uid and os.getgid() == running_gid:
        # could be useful
        os.environ['HOME'] = running_uid_home
        return True
    return False

logging.basicConfig(
    filename=AceConfig.logpath + 'acehttp.log' if AceConfig.loggingtoafile else None,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s', datefmt='%d.%m.%Y %H:%M:%S', level=AceConfig.debug)
logger = logging.getLogger('INIT')

# Loading plugins
# Trying to change dir (would fail in freezed state)
try:
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
except:
    pass
# Creating dict of handlers
AceStuff.pluginshandlers = dict()
# And a list with plugin instances
AceStuff.pluginlist = list()
pluginsmatch = glob.glob('plugins/*_plugin.py')
sys.path.insert(0, 'plugins')
pluginslist = [os.path.splitext(os.path.basename(x))[0] for x in pluginsmatch]
for i in pluginslist:
    plugin = __import__(i)
    plugname = i.split('_')[0].capitalize()
    try:
        plugininstance = getattr(plugin, plugname)(AceConfig, AceStuff)
    except Exception as e:
        logger.error("Cannot load plugin " + plugname + ": " + repr(e))
        continue
    logger.debug('Plugin loaded: ' + plugname)
    for j in plugininstance.handlers:
        AceStuff.pluginshandlers[j] = plugininstance
    AceStuff.pluginlist.append(plugininstance)

# Check whether we can bind to the defined port safely
if AceConfig.osplatform != 'Windows' and os.getuid() != 0 and AceConfig.httpport <= 1024:
    logger.error("Cannot bind to port " + str(AceConfig.httpport) + " without root privileges")
    quit(1)

server = HTTPServer((AceConfig.httphost, AceConfig.httpport), HTTPHandler)
logger = logging.getLogger('HTTP')

# Dropping root privileges if needed
if AceConfig.osplatform != 'Windows' and AceConfig.aceproxyuser and os.getuid() == 0:
    if drop_privileges(AceConfig.aceproxyuser):
        logger.info("Dropped privileges to user " + AceConfig.aceproxyuser)
    else:
        logger.error("Cannot drop privileges to user " + AceConfig.aceproxyuser)
        quit(1)

# Creating ClientCounter
AceStuff.clientcounter = ClientCounter()

# We need gevent >= 1.0.0 to use gevent.subprocess
if AceConfig.acespawn or AceConfig.vlcspawn:
    try:
        gevent.monkey.patch_subprocess()
    except:
        logger.error("Cannot spawn anything without gevent 1.0.0 or higher.")
        quit(1)

if AceConfig.vlcspawn or AceConfig.acespawn:
    DEVNULL = open(os.devnull, 'wb')

# Spawning procedures
def spawnVLC(cmd, delay = 0):
    try:
        AceStuff.vlc = gevent.subprocess.Popen(cmd, stdout=DEVNULL, stderr=DEVNULL)
        gevent.sleep(delay)
        return True
    except:
        return False

def connectVLC():
    try:
        AceStuff.vlcclient = vlcclient.VlcClient(
            host=AceConfig.vlchost, port=AceConfig.vlcport, password=AceConfig.vlcpass,
            out_port=AceConfig.vlcoutport)
        return True
    except vlcclient.VlcException as e:
        print repr(e)
        return False

def spawnAce(cmd, delay = 0):
    if AceConfig.osplatform == 'Windows':
        reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
        try:
            key = _winreg.OpenKey(reg, 'Software\AceStream')
        except:
            print "Can't find acestream!"
            quit(1)
        engine = _winreg.QueryValueEx(key, 'EnginePath')
        AceStuff.acedir = os.path.dirname(engine[0])
        try:
            AceConfig.aceport = int(open(AceStuff.acedir + '\\acestream.port', 'r').read())
            logger.warning("Ace Stream is already running, disabling runtime checks")
            AceConfig.acespawn = False
            return True
        except IOError:
            cmd = engine[0].split()
    try:
        AceStuff.ace = gevent.subprocess.Popen(cmd, stdout=DEVNULL, stderr=DEVNULL)
        gevent.sleep(delay)
        return True
    except:
        return False

def isRunning(process):
    if process.poll() is not None:
        return False
    return True

def clean_proc():
    # Trying to close all spawned processes gracefully
    if AceConfig.vlcspawn and isRunning(AceStuff.vlc):
        AceStuff.vlc.terminate()
        gevent.sleep(1)
        # or not :)
        if isRunning(AceStuff.vlc):
            AceStuff.vlc.kill()
    if AceConfig.acespawn and isRunning(AceStuff.ace):
        AceStuff.ace.terminate()
        gevent.sleep(1)
        if isRunning(AceStuff.ace):
            AceStuff.ace.kill()
        # for windows, subprocess.terminate() is just an alias for kill(), so we have to delete the acestream port file manually
        if AceConfig.osplatform == 'Windows' and os.path.isfile(AceStuff.acedir + '\\acestream.port'):
            os.remove(AceStuff.acedir + '\\acestream.port')

# This is what we call to stop the server completely
def shutdown(signum = 0, frame = 0):
    logger.info("Stopping server...")
    # Closing all client connections
    for connection in server.RequestHandlerClass.requestlist:
        try:
            # Set errorhappened to prevent waiting for videodestroydelay
            connection.errorhappened = True
            connection.hanggreenlet.kill()
        except:
            logger.warning("Cannot kill a connection!")
    clean_proc()
    server.server_close()
    quit()

def _reloadconfig(signum, frame):
    '''
    Reload configuration file.
    SIGHUP handler.
    '''
    global AceConfig

    logger = logging.getLogger('reloadconfig')
    reload(aceconfig)
    from aceconfig import AceConfig
    logger.info('Config reloaded')

# setting signal handlers
try:
    gevent.signal(signal.SIGHUP, _reloadconfig)
    gevent.signal(signal.SIGTERM, shutdown)
except AttributeError:
    # not available on Windows
    pass

if AceConfig.vlcuse:
    if AceConfig.vlcspawn:
        AceStuff.vlcProc = AceConfig.vlccmd.split()
        if spawnVLC(AceStuff.vlcProc, 1) and connectVLC():
            logger.info("VLC spawned with pid " + str(AceStuff.vlc.pid))
        else:
            logger.error("Cannot spawn VLC!")
            quit(1)
    else:
        if not connectVLC():
            clean_proc()
            quit(1);

if AceConfig.acespawn:
    if AceConfig.osplatform == 'Windows':
        import _winreg
        import os.path
        AceStuff.aceProc = ""
    else:
        AceStuff.aceProc = AceConfig.acecmd.split()
    if spawnAce(AceStuff.aceProc, 1):
        # could be redefined internally
        if AceConfig.acespawn:
            logger.info("Ace Stream spawned with pid " + str(AceStuff.ace.pid))
    else:
        logger.error("Cannot spawn Ace Stream!")
        clean_proc()
        quit(1)


try:
    logger.info("Using gevent %s" % gevent.__version__)
    if AceConfig.vlcuse:
         logger.info("Using VLC %s" % AceStuff.vlcclient._vlcver)
    logger.info("Server started.")
    while True:
        if AceConfig.vlcspawn and AceConfig.vlcuse:
            if not isRunning(AceStuff.vlc):
                del AceStuff.vlc
                if spawnVLC(AceStuff.vlcProc, 1) and connectVLC():
                    logger.info("VLC died, respawned it with pid " + str(AceStuff.vlc.pid))
                else:
                    logger.error("Cannot spawn VLC!")
                    clean_proc()
                    quit(1)
        if AceConfig.acespawn:
            if not isRunning(AceStuff.ace):
                del AceStuff.ace
                if spawnAce(AceStuff.aceProc, 1):
                    logger.info("Ace Stream died, respawned it with pid " + str(AceStuff.ace.pid))
                else:
                    logger.error("Cannot spawn Ace Stream!")
                    clean_proc()
                    quit(1)
        # Return to our server tasks
        server.handle_request()
except (KeyboardInterrupt, SystemExit):
    shutdown()