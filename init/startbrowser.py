import subprocess
import urllib
import time

webserver_ready = False

while not webserver_ready:
    webserver_ready = True
    try:
        urllib.urlopen('http://127.0.0.1:8080')
    except:
        webserver_ready = False
        time.sleep(0.1)

subprocess.Popen(['midori','-e','Fullscreen','-e','TabCloseOther','-a','127.0.0.1:8080'])
