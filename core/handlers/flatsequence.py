from core.databaseMongo import actionsDB, sequencesDB as sdb
from copy import deepcopy

def unrollAndDAG(sequence, outputMapping):
    full, outMap = unrollSequence(sequence, outputMapping)
    fullNext = computeNext(full, outMap)
    fullPN = computePrev(fullNext)
    return fullPN, outMap

def unrollSequence(sequence, outputMapping, superID=None, superMap={}):
    """
    Take a nested sequence and create a unique sequence.

    Adjusts ids and map processes added before a new sequence.
    """
    final = []
    midMap = {}
    for act in sequence:
        a = deepcopy(act)
        id = a["id"]
        mapping = a["map"]
        if superID:
            # action belongs to a subsequence
            prefix = superID + "_"
            id = prefix + a["id"]
            mapping = {}
            for k in a["map"]:
                l = str(a["map"][k]).split("/")
                if l[0] == "param":
                    mapping[k] = superMap[l[1]]
                else:
                    mapping[k] = prefix + a["map"][k]

        for k in mapping:
            l = str(mapping[k]).split("/")
            if l[0] in midMap:
                mapping[k] = midMap[l[0]][l[1]]

        if not actionsDB.availableActionName(a['name']):
            # encounter an action
            action = a
            action["id"] = id
            action["map"] = mapping
            action["prev"] = [v.split("/")[0] for v in action["map"].values()]
            final.append(action)
        else:
            proc = sdb.getSequence(a["name"])["fullSeq"]
            seq, innerOutMap = unrollSequence(proc, id, mapping)
            # setto come output della sottosequenza (per le successive) il nuovo id dell'ultima azione.
            midMap[id] = innerOutMap
            final += seq
    # fix outMap
    if not superID:
        newOutMap = {}
        for k in outputMapping:
            v = outputMapping[k]
            rid, out = v.split("/")
            if rid in midMap:
                newOutMap[k] = midMap[rid][out]
            else:
                newOutMap[k] = outputMapping[k]
    else:
        newOutMap = {}
        for k in outputMapping:
            newOutMap[k] = superID + "_" + outputMapping[k]

    return final, newOutMap

def computePrev(sequence):
    """Compute the full list of actions that comes before every action."""
    def getPrevFromId(id):
        if id == "param":
            return set()
        for a in sequence:
            if a["id"] == id:
                return set(a["prev"])
        return set()

    for a in sequence:
        nPrev = set(a["prev"])
        for p in a["prev"]:
            nPrev |= getPrevFromId(p)
        a["prev"] = list(nPrev)
    return sequence

def computeNext(sequence, outMap):
    """For every action find all the actions that uses its output."""
    outId = [v.split("/")[0] for v in outMap.values()]
    s = []
    for ind in range(0, len(sequence)):
        follows = []
        a = deepcopy(sequence[ind])
        id_A = a["id"]

        for j in range(ind, len(sequence)):
            b = sequence[j]
            vals = b["prev"]
            if id_A in vals:
                follows.append(b["id"])
        if id_A in outId:
            follows.append("__out__")

        a["next"] = follows
        s.append(a)

    return s
