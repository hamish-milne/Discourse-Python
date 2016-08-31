import requests
import datetime
import urllib
from string import Formatter
import collections

"""Discourse API in Python

Example:
	api = Discourse("https//example.com/forum", 'system', API_KEY)
	category = api.add_category('My Category')
	category.set_permission('everyone', Permission.SEE)
	
This module is a wrapper around the Discourse REST API, designed to
provide a sane, Pythonic interface and speed the development of custom
plugins and web apps.

Concepts like users, posts and categories are represented as `ForumObject`
subclasses, which expose data based on an internal dictionary which is created
from the JSON data provided by the server.

Access to member data is done through properties, which will automatically
perform any API requests needed to read or write them.

By default, any actions done in code will be applied immediately, which makes
interactions predictable and easy to write, but will obviously be rather slow.
To mitigate this you can call `suspend` on any `ForumObject` to disable
automatic updating, then `resume` to apply any changes over (in most cases) a
single HTTP request. You can also use the `with` statement.

Example:
	with category = api.category("my-category"):
		category.name = "New name"
		category.slug = "new-name"

The Discourse API is largely designed for internal use, and with the
platform still under heavy development there is a good chance that
the endpoints, functionality and conventions could change at any time.
This module is designed such that these changes can be quickly applied,
by separating out the endpoint definitions and automatically generating
properties for each class.
	
"""

TIME_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
"""str: The format string used to represent a timestamp in JSON data
"""

def fixed_delete(url, params):
	"""A wrapper around `requests.delete` that has a compatible signature
	
	For some reason, requests.delete doesn't allow a params argument, so
	we need to encode it manually here
	"""
	if params != None:
		url += '?' + urllib.urlencode(
			{k: v for k,v in params.iteritems() if v != None})
	return requests.delete(url)

"""API endpoint definition. Each endpoint is specified as a tuple:
	0: The request function to use. Corresponds to GET, PUT, POST etc.
	1: A format string describing the URI, formatted based on object members
	2: If None, the json response is returned in its entirety;
	   otherwise only the named member will be returned
"""

USER_GET1 =           (requests.get, "/users/{username}.json", 'user')
USER_GET2 =           (requests.get, "/admin/users/{id}.json", None)
USER_PUT =            (requests.put, "/users/{username}", 'user')

GROUP_GET =           (requests.get, "/groups/{name}.json", 'basic_group')
GROUP_PUT =           (requests.put, "/admin/groups/{id}", 'basic_group')
GROUP_DELETE =        (fixed_delete, "/admin/groups/{id}", None)
GROUP_ADD =           (requests.post, "/admin/groups", 'basic_group')
GROUPS_GET =          (requests.get, "/admin/groups.json", None)

GROUP_OWNERS_GET =    (requests.get, "/groups/{name}/members.json", 'owners')
GROUP_OWNERS_ADD =    (requests.put, "/admin/groups/{id}/owners.json", None)
GROUP_OWNERS_REMOVE = (fixed_delete, "/admin/groups/{id}/owners.json", None)
GROUP_MEMBERS_GET =   (requests.get, "/groups/{name}/members.json", None)
GROUP_MEMBERS_ADD =   (requests.put, "/admin/groups/{id}/members.json", None)
GROUP_MEMBERS_REMOVE = (fixed_delete, "/admin/groups/{id}/members.json", None)
GROUP_ADD_BULK =      (requests.put, "/admin/groups/bulk", None)

CATEGORY_GET =        (requests.get, "/c/{id_or_slug}/show.json", 'category')
CATEGORY_PUT =        (requests.put, "/categories/{id}", 'category')
CATEGORY_DELETE =     (fixed_delete, "/categories/{id}", None)
CATEGORY_SET_NOTIFY = (requests.post, "/category/{id}/notifications", None)
CATEGORY_ADD =        (requests.post, "/categories", 'category')

def str_to_time(string):
	""" Converts a standard date-time string into a datetime object """
	if not string:
		return None
	return datetime.datetime.strptime(string, TIME_FORMAT)

def time_to_str(time):
	""" Converts a datetime object into a standard string format """
	if not time:
		return None
	return time.strftime(TIME_FORMAT)
	
def nullable(type):
	"""A wrapper for type objects that preserves None values
	
	Use this with `AddProperties` when the value in question may be None/null
	"""
	return lambda x: None if x == None else type(x)

def reftype(x):
	"""Used with `AddProperties` for values that should not be
	transformed; lists, dictionaries etc.
	"""
	return x

