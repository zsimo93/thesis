import uuid
from gridfs import GridFS
from pymongo import MongoClient
from datetime import datetime
from bson import Binary
from io import BytesIO

class NoFileException(Exception):
    pass

class WrongTypeException(Exception):
    pass

class FileManager:

    mongoclient = MongoClient(host='127.0.0.1', port=27017)
    mongodb = mongoclient.my_db
    coll = mongodb.userdata
    fs = GridFS(mongodb, collection="userdata")

    def saveFile(self, file, filename):
        # Pass as file a io.BytesIO data type
        # or bytes

        id = str(uuid.uuid4())
        if (type(file) == unicode):
            toSave = Binary(str(file))
        elif (type(file) == BytesIO):
            toSave = Binary(file.getvalue())
        else:
            try:
                toSave = Binary(file)
            except:
                try:
                    toSave = Binary(file.read())
                except:
                    raise WrongTypeException("cannot save the data in the type given")

        self.fs.put(toSave, _id=id, filename=filename,
                    uploadDate=datetime.utcnow())

        return id

    def loadFile(self, fileID):
        f = self.fs.find_one(str(fileID))
        if f:
            return f
        else:
            raise NoFileException("No file with id " + str(fileID))
