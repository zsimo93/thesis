from core.databaseMongo.sequencesDB import getSequence
from core.databaseMongo import actionsDB, nodesDB
from requests import ConnectionError
from invokers import NodeInvoker, AWSInvoker, InvokerThread
from threading import Thread
import time
from datetime import datetime
import json
import traceback, sys
from copy import deepcopy


def giveMeHandler(param, default, configs, name, sessionID, optimise, log):
    if not actionsDB.availableActionName(name):
        return ActionExecutionHandler(default, configs, name,
                                      sessionID, param, log)
    else:
        return SeqExecutionHandler(default, configs, name,
                                   sessionID, param, optimise, log)


def createAction(name, default, configs, myID, map, timeout,
                 language, cloud, next, contTag, containerName):
    action = {"name": name,
              'id': myID,  # None if single action execution
              "map": map,
              "contTag": contTag}  # None if single action execution

    if configs and name in configs:
        conf = configs[name]
    else:
        conf = default
    action["memory"] = conf["memory"]

    if not myID:
        # single action execution. Retrieve information.
        fromDB = actionsDB.getAction(name)
        action["timeout"] = fromDB['timeout']
        action["language"] = fromDB['language']
        action["cloud"] = fromDB['cloud']
        action["contTag"] = fromDB['contTag']
        try:
            action["containerName"] = fromDB["containerName"]
        except KeyError:
            pass
    else:
        action["timeout"] = timeout
        action["language"] = language
        action["cloud"] = cloud
        action["next"] = next
        action["containerName"] = containerName

    if action["cloud"]:
        action["actionClass"] = conf["actionClass"]

    return action

def calcBlockMemory(actList):
    memory = 0
    actNameList = []
    for a in actList:
        if a["name"] not in actNameList:
            actNameList.append(a["name"])
            memory += a["memory"]
    return memory


class NoResourceException(Exception):
    pass

class ActionExecutionHandler:
    def __init__(self, default, configs, name, sessionID, param, nlog,
                 myID=None, map=None, next=None, timeout=None,
                 language=None, cloud=None, contTag=None, containerName=None):

        self.param = self.prepareInput(map, param)
        self.sessionID = sessionID
        self.action = createAction(name, default, configs, myID, map, timeout,
                                   language, cloud, next, contTag, containerName)
        self.nlog = nlog
        self.logList = []

    def prepareInput(self, map, param):
        inParam = {}
        if not map:
            return param
        for newkey in map:
            s = map[newkey]
            list = s.split("/")
            refId = list[0]
            value = list[1]
            inParam[newkey] = param[refId][value]
        return inParam

    def sortedCPU(self, avList):
        # sort the available nodes per cpu usage
        return sorted(avList, key=lambda node: node['cpu'])

    def sortedMem(self, avList):
        # sort the available nodes per free memory
        return sorted(avList, key=lambda node: node['memory'])

    def chooseActionNode(self, action):
        begin = time.time()
        if action["cloud"] == "2":
            # cloud execution forced
            elapsed = time.time() - begin
            self.log("Time to choose location: " + repr(elapsed))
            return ("_cloud", AWSInvoker())

        # Select the node with more free cpu and enought memory
        req_mem = long(action["memory"]) * 1000000
        nodesRes = nodesDB.allRes()

        selected = None
        sortedNodes = self.sortedCPU(nodesRes)
        # sortedNodes = self.sortedMem(nodesRes)
        #   will take the node with less free memory
        #   that fit the requested memory

        attempt = 0
        while attempt < 3:
            # 3 attempts of finding a node with enought memory.
            # if no node and action no AWS execution, wait and retry later.

            for node in sortedNodes:
                if node["cpu"] > 75:
                    self.log("Selecting node - Jumping node %s because full" % (node["_id"]))
                    continue
                if req_mem < node['memory']:
                    # most free cpu and enought memory
                    selected = node
                    elapsed = time.time() - begin
                    self.log("Time to choose location: " + repr(elapsed))
                    return (selected["_id"],
                            NodeInvoker(nodesDB.getNode(selected['_id'])['ip']))

            if not selected:
                if action["cloud"] == "1":
                    elapsed = time.time() - begin
                    self.log("Time to choose location: " + repr(elapsed))
                    return ("_cloud", AWSInvoker())
                else:
                    time.sleep(0.5)
                    attempt += 1
                    continue

        raise NoResourceException("Not enought memory resources in the " +
                                  "system to execute " + action["name"] +
                                  " using " + str(action["memory"]) + "MB")

    def startThreaded(self):
        return Thread(target=self.start)

    def start(self):
        i = 0
        while(i < 3):
            try:
                name, invoker = self.chooseActionNode(self.action)
                request = {
                    "type": "action",
                    "sessionID": self.sessionID,
                    "param": self.param,
                    "action": self.action
                }
                begin = time.time()
                text, status_code = invoker.startExecution(request, self.nlog)
                elapsed = time.time() - begin
                if status_code >= 400:
                    self.ret = ({"error": text}, 500)
                    self.log("ERROR in remote execution")
                    self.logList.append(text)
                    return self.ret
                try:
                    self.ret = (json.loads(text), 200)
                except TypeError:
                    self.ret = (text, 200)
                if self.nlog:
                    self.logList += self.ret[0]["__log__"]
                    del self.ret[0]["__log__"]
                self.log("EXECUTED in node " + name + " - time:" + repr(elapsed))
                self.ret = self.ret
                return self.ret
            except ConnectionError:
                self.log("Deleting node %s for not responding" % name)
                # nodesDB.deleteNode(name)
            except Exception, e:
                self.log("Exception in local")
                print '-' * 60
                traceback.print_exc(file=sys.stdout)
                print '-' * 60
                self.ret = ({"error": str(e)}, 500)
                return self.ret
            else:
                break

        self.ret = ({"error": "2 nodes failed."}, 500)
        return self.ret

    def log(self, message):
        ts = datetime.now().isoformat()
        actID = self.action["id"] if self.action["id"] else ""
        id = "ACTION " + actID + " " + self.action['name']
        logStr = ts + " - " + id + ": " + message
        print logStr
        self.logList.append(logStr)

