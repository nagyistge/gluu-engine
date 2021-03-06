# -*- coding: utf-8 -*-
# Copyright (c) 2015 Gluu
#
# All rights reserved.

import json

import jsonpickle
from werkzeug.utils import import_string
from flask_pymongo import PyMongo


class Database(PyMongo):
    def _load_pyobject(self, data):
        # ``jsonpickle.decode`` automatically instantiates object from
        # ``py/object`` value stored in database; the problem is,
        # this object won't recognize new attribute hence we're
        # instantiating object and setting its attributes manually
        cls = import_string(data["py/object"])
        obj = cls()
        for k, v in data.iteritems():
            setattr(obj, k, v)
        return obj

    def get(self, identifier, table_name):
        obj = self.db[table_name].find_one({"id": identifier})

        if not obj:
            return
        return self._load_pyobject(obj)

    def persist(self, obj, table_name):
        # encode the object so we can decode it later
        encoded = jsonpickle.encode(obj)

        # tinydb requires a ``dict`` object
        data = json.loads(encoded)
        data["_id"] = data["id"]
        return self.db[table_name].insert_one(data)

    def all(self, table_name):
        data = self.db[table_name].find()
        return [self._load_pyobject(item) for item in data]

    def delete(self, identifier, table_name):
        return self.db[table_name].delete_one({"id": identifier})

    def update(self, identifier, obj, table_name):
        # encode the object so we can decode it later
        encoded = jsonpickle.encode(obj)

        # tinydb requires a ``dict`` object
        data = json.loads(encoded)
        return self.db[table_name].update({"id": identifier}, data, True)

    def search_from_table(self, table_name, condition):
        data = self.db[table_name].find(condition)
        return [self._load_pyobject(item) for item in data]

    def count_from_table(self, table_name, condition):
        return self.db[table_name].count(condition)

    def update_to_table(self, table_name, condition, obj):
        # encode the object so we can decode it later
        encoded = jsonpickle.encode(obj)

        # tinydb requires a ``dict`` object
        data = json.loads(encoded)
        return self.db[table_name].update(condition, data, True)

    def delete_from_table(self, table_name, condition):
        return self.db[table_name].delete_one(condition)


# shortcut to database object
db = Database()
