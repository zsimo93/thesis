import gridfs
from pymongo import MongoClient
from core.utils.fileutils import unzip, uniqueName
import os

fs = gridfs.GridFS(MongoClient(host='localhost', port=27017).fs)
print "importing FS client"

def saveFile(file, actionName):
    fs.put(file, _id=actionName, content_type=file.content_type,
           filename=file.filename)


def loadFile(actionName):
    while(True):
        folderName = uniqueName()
        path = "/tmp/" + folderName
        try:
            os.stat(path)
        except Exception:
            os.mkdir(path)
            break

    f = fs.find_one(actionName)

    name = f.filename
    f.seek(0)
    data = f.read()

    pathfile = path + "/" + name
    # save the file in local fs
    file = open(pathfile, "w+")
    file.write(data)
    file.close()

    # if a zip, unzip it
    if name.endswith(".zip"):
        unzip(pathfile, path)
        os.remove(pathfile)
    
    return path

def removeFile(actionName):
    fs.delete(actionName)

def tempResult(data, actionName):
    fs.put(data, action=actionName)