class AsActionExecutionHandler(ActionExecutionHandler):
    # This classis used when the "action" json is already formed.
    #   in case of single execution in block and parallel
    def __init__(self, sessionID, action, param, nlog):
        self.param = self.prepareInput(action["map"], param)
        self.sessionID = sessionID
        self.action = action
        self.nlog = nlog
        self.logList = []

class SeqExecutionHandler:
    def __init__(self, default, configs, name, sessionID, param, optimise, nlog):
        self.param = param
        self.sessionID = sessionID
        self.name = name
        self.default = default
        self.configs = configs
        self.nlog = nlog
        self.logList = []
        s = getSequence(name)
        if not optimise:
            self.log("Running without optimisations")
            self.sequence = s["execSeq_noopt"]
        else:
            self.sequence = s["execSeq"]
        self.outMap = s["outMapFLAT"]
        self.results = {}

    def finalizeResult(self):
        """
        Compose the results based on the out Map

        Return the result.
        """
        res = {}
        for k in self.outMap:
            v = self.outMap[k]
            rid, p = v.split("/")
            res[k] = self.results[rid][p]
        return (res, 200)

    def start(self):
        self.log("Running")
        for a in self.sequence:
            p = {}
            p["param"] = self.param
            param = dict(p, **self.results)
            if a["type"] == "action":
                handler = ActionExecutionHandler(self.default, self.configs,
                                                 a["name"], self.sessionID,
                                                 param, self.nlog, myID=a["id"], map=a["map"],
                                                 timeout=a["timeout"],
                                                 language=a["language"],
                                                 cloud=a["cloud"], next=a["next"],
                                                 contTag=a["contTag"],
                                                 containerName=a["containerName"])

                try:
                    r, status_code = handler.start()
                    self.logList += handler.logList
                    if status_code >= 400:
                        self.ret = (r, 500)
                        return self.ret
                    else:
                        self.results[handler.action["id"]] = r
                        continue

                except Exception as e:
                    self.log("Local Exception")
                    print '-' * 60
                    traceback.print_exc(file=sys.stdout)
                    print '-' * 60
                    return {"error": str(e)}, 500

            if a["type"] == "parallel":
                actList = []
                for act in a["list"]:
                    if a["type"] == "action":
                        actList.append(a)
                    else:
                        for b in a["list"]:
                            actList.append(b)

                handler = ParallelExecutionHandler(self.default, self.configs,
                                                   self.sessionID, a["list"], param, self.nlog)
            else:
                # a["type"] == "block"
                handler = BlockExecutionHandler(self.default, self.configs,
                                                self.sessionID, a["list"], param, self.nlog)

            try:
                r, status_code = handler.start()
                self.logList += handler.logList
                if status_code >= 400:
                    self.ret = (r, 500)
                    return self.ret
                else:
                    for key in r:
                        self.results[key] = r[key]

            except Exception as e:
                self.log("Local Exception")
                print '-' * 60
                traceback.print_exc(file=sys.stdout)
                print '-' * 60
                return {"error": str(e)}, 500
        self.log("END")
        return self.finalizeResult()

    def log(self, message):
        ts = datetime.now().isoformat()
        id = "SEQUENCE " + self.name
        logStr = ts + " - " + id + ": " + message
        print logStr
        self.logList.append(logStr)


