#WebScraping
#import requests
import urllib2
from bs4 import BeautifulSoup

class HTTPHandler():
    server = "http://185.53.131.158:8000"

    queryList = [
        'daddylive', 'morningstreams', 'overtakefans'
    ]

    channels = [
        ('DanishBay' ,'88994d418b6cf4b6052dce047abcb71110b0e7e7', 'http://185.53.131.158:8000/pid/88994d418b6cf4b6052dce047abcb71110b0e7e7/Danishbay.mp4')
    ]

    def findPIDList(self):
        for q in self.queryList:
            URL = "https://acestreamsearch.net/en/?q=" + str(q)
            page = urllib2.Request(URL)
            response = urllib2.urlopen(page)
            content = response.read()
            soup = BeautifulSoup(content, 'lxml')
            results = soup.find_all('li', class_="list-group-item")
            for li in results:
                pid = li.span.get("data-copy")
                name = li.a.text
                self.channels.append((name, pid, self.server + "/pid/" + pid + "/" + name.replace(" ", "") + ".mp4"))

    def findPID(self, q):
        URL = 'https://acestreamsearch.net/en/?q=' + q
        page = urllib2.Request(URL)
        response = urllib2.urlopen(page)
        content = response.read()
        soup = BeautifulSoup(content, 'lxml')
        span = soup.find_all('span', class_="pull-right glyphicon glyphicon-copy js-tooltip js-copy")
        if span:
            for pid in span:
                if pid:
                    # Implement VLC check
                    return self.server.geturl() + "/pid/" + pid.get("data-copy") + "/" + q + ".mp4"
                else:
                    return span
        else:
            return "No channel available"

    def generateM3U(self):
        strPlaylist = "#EXTM3U \n"
        for channel in self.channels:
            strElement = "#EXTINF:0," + channel[0] + ".mp4 \n"
            strElement += "#EXTVLCOPT:network-caching=1000 \n"
            strElement += str(channel[2]) + "\n"
            strPlaylist += strElement
        hs = open("playlist.m3u", 'w')
        hs.write(strPlaylist)


Parser = HTTPHandler()
#Parser.findPIDList()
#Parser.generateM3U()

#print(Parser.channels)
print(Parser.findPID("bein"))