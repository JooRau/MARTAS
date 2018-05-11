from twisted.internet import reactor
from twisted.web.server import Site
from twisted.web.static import File
from twisted.internet import reactor
import sys

webpath = sys.argv[1]
webport = int(sys.argv[2])
resource = File(webpath)
factory = Site(resource)
reactor.listenTCP(webport,factory)
reactor.run()
