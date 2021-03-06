import hbMaster, hbNode
from threading import Thread
import os

def checkMaster():
    role = os.environ.get("TH_ROLE")
    return role == "MASTER"

def startHeartBeat():
    if checkMaster():
        Thread(target=hbMaster.start).start()
    else:
        Thread(target=hbNode.start).start()