class BlockExecutionHandler(ActionExecutionHandler):
    def __init__(self, default, configs, sessionID, list, param, nlog):
        self.default = default
        self.configs = configs
        self.sessionID = sessionID
        self.ids = []
        self.nlog = nlog
        self.logList = []
        self.param = param

        self.results = {}

        self.blockList = []
        for a in list:
            ar = createAction(a["name"], self.default, self.configs,
                              a["id"], a["map"], a["timeout"],
                              a["language"], a["cloud"], a["next"],
                              a["contTag"], a["containerName"])
            self.ids.append(a["id"])
            self.blockList.append(ar)

    def prepareBlockInput(self, actionList):
        inParam = {}
        listId = [a["id"] for a in actionList]
        for action in actionList:
            for newkey in action["map"]:
                s = action["map"][newkey]
                refId = s.split("/")[0]
                if refId not in listId:
                    if refId not in inParam:
                        inParam[refId] = self.param[refId]
        return inParam

    def chooseBlockNode(self, actList):
        memory = calcBlockMemory(actList) * 1000000
        nodesRes = nodesDB.allRes()
        # sortedNodes = self.sortedMem(nodesRes)  take less memory that fits
        sortedNodes = self.sortedCPU(nodesRes)
        for node in sortedNodes:
            if node["cpu"] > 75:
                self.log("Selecting node - Jumping node %s because full" % (node["_id"]))
                continue
            if memory < node['memory']:
                # most free cpu and enought memory
                return node["_id"], NodeInvoker(nodesDB.getNode(node['_id'])['ip'])

        return None, None

    def start(self):
        self.log("Executing block with actions: " + str(self.ids))

        while self.blockList:
            invoker = None

            if len(self.blockList) == 1:
                # one action left in the block. Execute as single action
                param = self.prepareBlockInput(self.blockList)
                h = AsActionExecutionHandler(self.sessionID,
                                             self.blockList[0],
                                             param, self.nlog)
                text, code = h.start()
                try:
                    retJson = json.loads(text)
                except TypeError:
                    retJson = text
                self.logList += h.logList
                self.blockList = []
                self.ret = retJson, code
                if code >= 400:
                        self.log("ERROR")
                        self.ret = {"error": retJson}, 500
                        return self.ret

                self.results[h.action["id"]] = retJson

                self.ret = self.results, 200
                return self.ret

            else:
                name, invoker = self.chooseBlockNode(self.blockList)
                if invoker:
                    # can execute the full block in a node. Do it!
                    param = self.prepareBlockInput(self.blockList)
                    payload = {
                        "type": "block",
                        "sessionID": self.sessionID,
                        "param": param,
                        "block": self.blockList
                    }
                    begin = time.time()
                    text, code = invoker.startExecution(payload, self.nlog)
                    elapsed = time.time() - begin
                    # TODO Handle node disconnection
                    if code >= 400:
                        self.log("ERROR " + text)
                        self.ret = {"error": text}, 500
                        return self.ret

                    self.blockList = []

                    try:
                        retJson = json.loads(text)
                    except TypeError:
                        retJson = text
                    if self.nlog:
                        self.logList += retJson["__log__"]
                        del retJson["__log__"]
                    self.log("EXECUTED " + str(self.ids) + " on node " + name + " in " + repr(elapsed))

                    for k in retJson:
                        self.results[k] = retJson[k]
                    self.ret = self.results, 200
                    return self.ret

                else:
                    # cannot execute the full block. Try removing actions from
                    # end of block one at a time.
                    i = 0
                    while not invoker:
                        i -= 1
                        if len(self.blockList[:i]) == 1:
                            # if just one action, execute as single action.
                            param = self.prepareBlockInput([self.blockList[0]])
                            h = AsActionExecutionHandler(self.sessionID,
                                                         self.blockList[0],
                                                         param, self.nlog)
                            text, code = h.start()
                            try:
                                retJson = json.loads(text)
                            except TypeError:
                                retJson = text
                            self.logList += h.logList
                            if code >= 400:
                                self.ret = {"error": retJson}, 500
                                self.log("ERROR")
                                return self.ret
                            self.results[h.action["id"]] = retJson
                            self.param[h.action["id"]] = retJson

                            self.ids = self.ids[i:]
                            self.blockList = self.blockList[i:]
                            singleCase = True
                            break
                        else:
                            name, invoker = self.chooseBlockNode(self.blockList[:i])
                            singleCase = False

                    if not singleCase:
                        # execute the sub-block selected and reiterate with
                        # remaining actions in block
                        param = self.prepareBlockInput(self.blockList[:i])
                        payload = {
                            "type": "block",
                            "sessionID": self.sessionID,
                            "param": param,
                            "block": self.blockList[:i]
                        }
                        begin = time.time()
                        text, code = invoker.startExecution(payload, self.nlog)
                        elapsed = time.time() - begin
                        # TODO Handle node disconnection
                        if code >= 400:
                            self.log("ERROR " + text)
                            self.ret = {"error": text}, 500
                            return self.ret

                        try:
                            retJson = json.loads(text)
                        except TypeError:
                            retJson = text

                        if self.nlog:
                            self.logList += retJson["__log__"]
                            del retJson["__log__"]

                        for k in retJson:
                            self.results[k] = retJson[k]
                            self.param[k] = retJson[k]

                        self.log("EXECUTED " + str(self.ids[:i]) + " on node " + name + " in " + repr(elapsed))
                        self.blockList = self.blockList[i:]
                        self.ids = self.ids[i:]

        self.log("END")
        self.ret = "OK", 200
        return self.ret

    def log(self, message):
        ts = datetime.now().isoformat()
        id = "BLOCK"
        logStr = ts + " - " + id + ": " + message
        print logStr
        self.logList.append(logStr)

