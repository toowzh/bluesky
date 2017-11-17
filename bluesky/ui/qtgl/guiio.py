''' I/O Client implementation for the QtGL gui. '''
try:
    from PyQt5.QtCore import QTimer

except ImportError:
    from PyQt4.QtCore import QTimer

import numpy as np

from bluesky.io import Client
from bluesky.tools import Signal
from bluesky.tools.aero import ft

# Globals
UPDATE_ALL = ['POLY', 'TRAILS', 'CUSTWPT', 'PANZOOM', 'ECHOTEXT']

# Signals
actnodedata_changed = Signal()
nodes_changed       = Signal()
event_received      = Signal()
stream_received     = Signal()

class nodeData(object):
    def __init__(self):
        # Stack window
        self.echo_text     = ''

        # Display pan and zoom
        self.pan           = (0.0, 0.0)
        self.zoom          = 1.0

        # Per-scenario data
        self.clear_scen_data()

    def clear_scen_data(self):
        # Clear all scenario-specific data for sender node
        self.polynames = dict()
        self.polydata  = np.array([], dtype=np.float32)
        self.custwplbl = ''
        self.custwplat = np.array([], dtype=np.float32)
        self.custwplon = np.array([], dtype=np.float32)

        # Filteralt settings
        self.filteralt = False

        # Create trail data
        self.traillat0 = []
        self.traillon0 = []
        self.traillat1 = []
        self.traillon1 = []

        # Reset transition level
        self.translvl = 4500.*ft

        # Display flags
        self.show_map      = True
        self.show_coast    = True
        self.show_traf     = True
        self.show_pz       = False
        self.show_fir      = True
        self.show_lbl      = 2
        self.show_wpt      = 1
        self.show_apt      = 1
        self.ssd_all       = False
        self.ssd_conflicts = False
        self.ssd_ownship   = set()


    def panzoom(self, pan=None, zoom=None, absolute=True):
        if pan:
            self.pan  = pan
        if zoom:
            self.zoom = zoom

    def update_poly_data(self, name, data=None):
        if name in self.polynames:
            # We're either updating a polygon, or deleting it. In both cases
            # we remove the current one.
            self.polydata = np.delete(self.polydata, list(range(*self.polynames[name])))
            del self.polynames[name]

        # Break up polyline list of (lat,lon)s into separate line segments
        if data is not None:
            self.polynames[name] = (len(self.polydata), 2 * len(data))
            newbuf = np.empty(2 * len(data), dtype=np.float32)
            newbuf[0::4]   = data[0::2]  # lat
            newbuf[1::4]   = data[1::2]  # lon
            newbuf[2:-2:4] = data[2::2]  # lat
            newbuf[3:-3:4] = data[3::2]  # lon
            newbuf[-2:]    = data[0:2]
            self.polydata  = np.append(self.polydata, newbuf)

    def defwpt(self, name, lat, lon):
        self.custwplbl += name.ljust(5)
        self.custwplat = np.append(self.custwplat, np.float32(lat))
        self.custwplon = np.append(self.custwplon, np.float32(lon))

    def setflag(self, flag, args):
        # Switch/toggle/cycle radar screen features e.g. from SWRAD command
        if flag == 'SYM':
            # For now only toggle PZ
            self.show_pz = not self.show_pz
        # Coastlines
        elif flag == 'GEO':
            self.show_coast = not self.show_coast

        # FIR boundaries
        elif flag == 'FIR':
            self.show_fir = not self.show_fir

        # Airport: 0 = None, 1 = Large, 2= All
        elif flag == 'APT':
            self.show_apt = not self.show_apt

        # Waypoint: 0 = None, 1 = VOR, 2 = also WPT, 3 = Also terminal area wpts
        elif flag == 'VOR' or flag == 'WPT' or flag == 'WP' or flag == 'NAV':
            self.show_wpt = not self.show_wpt

        # Satellite image background on/off
        elif flag == 'SAT':
            self.show_map = not self.show_map

        # Satellite image background on/off
        elif flag == 'TRAF':
            self.show_traf = not self.show_traf

        elif flag == 'SSD':
            self.show_ssd(args)

        elif flag == 'FILTERALT':
            # First argument is an on/off flag
            if args[0]:
                self.filteralt = args[1:]
            else:
                self.filteralt = False

    def echo(self, text):
        self.echo_text += ('\n' + text)

    def show_ssd(self, arg):
        if 'ALL' in arg:
            self.ssd_all      = True
            self.ssd_conflicts = False
        elif 'CONFLICTS' in arg:
            self.ssd_all      = False
            self.ssd_conflicts = True
        elif 'OFF' in arg:
            self.ssd_all      = False
            self.ssd_conflicts = False
            self.ssd_ownship = set()
        else:
            remove = self.ssd_ownship.intersection(arg)
            self.ssd_ownship = self.ssd_ownship.union(arg) - remove

class GuiClient(Client):
    default_data = nodeData()

    def __init__(self):
        super(GuiClient, self).__init__()
        self.act = b''
        self.nodedata = dict()
        self.timer = None

    def event(self, name, data, sender_id):
        sender_data = self.nodedata.get(sender_id)
        data_changed = []
        if not sender_data:
            sender_data = self.nodedata[sender_id] = nodeData()
        if name == b'RESET':
            sender_data.clear_scen_data()
            data_changed = list(UPDATE_ALL)
        elif name == b'POLY':
            sender_data.update_poly_data(**data)
            data_changed.append('POLY')
        elif name == b'DEFWPT':
            sender_data.defwpt(**data)
            data_changed.append('CUSTWPT')
        elif name == b'DISPLAYFLAG':
            sender_data.setflag(**data)
        elif name == b'ECHO':
            sender_data.echo(data)
            data_changed.append('ECHOTEXT')
        elif name == b'PANZOOM':
            sender_data.panzoom(**data)
            data_changed.append('PANZOOM')
        else:
            event_received.emit(name, data, sender_id)

        if sender_id == self.act and data_changed:
            actnodedata_changed.emit(sender_id, sender_data, data_changed)

    def stream(self, name, data, sender_id):
        stream_received.emit(name, data, sender_id)

    def nodes_changed(self, data):
        node_id = b''
        for node_ids in data.values():
            for node_id in node_ids:
                if node_id not in self.nodedata:
                    self.nodedata[node_id] = nodeData()

        nodes_changed.emit(data)
        # If this is the first known node, select it as active node
        if not self.act and node_id:
            self.actnode(node_id)

    def actnode(self, newact=None):
        if newact is not None:
            # Unsubscribe from previous node, subscribe to new one.
            if self.act:
                self.unsubscribe(b'ACDATA', self.act)
            self.subscribe(b'ACDATA', newact)

            self.act = newact
            actdata = self.nodedata.get(newact)
            actnodedata_changed.emit(newact, actdata, UPDATE_ALL)
        return self.act

    def send_event(self, name, data=None, target=None):
        super(GuiClient, self).send_event(name, data, target or self.act)

    def get_nodedata(self, nodeid=None):
        return self.nodedata.get(nodeid or self.act, self.default_data)

    def init(self):
        self.connect()
        self.timer = QTimer()
        self.timer.timeout.connect(self.receive)
        self.timer.start(20)
        self.subscribe(b'SIMINFO')

# Globals
_client = GuiClient()

actnode = _client.actnode
send_event = _client.send_event
get_nodedata = _client.get_nodedata
get_hostid = _client.get_hostid
init = _client.init

def sender():
    return _client.sender_id
