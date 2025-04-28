from database.connect import database
from pymongo.errors import OperationFailure
import json
from bson import ObjectId
from datetime import datetime, timedelta


db = database['users']


class Users:
    def __init__(self,  role = 0, name = "", email = "", password = "" ,histories = []):
        self.role = role
        self.name = name
        self.email = email
        self.password = password
        self.histories = histories
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
                self.role = result['role']
                self.name = result['name']
                self.histories = result['histories']
                self.email = result['email']
                self.password = result['password']
                self.createdAt = result['createdAt']
                self.updatedAt = result['updatedAt']
            else:
                return None
        except OperationFailure as e:
            print(f"Error finding settings: {e}")
            return None
        
    def find_by_email(self, email):
        try:
            result = db.find_one({"email":email})
            if result:
                result['_id'] = str(result['_id'])
                self._id = str(result['_id'])
                self.role = result['role']
                self.name = result['name']
                self.histories = result['histories']
                self.email = result['email']
                self.password = result['password']
                self.createdAt = result['createdAt']
                self.updatedAt = result['updatedAt']
                return True
            else:
                return False
        except OperationFailure as e:
            print(f"Error finding settings: {e}")
            return False
        
    @staticmethod
    def get_all_user():
        try:
            result = db.find({"role": 1})
            if result:
                result = list(result)
                for item in result:
                    item["_id"] = str(item['_id'])
                return result
            else:
                return []
        except OperationFailure as e:
            print(f"Error finding settings: {e}")
            return False

    @staticmethod
    def get_total():
        try:
            res = db.count_documents({"role": 1})
            return res
        except OperationFailure as e:
            print(f"Error finding settings: {e}")
            return None
        
    def find_by_question(self, quesion):
        try:
            res = db.count_documents({})
            return res
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

    