class AsBlockExecutionHandler(BlockExecutionHandler):
    def __init__(self, sessionID, blockList, param, nlog, ids, memory):
        self.sessionID = sessionID
        self.ids = ids
        self.nlog = nlog
        self.logList = []
        self.param = param

        self.results = {}
        self.blockList = blockList
        self.memory = memory


class ParallelExecutionHandler(BlockExecutionHandler):
    def __init__(self, default, configs, sessionID, plist, param, nlog):
        self.default = default
        self.configs = configs
        self.sessionID = sessionID
        self.param = param
        self.results = {}
        self.nlog = nlog
        self.logList = []

        self.actList = []
        for a in plist:
            if a["type"] == "action":
                h = createAction(a["name"], self.default, self.configs,
                                 a["id"], a["map"], a["timeout"],
                                 a["language"], a["cloud"], a["next"],
                                 a["contTag"], a["containerName"])
                h["type"] = "action"

            else:
                h = {}
                blockList = []
                ids = []
                for b in a["list"]:
                    ar = createAction(b["name"], self.default, self.configs,
                                      b["id"], b["map"], b["timeout"],
                                      b["language"], b["cloud"], b["next"],
                                      b["contTag"], b["containerName"])
                    blockList.append(ar)
                    ids.append(b["id"])
                h["memory"] = calcBlockMemory(blockList)
                h["block"] = blockList
                h["ids"] = ids
                h["id"] = str(ids)
                h["type"] = "block"

            self.actList.append(h)

    def start(self):

        def fit(actions, nodes):
            """
            Search a feasible parallel assignement of actions in nodes.

            If action fit (memory) in the first most free node, make the couple,
            remove the used memory from the available in the node, and put node
            at the end of the list.
            Recursively call itself removing the assigned action and with the new
            ordered node list.
            """
            couples = []
            actL = deepcopy(actions)[1:]

            a = actions[0]

            if a["type"] == "action" and a["cloud"] == "2":
                couples.append((a, "_cloud", AWSInvoker()))
                if len(actL) == 0:
                    return couples
                ret = fit(actL, nodes)
                if ret:
                    couples += ret
                    return couples
            else:
                for n in nodes:
                    nodeL = deepcopy(nodes)
                    if n["cpu"] > 75:
                        self.log("Selecting node - Jumping node %s because full" % (n["_id"]))
                        continue
                    actMem = a["memory"] * 1000000
                    if actMem <= n["memory"]:
                        nodeL.remove(n)
                        newNode = deepcopy(n)
                        newNode["memory"] = n["memory"] - actMem
                        nodeL.append(newNode)

                        if len(actL) == 0:
                            # No more actions to assign
                            couples.append((a, n['_id'],
                                            NodeInvoker(nodesDB.getNode(n['_id'])['ip'])))
                            return couples

                        ret = fit(actL, nodeL)
                        if not ret:
                            continue
                        else:
                            couples.append((a, n['_id'],
                                            NodeInvoker(nodesDB.getNode(n['_id'])['ip'])))
                            couples += ret
                            return couples
                if a["type"] == "action" and a["cloud"] == "1":
                    # no node available, i can go on cloud, offload!
                    couples.append((a, "_cloud", AWSInvoker()))
                    if len(actL) == 0:
                        return couples
                    ret = fit(actL, nodeL)
                    if ret:
                        couples += ret
                        return couples

            return None

        self.log("start execution")
        threads = []
        nodesRes = nodesDB.allRes()
        nodesL = self.sortedCPU(nodesRes)  # Sort available nodes by memory
        begin = time.time()
        coupling = fit(self.actList, nodesL)
        elapsed = time.time() - begin
        self.log("Parallel placement in " + repr(elapsed))
        if coupling:
            for c in coupling:
                act, nodeName, inv = c

                try:
                    param = self.prepareBlockInput(act["block"])
                except KeyError:
                    param = self.prepareInput(act["map"], self.param)

                t = InvokerThread(inv, act, self.sessionID, param, act["type"], self.nlog)
                t.start()
                self.log("Executing " + act["id"] + " in: " + nodeName)
                threads.append(t)

            for t in threads:
                t.join()
                text, code = t.ret

                if code >= 400:
                    self.ret = ({"error": text}, 500)
                    self.log("ERROR in remote execution")
                    self.log(text)
                    # TODO recovery action
                    return self.ret
                else:
                    try:
                        retJson = json.loads(text)
                    except TypeError:
                        retJson = text

                    self.log("EXECUTED %s in %s" % (t.action["id"], repr(t.elapsed)))
                    if self.nlog:
                        self.logList += retJson["__log__"]
                        del retJson["__log__"]

                    if t.actType == "block":
                        for k in retJson:
                            self.results[k] = retJson[k]
                    else:
                        self.results[t.action["id"]] = retJson

        else:
            self.ret = self.startDumb()
            return self.ret

        self.ret = self.results, 200
        return self.ret

    # DUMB START, just parallel start
    def startDumb(self):
        """Manage the parallel actions as if they come in separate calls (with threads)."""
        self.log("start independent execution")
        handlers = []
        threads = []
        for h in self.actList:
            if h["type"] == "action":
                hand = AsActionExecutionHandler(self.sessionID, h, self.param, self.nlog)
                handlers.append(hand)
            else:
                hand = AsBlockExecutionHandler(self.sessionID,
                                               h["block"],
                                               self.param,
                                               self.nlog,
                                               h["ids"],
                                               h["memory"])
                handlers.append(hand)

            t = hand.startThreaded()
            t.start()
            threads.append(t)

        for t in threads:
            t.join()

        for h in handlers:
            ret, status_code = h.ret
            self.logList += h.logList
            if status_code >= 400:
                self.log("Error")
                self.ret = ret, status_code
                return self.ret

            if h.__class__ == AsActionExecutionHandler:
                self.results[h.action["id"]] = ret
            else:
                for k in ret:
                    self.results[k] = ret[k]

        self.log("end execution")
        self.ret = self.results, 200
        return self.ret

    def log(self, message):
        ts = datetime.now().isoformat()
        id = "PARALLEL"
        logStr = ts + " - " + id + ": " + message
        print logStr
        self.logList.append(logStr)