def find(list, f, default=None):
	"""Searches for an item in a collection based on a condition function
	
	Returns the first item in `list` for which `f(x)` evaluates to `True`
	If no items match, `default` is returned
	"""
	for x in list:
		if f(x):
			return x
	return default

def is_iterable(o):
	return isinstance(o, collections.Iterable) and not isinstance(o, str)
	
class Permission:
	"""Constants for category permissions.
	Describes what a given group can do within that category"""
	NONE = 0
	ALL = 1
	REPLY = 2
	VIEW = 3

class NotifyLevel:
	"""Constants for category notification levels
	Describes what sort of actions trigger user notifications"""
	MUTED = 0
	NORMAL = 1
	WATCHING_FIRST_POST = 4
	TRACKING = 2
	WATCHING = 3

class AliasLevel:
	"""Constants for group `alias_level`
	Describes who can @mention this group"""
	NOBODY = 0
	STAFF = 2
	GROUP_MEMBERS = 3
	EVERYONE = 99

def AddProperties(c, list):
	"""Adds named properties to a ForumObject class
	
	Args:
		c: The class object to add properties to
		list: A list of property tuples
		
	The function expects tuples of the form:
		(name:str, type:function, writable:bool, set_cast:function)
	
	If they are not provided, the is assumed to be `str`, writable is assumed
	True, and `set_cast` is set the same as `type`.
	
	A string on its own can be used in place of a singleton tuple. It will
	create a read-write string property.
	
	Reading the property will return `type(self.get(name))`.
	Writing it will call `self.set(name, set_cast(value))`.
	
	In `ForumObject`, these methods access the backing dictionary and
	do any necessary HTTP requests.
	
	Additionally, the function will create a class method `get_writable` which
	returns a tuple of writable property names. This is used by the object
	classes for which all parameters must be set in every mutating HTTP request.
	"""
	
	wlist = []
	for p in list:
		# Load in arguments
		if isinstance(p, str):
			p = (p,)
		name = p[0]
		type = str if len(p) <= 1 else p[1]
		writable = True if len(p) <= 2 else p[2]
		set_cast = type if len(p) <= 3 else p[3]
		
		# Create property object
		if writable:
			prop = property(lambda s,name=name,type=type: type(s.get(name)),
			lambda s,v,name=name,set_cast=set_cast: s.set(name, set_cast(v)))
			wlist.append(name)
		else:
			prop = property(lambda s,name=name,type=type: type(s.get(name)))
		setattr(c, name, prop)
	
	# Create `get_writable`
	wlist = tuple(wlist)
	setattr(c, 'get_writable', lambda s: wlist)

class ForumObject(object):
	"""Base class for a forum object backed by a JSON dictionary
	
	If needed, the backing dictionary can be accessed directly with `_d`
	"""
	def __init__(self, api):
		if not api:
			raise Exception("Cannot create a ForumObject with no API")
		self.api = api
		self._d = None
		self.suspended = False
		self.has_changes = False
	
	def request(self, url_tuple, params=None):
		if params:
			for i in Formatter().parse(url_tuple[1]):
				if i[1] and i[1] not in self._d:
					self.update()
					break
		url = url_tuple[1]
		url = url.format(**self._d)
		return self.api.request(url_tuple[0], url, url_tuple[2], params)
	
	def get_state(self):
		"""Gets a map of writable properties and their values"""
		return {k: self._d[k] for k in self.get_writable() if k in self._d}
	
	def put_endpoint(self):
		"""Gets the endpoint for updating
		
		Returns:
			An endpoint tuple as described above
		"""
		raise Exception("No endpoint defined!")
	
	def get_endpoint(self):
		"""Gets the endpoint for downloading values
		
		Returns:
			An endpoint tuple as described above
		"""
		raise Exception("No endpoint defined!")
	
	def commit_all_fields(self):
		"""Whether all writable fields need to be updated in a single request
		
		Some Discourse endpoints require setting all relevant fields at once,
		or the rest of the data will be implicitly set to null. If this is the
		case, override this method to return `True`.
		"""
		return False
	
	def commit(self, changes=None):
		"""Writes back your changes to the server
		
		Args:
			changes: The map of changed field names to values. If None,
			`self.get_state()` is used
		"""
		if not changes:
			changes = self.get_state()
		self._d.update(self.request(self.put_endpoint(), changes))
		self.has_changes = False
	
	def update(self):
		"""Downloads the object state from the server"""
		self._d = self.request(self.get_endpoint())
	
	def suspend(self):
		"""Pauses automatic committing when a value is changed"""
		self.suspended = True
	
	def resume(self):
		"""Disables the suspension and commits changes"""
		self.suspended = False
		if self.has_changes:
			self.commit()
	
	def get(self, key):
		"""Gets a value from the cache or server"""
		if key not in self._d:
			self.update()
		return self._d[key]
	
	def set(self, key, value):
		"""Sets a value, which will commit changes to the server if needed"""
		self.has_changes = self.has_changes or \
			(key not in self._d or self._d[key] != value)
		self._d[key] = value
		if not self.suspended and self.has_changes:
			if not self.commit_all_fields():
				self.commit({key: value})
			else:
				self.commit()
	
	def __enter__(self):
		self.suspend()
		return self
	
	def __exit__(self, type, value, traceback):
		self.resume()
	
	def __eq__(self, y):
		if not isinstance(y, type(self)):
			return False
		return self.id == y.id
	
	def __ne__(self, y):
		if not isinstance(y, type(self)):
			return False
		return self.id != y.id
	
	def __hash__(self):
		return self.id
	
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
	
	def get_endpoint(self):
		return USER_GET1
		
	def put_endpoint(self):
		return USER_PUT
	
	def update(self, complete=True):
		loaded = False
		if 'username' in self._d and (complete or 'id' not in self._d):
			super(User, self).update()
			loaded = True
		if complete or not loaded:
			self._d.update(self.request(USER_GET2))
	
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

