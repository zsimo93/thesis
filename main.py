import sys, os
import threading

def checkMaster():
    role = os.environ.get("TH_ROLE")
    return role == "MASTER"

def setup(ip):
    from pymongo import MongoClient

    config = {'_id': 'foo',
              'version': 1,
              'members': [
                  {'_id': 0, 'host': ip + ':27017',
                   "votes": 1, "priority": 1}]}
    c = MongoClient(host=ip, port=27017)
    c.admin.command("replSetInitiate", config)

def createNodeMaster(ip):
    from core.databaseMongo import mainDB
    name = os.environ["TH_NODENAME"]
    node = {
        '_id': name,
        'name': name,
        'ip': ip,
        'role': 'MASTER',
        'architecture': os.environ.get("TH_ARCH"),
        'replica_id': 0
    }

    db = mainDB.db
    n = db.nodes
    nrs = db.nodesRes
    n.insert_one(node)

    info = {
        '_id': name,
        'cpu': '',
        'memory': ''}
    nrs.insert_one(info)

def execute():
    from core.APIGateway import run
    from core.heartbeat import heartbeatMain
    from core.databaseMongo.localDB import removeTimedOutCont

    threading.Thread(target=removeTimedOutCont).start()
    heartbeatMain.startHeartBeat()
    run(False)


if checkMaster():
    if len(sys.argv) == 1:
        sys.exit("run the script with the IP of the localnode")
    ip = sys.argv[1]
    os.environ["TH_MASTERIP"] = ip
    setup(ip)
    createNodeMaster(ip)
    from core.gridFS.files import removeChunks

    # thread for cleaning up chunks table for user data
    # removed after TTL
    threading.Thread(target=removeChunks).start()

execute()
