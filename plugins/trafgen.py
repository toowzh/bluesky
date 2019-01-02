"""
Airspace Design Contest Scenario Generator:

Draw circles and runways in use
Generate traffic at edges and at airports
Make sure scenario can be saved

"""


from bluesky import stack,traf,sim,tools,navdb  #, settings, navdb, traf, sim, scr, tools
from trafgenclasses import Source, setcircle
from bluesky.tools.position import txt2pos
from bluesky.tools.geo import kwikpos
#from bluesky.tools import areafilter
#from bluesky.tools.aero import vtas2cas,ft
#from bluesky.tools.misc import degto180


import numpy as np

# Default values
ctrlat = 52.6
ctrlon = 5.4
radius = 230.


def init_plugin():
    print("Initialising contest scenario generator")

    # Create an empty geovector list
    reset()

    # Configuration parameters
    config = {
        # The name of your plugin
        'plugin_name'      : 'TRAFGEN',
        'plugin_type'      : 'sim',
        'update_interval'  :  0.1,

        # The update function is called after traffic is updated.
        'update':          update,

        # The preupdate function is called before traffic is updated. Use this
        #'preupdate':       preupdate,

        # Reset contest
        'reset':         reset
        }

    # Add two commands: GEOVECTOR to define a geovector for an area
    stackfunctions = {
        # Starting contest traffic generation
        'TRAFGEN': [
            'TRAFGEN [location],cmd,[arg, arg, ...]',
            'string',
            trafgencmd,
            'CONTEST command']
        }

    # init_plugin() should always return these two dicts.

    return config, stackfunctions

def reset():
    # Contest global variables
    global ctrlat,ctrlon,radius,dtsegment,drains,sources,rwsdep,rwsarr

    # Set default parameters for spawning circle

    swcircle = False
    ctrlat = 52.6  # [deg]
    ctrlon = 5.4  # [deg]
    radius = 230.0  # [nm]

    # Draw circle
    stack.stack("CIRCLE SPAWN," + str(ctrlat) + "," + str(ctrlon) + "," + str(radius))

    # Average generation interval in [s] per segment
    dtsegment = 12 * [1.0]

    # drains: dictionary of drains
    sources     = dict([])
    drains      = dict([])

    return


### Periodic update functions that are called by the simulation. You can replace
### this by anything, so long as you communicate this in init_plugin

#def preupdate(): # To be safe preupdate is used iso update
#    pass
#    return


def update(): # Update all sources and drain
    for src in sources:
        sources[src].update()

    return

### Other functions of your plug-in
def trafgencmd(cmdline):
    global ctrlat,ctrlon,radius,dtsegment,drains,sources,rwsdep,rwsarr

    cmd,args = splitline(cmdline)

    #print("TRAFGEN: cmd,args=",cmd,args)

    if cmd=="CIRCLE" or cmd=="CIRC":

        # Draw circle
        try:
            swcircle = True
            ctrlat = float(args[0])
            ctrlon = float(args[1])
            radius = float(args[2])
            setcircle(ctrlat, ctrlon, radius)
        except:
            return False,'TRAFGEN ERROR while reading CIRCLE command arguments (lat,lon,radius):'+str(args)
        stack.stack("DEL SPAWN")
        stack.stack("CIRCLE SPAWN," + str(ctrlat) + "," + str(ctrlon) + "," + str(radius))

    elif cmd=="SRC" or cmd == 'SOURCE': # Define streams by source, give destinations
        name = args[0].upper()
        cmd = args[1].upper()
        cmdargs = args[2:]
        if name not in sources:
            success,posobj = txt2pos(name,ctrlat,ctrlon)
            if success:
                aptlat, aptlon = posobj.lat, posobj.lon
                sources[name] = Source(name,cmd,cmdargs)
        else:
            aptlat,aptlon = sources[name].lat,sources[name].lat
            success = True

        if success:
            if cmd=="RUNWAY" or cmd=="RWY":
                sources[name].addrunways(cmdargs)
                errormsg = drawrwy(name,cmdargs,aptlat,aptlon,drawdeprwy)
                if len(errormsg) > 0:
                    return False, "TRAFGEN SRC RWY ERROR" + " ".join(errormsg) + " NOT FOUND"

            elif cmd=="DEST":
                sources[name].adddest(cmdargs)
            elif cmd=="FLOW":
                sources[name].setflow(cmdargs[0])
            elif cmd=="TYPES" or cmd=="TYPE":
                sources[name].addactypes(cmdargs)
        else:
            return False,"TRAFGEN SRC ERROR "+name+" NOT FOUND"

    elif cmd=="DRN" or cmd=="DRAIN":
        name = args[0].upper()
        cmd = args[1].upper()
        cmdargs = args[2:]
        if name not in drains:
            success, posobj = txt2pos(name, ctrlat, ctrlon)
            if success:
                drains[name] = [name,posobj.lat,posobj.lon]
        else:
            success = True


        if success:
            if cmd == "RUNWAY" or cmd == "RWY":
                aptlat, aptlon = drains[name][1:3]
                errormsg = drawrwy(name,cmdargs,aptlat,aptlon,drawapprwy)
                if len(errormsg) > 0:
                    return False, "TRAFGEN DRN RWY ERROR" + " ".join(errormsg) + " NOT FOUND"
        else:
            return False, "TRAFGEN DRN ERROR " + name + " NOT FOUND"

    return True

