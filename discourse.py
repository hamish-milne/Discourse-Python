
"""
Python module for interfacing with the Discourse API
"""

import requests
import datetime
import urllib

TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"

# For some reason, requests.delete doesn't allow a params argument, so we need to
# encode it manually here
def fixed_delete(url, params):
	if params != None:
		url += '?' + urllib.urlencode(params)
	return requests.delete(url)

# Here we specify how the different objects are retrieved and modified from the API
# The endpoints are specified as a tuple:
#    0: The request function to use. Corresponds to GET, PUT, POST etc.
#    1: A format string describing the URI, formatted based on object members
#    2: If None, the json response is returned in its entirety;
#        otherwise only the named member will be returned
USER_GET1 =           (requests.get, "/users/{username}.json", 'user')
USER_GET2 =           (requests.get, "/admin/users/{id}.json", None)
USER_PUT =            (requests.put, "/users/{username}", 'user')

GROUP_GET =           (requests.get, "/groups/{name}.json", 'basic_group')
GROUP_PUT =           (requests.put, "/admin/groups/{id}", 'basic_group')
GROUP_MEMBERS_GET =   (requests.get, "/groups/{name}/members.json", None)
GROUPS_GET =          (requests.get, "/admin/groups.json", None)

CATEGORY_GET =        (requests.get, "/c/{id}/show.json", 'category')
CATEGORY_PUT =        (requests.put, "/categories/{id}", 'category')
CATEGORY_DELETE =     (fixed_delete, "/categories/{id}", None)
CATEGORY_SET_NOTIFY = (requests.post, "/category/{id}/notifications", None)
CATEGORY_ADD =        (requests.post, "/categories", 'category')

def str_to_time(string):
	if not string:
		return None
	return datetime.datetime.strptime(string, TIME_FORMAT)

def nullable(type):
	return lambda x: None if x == None else type(x)

def reftype(x):
	return x

def find(list, f, default=None):
	for x in list:
		if f(x):
			return x
	return default

def time_to_str(time):
	if not time:
		return None
	return time.strftime(TIME_FORMAT)
	
def AddProperties(c, list):
	wlist = []
	for p in list:
		if isinstance(p, str):
			p = (p,)
		name = p[0]
		type = str if len(p) <= 1 else p[1]
		writable = True if len(p) <= 2 else p[2]
		set_cast = type if len(p) <= 3 else p[3]
		if writable:
			prop = property(lambda s,name=name,type=type: type(s.get(name)),
				lambda s,v,name=name,set_cast=set_cast: s.set(name, set_cast(v)))
			wlist.append(name)
		else:
			prop = property(lambda s,name=name,type=type: type(s.get(name)))
		setattr(c, name, prop)
	setattr(c, 'get_writable', lambda s: wlist)
	
class ForumObject(object):
	def __init__(self, api):
		self.api = api
		self._d = None
	
	def create_writable(self):
		return {k: self._d[k] for k in self.get_writable() if k in self._d}
	
	
class User(ForumObject):

	def __init__(self, api, params):
		super(User, self).__init__(api)
		if isinstance(params, int):
			self._d = {'id': params}
			self.update(False)
		elif isinstance(params, str):
			self._d = {'username': params}
			self.update(False)
		else:
			self._d = params
	
	def update(self, complete):
		loaded = False
		if 'username' in self._d and (complete or 'id' not in self._d):
			self._d = self.api.request(USER_GET1, self._d)
			loaded = True
		if complete or not loaded:
			self._d.update(self.api.request(USER_GET2, self._d))
	
	def set(self, name, value):
		self._d.update(self.api.request(USER_PUT, self._d, {name: value}))
	
	def get(self, name):
		if name not in self._d:
			self.update(True)
		return self._d[name]
	
	def __str__(self):
		return self.username


AddProperties(User, [
	('id', int, False),
	('avatar_template', str, False),
	('last_posted_at', str_to_time, False),
	('last_seen_at', str_to_time, False),
	('created_at', str_to_time, False),
	'username',
	'name',
	'email',
	'bio_raw',
	('bio_cooked', str, False),
	('bio_excerpt', str, False),
	'website_name',
	'profile_background',
	'card_background',
	'location',
	('trust_level', int),
	('moderator', bool),
	('admin', bool),
	'title'
])

	
class MemberCollection(object):

	def __init__(self, group):
		self.__group = group
		self.__list = None
		self.__offset = 0
		self.__count = None
	
	def __len__(self):
		if self.__count == None:
			data = self.__group.api.request(GROUP_MEMBERS_GET, self.__group._Group_d, {'limit': 0})
			self.__count = int(data['meta']['total'])
		return self.__count
	
	def __getitem__(self, i):
		list = self.__list
		offset = self.__offset
		if not list or i < offset or i >= len(list)+offset:
			group = self.__group
			data = group.api.request(GROUP_MEMBERS_GET, self.__group._Group_d, {'offset': i})
			self.__offset = i
			self.__count = int(data['meta']['total'])
			self.__list = [User(group.api, p) for p in data['members']]
		return self.__list[i - self.__offset]