class UserList(object):
	def __init__(self, group):
		self._group = group
		self._list = None
	
	def get_endpoint(self):
		raise Exception("Endpoint not defined")
	
	def add_endpoint(self):
		raise Exception("Endpoint not defined")
	
	def del_endpoint(self):
		raise Exception("Endpoint not defined")
	
	def add(self, members):
		if not is_iterable(members):
			members = [members]
		else:
			members = list(members)
		for i in range(len(members)):
			m = members[i]
			if not isinstance(m, str):
				if isinstance(m, User):
					members[i] = m.username
				else:
					members[i] = self._group.api.user(m).username
		self._group.request(self.add_endpoint(), \
			{'usernames': ",".join(members)})
		self._list = None
	
	def remove(self, members):
		if not is_iterable(members):
			members = [members]
		for i in members:
			if not isinstance(i, int):
				if isinstance(i, User):
					i = i.id
				else:
					i = self._group.api.user(i).id
			self._group.request(self.del_endpoint(), {'user_id': i})
		self._list = None

	def update(self):
		self._list = self._group.request(self.get_endpoint())
	
	def __len__(self):
		if not self._list:
			self.update()
		return len(self._list)
	
	def __getitem__(self, i):
		if not self._list:
			self.update()
		return User(self._group.api, self._list[i])
			
	def replace_all(self, members):
		if not self._list:
			self.update()
		members = list(members) if is_iterable(members) else [members]
		toAdd = set()
		for i in range(len(members)):
			m = members[i]
			if not isinstance(m, User):
				toAdd.add(self._group.api.user(m))
			else:
				toAdd.add(m)
		toRemove = {o for o in self._list}
		cmdRemove = toRemove.difference(toAdd)
		cmdAdd = ",".join(toAdd.difference(toRemove))
		self._group.request(self.add_endpoint(), {'usernames': cmdAdd})
		for id in cmdRemove:
			self._group.request(self.del_endpoint(), {'user_id': id})
		self._list = members
	
class MemberList(UserList):

	def __init__(self, group):
		super(MemberList, self).__init__(group)
		self.__offset = 0
		self.__count = None
	
	def get_endpoint(self):
		return GROUP_MEMBERS_GET

	def add_endpoint(self):
		return GROUP_MEMBERS_ADD

	def del_endpoint(self):
		return GROUP_MEMBERS_REMOVE
	
	def __len__(self):
		if self.__count == None:
			data = self._group.request(self.get_endpoint(), {'limit': 0})
			self.__count = int(data['meta']['total'])
		return self.__count
	
	def __getitem__(self, i):
		list = self._list
		offset = self.__offset
		if not list or i < offset or i >= len(list)+offset:
			group = self._group
			data = group.request(self.get_endpoint(), {'offset': i})
			self.__offset = i
			self.__count = int(data['meta']['total'])
			self._list = [User(group.api, p) for p in data['members']]
		return self._list[i - self.__offset]
	
	def add_bulk(self, emails):
		self._group.request(GROUP_ADD_BULK, {
			'group_id': self._group.id, 'users[]': emails})
		self._list = None