def splitline(rawline):
    # Interpet string like a command with arguments
    # Replace multiple spaces by one space

    line = rawline.strip().upper()
    if line.count("#")>=1:
        icomment = line.index("#")
        line  = line[:icomment]

    while line.count("  ") > 0:
        line = line.replace("  ", " ")

    # and remove spaces around commas
    while line.count(", ") > 0:
        line = line.replace(", ", ",")

    while line.count(" ,") > 0:
        line = line.replace(" ,", ",")

    # Replace remaining spaces, which are separators, by comma
    line = line.strip().replace(" ",",")

    # Split using commas
    args = line.split(",")
    if len(args)>=1:
        cmd = args[0]
    else:
        cmd = ""
    return cmd,args[1:]

def drawrwy(name,cmdargs,aptlat,aptlon,drawfunction):
    errormsg = []

    for rwy in cmdargs:
        if rwy[0] == "R":
            success, rwyposobj = txt2pos(name + "/" + rwy, aptlat, aptlon)
        else:
            success, rwyposobj = txt2pos(name + "/RW" + rwy, aptlat, aptlon)
        if success:
            rwydigits = rwy.lstrip("RWY").lstrip("RW")

            # Look up threshold position
            try:
                rwyhdg = navdb.rwythresholds[name][rwydigits][2]
            except:
                errormsg.append(name + "/RW" + rwydigits)

            drawfunction(name, rwy, rwyposobj.lat, rwyposobj.lon, rwyhdg)
        else:
            errormsg.append(name + "/" + rwy)
    return errormsg


def drawapprwy(apt,rwy,rwylat,rwylon,rwyhdg):
    # Draw approach ILS arrow
    Lapp  =  7. # [nm] length of approach path drawn
    phi   =  5. # [deg] angle of half the arrow

    # Calculate arrow (T = Threshold runway):
    #                               /------------- L   (left)
    #                 /-----------/              /
    #   T -------------------------------------- A    (approach)
    #                 \-----------\              \
    #                              \--------------R    (right)
    #

    applat,applon     = kwikpos(rwylat,rwylon,(rwyhdg+180)%360.,Lapp)
    rightlat,rightlon = kwikpos(rwylat,rwylon,(rwyhdg+180-phi)%360,Lapp*1.1)
    leftlat,leftlon   = kwikpos(rwylat,rwylon,(rwyhdg+180+phi)%360,Lapp*1.1)

    # Make arguments for POLYLINE command
    T = str(rwylat)+","+str(rwylon)
    A = str(applat)+","+str(applon)
    L = str(leftlat)+","+str(leftlon)
    R = str(rightlat)+","+str(rightlon)

    stack.stack("LINE "+apt+rwy+"-A1,"+",".join([T,A]))
    stack.stack("LINE "+apt+rwy+"-A2,"+",".join([A,L]))
    stack.stack("LINE "+apt+rwy+"-A3,"+",".join([L,T]))
    stack.stack("LINE "+apt+rwy+"-A4,"+",".join([T,R]))
    stack.stack("LINE "+apt+rwy+"-A5,"+",".join([R,A]))

    return

def drawdeprwy(apt,rwy,rwylat,rwylon,rwyhdg):
    # Draw approach ILS arrow
    Ldep  =  5. # [nm] length of approach path drawn
    phi   =  3. # [deg] angle of half the arrow

    # Calculate arrow (T = Threshold runway):
    #                               /------------- L   (left)
    #                 /-----------/              /
    #   T -------------------------------------- A    (approach)
    #                 \-----------\              \
    #                              \--------------R    (right)
    #

    deplat,deplon     = kwikpos(rwylat,rwylon,rwyhdg%360.,Ldep*1.1)
    rightlat,rightlon = kwikpos(rwylat,rwylon,(rwyhdg+phi)%360,Ldep)
    leftlat,leftlon   = kwikpos(rwylat,rwylon,(rwyhdg-phi)%360,Ldep)

    # Make arguments for POLYLINE command
    T = str(rwylat)+","+str(rwylon)
    D = str(deplat)+","+str(deplon)
    L = str(leftlat)+","+str(leftlon)
    R = str(rightlat)+","+str(rightlon)

    stack.stack("LINE "+apt+rwy+"-D1,"+",".join([T,D]))
    stack.stack("LINE "+apt+rwy+"-D2,"+",".join([L,D]))
    stack.stack("LINE "+apt+rwy+"-D4,"+",".join([D,R]))

    return