class Group(ForumObject):

	def __init__(self, api, params):
		super(Group, self).__init__(api)
		if isinstance(params, int):
			self._d = {'id': params}
			self.update(False)
		elif isinstance(params, str):
			self._d = {'username': params}
			self.update(False)
		else:
			self._d = params
		self.members = MemberCollection(self)
	
	def get(self, name):
		return self._d[name]
	
	def set(self, name, value):
		args = self.create_writable()
		args[name] = value
		self._d = self.api.request(GROUP_PUT, self._d, args)
	
	def __str__(self):
		return self.name

AddProperties(Group, [
	('id', int, False),
	('automatic', bool, False),
	'name',
	('user_count', int, False),
	('alias_level', int), # Check this
	('visible', bool),
	'automatic_membership_email_domains',
	('automatic_membership_retroactive', bool),
	('primary_group', bool),
	'title',
	('grant_trust_level', int),
	('incoming_email', nullable(str)), # Check type
	('has_messages', bool, False), # Check this
	('is_member', bool, False), # Check this
	('mentionable', bool, False),
	('flair_url', nullable(str)),
	('flair_bg_color', nullable(str))
])

class Permission:
	NONE = 0
	ALL = 1
	REPLY = 2
	VIEW = 3

class NotifyLevel:
	MUTED = 0
	NORMAL = 1
	WATCHING_FIRST_POST = 4
	TRACKING = 2
	WATCHING = 3
	
class Category(ForumObject):
	
	def __init__(self, api, params={}):
		super(Category, self).__init__(api)
		if isinstance(params, int):
			self._d = {'id': params}
			self.update()
		elif isinstance(params, str):
			self._d = {'slug': params}
			self.update()
		else:
			self._d = params
	
	def update(self):
		if 'id' in self._d:
			id = str(self._d['id'])
		else:
			id = self._d['slug']
		self._d = self.api.request(CATEGORY_GET, {'id': id})
	
	def get(self, key):
		if not key in self._d:
			self.update()
		return self._d[key]
	
	def create_writable(self):
		base = super(Category, self).create_writable()
		gp = self._d.get('group_permissions')
		if gp:
			for x in gp:
				base["permissions[{0}]".format(x['group_name'])] = x['permission_type']
		return base
	
	def set(self, key, value):
		args = self.create_writable()
		args[key] = value
		self._d.update(self.api.request(CATEGORY_PUT, self._d, args))
	
	def get_permission(self, key):
		p = find(self.get('group_permissions'), lambda x: x['group_name'] == key)
		if p:
			return p['permission_type']
		return Permission.NONE
	
	def set_permission(self, key, value):
		p = find(self.get('group_permissions'), lambda x: x['group_name'] == key)
		if p:
			p['permission_type'] = int(value)
		else:
			self.get('group_permissions').append({'group_name': key, 'permission_type': value})
		self.set('slug', self._d['slug']) # TODO: Dedicated 'upload' function?
	
	@property
	def notification_level(self):
		return int(self.get('notification_level'))
	
	@notification_level.setter
	def notification_level(self, value):
		self.api.request(CATEGORY_SET_NOTIFY, self._d, {'notification_level': int(value)})
	
	def delete(self):
		self.api.request(CATEGORY_DELETE, self._d)
	

AddProperties(Category, [
	('id', int, False),
	'name',
	'color',
	'text_color',
	'slug',
	('topic_count', int, False),
	('post_count', int, False),
	('position', int),
	('description_text', str, False),
	('description', str, False),
	'topic_url',
	'logo_url',
	'background_url',
	('read_restricted', bool),
	('permission', int),
	('can_edit', bool, False),
	'topic_template',
	('has_children', nullable(str), False),
	('auto_close_hours', str_to_time, True, time_to_str),
	('auto_close_based_on_last_post', bool),
	('email_in', nullable(str)),
	('email_in_allow_strangers', bool),
	('suppress_from_homepage', bool),
	('can_delete', bool, False),
	('cannot_delete_reason', nullable(str), False),
	('is_special', bool, False),
	('allow_badges', bool),
	('custom_fields', reftype, False)
])

class Discourse(object):
	
	def __init__(self, url, apiName=None, apiKey=None):
		self.url = url
		self.apiName = apiName
		self.apiKey = apiKey
	
	def request(self, url_tuple, d, params=None, throwOnFail=True):
		if not params:
			params = {}
		if self.apiName:
			params['api_username'] = self.apiName
		if self.apiKey:
			params['api_key'] = self.apiKey
		url = url_tuple[1]
		url = url.format(**d)
		function = url_tuple[0]
		r = function(self.url + url, params)
		if r.status_code != 200 and not throwOnFail:
			return None
		r.raise_for_status()
		j = r.json()
		if isinstance(j, dict):
			errors = j.get('errors')
			if errors:
				raise Exception(errors)
		if url_tuple[2] != None:
			j = j[url_tuple[2]]
		return j
	
	def groups(self):
		return [Group(self, p) for p in self.request(GROUPS_GET, {})]
	
	def group(self, name):
		return Group(self, self.request(GROUP_GET, {'name': name}))

	def user(self, name):
		return User(self, name)
	
	def category(self, id):
		return Category(self, id)
	
	def add_category(self, name):
		cat = Category(self, {'name': name, 'color': 'AB9364', 'text_color': 'FFFFFF', 'parent_category_id': None, 'allow_badges': True})
		print self.request(CATEGORY_ADD, cat._d, cat.create_writable())
		return cat