class OwnerList(UserList):
	def get_endpoint(self):
		return GROUP_OWNERS_GET

	def add_endpoint(self):
		return GROUP_OWNERS_ADD

	def del_endpoint(self):
		return GROUP_OWNERS_REMOVE


class Group(ForumObject):

	def __init__(self, api, params):
		super(Group, self).__init__(api)
		if isinstance(params, str):
			self._d = {'name': params}
			self.update()
		else:
			self._d = params
		self.__members = MemberList(self)
		self.__owners = OwnerList(self)
	
	members = property(lambda s: s.__members, 
		lambda s,v: s.__members.replace_all(v))
	
	owners = property(lambda s: s.__owners, 
		lambda s,v: s.__owners.replace_all(v))
	
	def get_endpoint(self):
		return GROUP_GET
	
	def put_endpoint(self):
		return GROUP_PUT
	
	def commit_all_fields(self):
		return True
	
	def delete():
		self.request(GROUP_DELETE)
	
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
	
	def get_endpoint(self):
		return CATEGORY_GET
	
	def put_endpoint(self):
		return CATEGORY_PUT
	
	def commit_all_fields(self):
		return True
	
	def update(self):
		self._d['id_or_slug'] = self._d.get('id') or self._d['slug']
		super(Category, self).update()
	
	def get_state(self):
		state = super(Category, self).get_state()
		gp = self._d.get('group_permissions')
		if gp:
			for x in gp:
				state["permissions[{0}]".format(x['group_name'])] = \
					x['permission_type']
		return state
	
	def get_permission(self, key):
		p = find(self.get('group_permissions'),
			lambda x: x['group_name'] == key)
		if p:
			return p['permission_type']
		return Permission.NONE
	
	def set_permission(self, key, value):
		p = find(self.get('group_permissions'),
			lambda x: x['group_name'] == key)
		if p:
			p['permission_type'] = int(value)
		else:
			self.get('group_permissions').append({
				'group_name': key,
				'permission_type': value})
		if not self.suspended:
			self.commit()
	
	@property
	def notification_level(self):
		return int(self.get('notification_level'))
	
	@notification_level.setter
	def notification_level(self, value):
		self.request(CATEGORY_SET_NOTIFY, {'notification_level': int(value)})
	
	def delete(self):
		self.request(CATEGORY_DELETE)
	

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

class ObjectCreator(object):
	def __init__(self, obj, finish):
		self.obj = obj
		self.finish = finish

	def __enter__(self):
		return self.obj
	
	def __exit__(self, e_type, e_value, e_traceback):
		if not e_type:
			self.finish(self.obj)

class Discourse(object):
	
	def __init__(self, url, apiName=None, apiKey=None):
		self.url = url
		self.apiName = apiName
		self.apiKey = apiKey
	
	def request(self, function, url, member, params=None, throwOnFail=True):
		if not params:
			params = {}
		if self.apiName:
			params['api_username'] = self.apiName
		if self.apiKey:
			params['api_key'] = self.apiKey
		r = function(self.url + url, params)
		if r.status_code != 200 and not throwOnFail:
			return None
		r.raise_for_status()
		j = r.json()
		if isinstance(j, dict):
			errors = j.get('errors')
			if errors:
				raise Exception(errors)
		if member:
			j = j[member]
		return j
	
	def groups(self):
		return [Group(self, p) for p in self.request(GROUPS_GET)]
	
	def group(self, name):
		return Group(self, name)

	def user(self, name):
		return User(self, name)
	
	def category(self, id):
		return Category(self, id)
	
	def search_users(self, term, include_groups=False,
		include_mentionable_groups=False, topic_allowed_users=False):
		# GET /users/search/users
		pass
	
	def add_group(self, name):
		group = Group(self, {
			'name': name,
			'visible': True,
			'automatic_membership_retroactive': False,
			'primary_group': False})
		group.suspend()
		def group_create(g):
			g._d = g.request(GROUP_ADD, g.get_state())
			g.suspended = False
		return ObjectCreator(g, group_create)
	
	def add_category(self, name):
		cat = Category(self, {
			'name': name,
			'color': 'AB9364',
			'text_color': 'FFFFFF',
			'allow_badges': True})
		cat.suspend()
		def cat_create(c):
			cat._d = cat.request(CATEGORY_ADD, c.get_state())
			cat.suspended = False
		return ObjectCreator(cat, cat_create)
