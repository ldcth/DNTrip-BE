from database.connect import database
from pymongo.errors import OperationFailure
import json
from bson import ObjectId
from datetime import datetime, timedelta


db = database['contents']


class Contents:
    def __init__(self,  conversationId=None, threadId=None, content="", type="", intent=""):
        self.conversationId = conversationId
        self.threadId = threadId
        self.content = content
        self.type = type
        self.intent = intent
        self._id = None
        self.createdAt = datetime.utcnow()
        self.updatedAt = datetime.utcnow()

    def save_to_db(self):
        try:
            if self._id != None:
                self.updatedAt = datetime.utcnow()
                obj_dict = self.__dict__.copy()
                obj_dict.pop('_id', None)
                result = db.find_one_and_update({"_id": ObjectId(self._id)},
                                                {"$set": obj_dict})
            else:
                obj_dict = self.__dict__.copy()
                obj_dict.pop('_id', None)
                result = db.insert_one(obj_dict)
                self._id = str(result.inserted_id)
                return result.inserted_id
        except OperationFailure as e:
            print(f"Error save to database: {e}")
            return None
    
    def find_by_id(self, id):
        try:
            result = db.find_one({"_id": ObjectId(id)})
            if result:
                result['_id'] = str(result['_id'])
                self._id = str(result['_id'])
                self.conversationId = result['conversationId']
                self.threadId = result['threadId']
                self.content =  result['content']
                self.type = result['type']
                self.intent =  result['intent']
                self.createdAt = result['createdAt']
                self.updatedAt = result['updatedAt']
            else:
                return None
        except OperationFailure as e:
            print(f"Error finding settings: {e}")
            return None
        
    @staticmethod
    def get_total():
        try:
            res = db.count_documents({"type": "answer"})
            return res
        except OperationFailure as e:
            print(f"Error finding settings: {e}")
            return None
        
    @staticmethod
    def get_total_feedback():
        try:
            res = db.count_documents({"bad_response": True, "type": "answer"})
            return res
        except OperationFailure as e:
            print(f"Error finding settings: {e}")
            return None
    
    @staticmethod
    def delete_by_conversation_id(id):
        try:
            result = db.find({"conversationId": id})
            if result:
                result = list(result)
                for item in result:
                    item["_id"] = str(item['_id'])
                return result
        except OperationFailure as e:
            print(f"Error finding settings: {e}")
            return None

    @staticmethod
    def delete_by_id(id):
        try:
            db.delete_one({"_id": ObjectId(id)})
        except OperationFailure as e:
            print(f"Error finding settings: {e}")
            return None

    