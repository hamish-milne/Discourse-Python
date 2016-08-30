import requests
import datetime
import urllib

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
		url += '?' + urllib.urlencode(params)
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
GROUP_MEMBERS_GET =   (requests.get, "/groups/{name}/members.json", None)
GROUPS_GET =          (requests.get, "/admin/groups.json", None)

CATEGORY_GET =        (requests.get, "/c/{id}/show.json", 'category')
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
	
class Permission:
	"""Constants for category permissions"""
	NONE = 0
	ALL = 1
	REPLY = 2
	VIEW = 3

class NotifyLevel:
	"""Constants for category notification levels"""
	MUTED = 0
	NORMAL = 1
	WATCHING_FIRST_POST = 4
	TRACKING = 2
	WATCHING = 3

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
		self.api = api
		self._d = None
		self.suspended = False
		self.has_changes = False
	
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
	
	def update_all_fields(self):
		"""Whether all writable fields need to be updated in a single request
		
		Some Discourse endpoints require setting all relevant fields at once,
		or the rest of the data will be implicitly set to null. If this is the
		case, override this method to return `True`.
		"""
		return False
	
	def commit(self, changes=None):
		"""Writes back your changes to the server (if not suspended)
		
		Args:
			changes: The map of changed field names to values. If None,
			`self.get_state()` is used
		"""
		if not suspended and (changes or self.has_changes):
			if not changes:
				changes = self.get_state()
			self._d.update(self.api.request(
				self.put_endpoint(), self._d, changes))
			self.has_changed = 0
	
	def update(self):
		"""Downloads the object state from the server"""
		self._d = self.api.request(self.get_endpoint(), self._d)
	
	def suspend(self):
		"""Pauses automatic committing when a value is changed"""
		self.suspended = True
	
	def resume(self):
		"""Disables the suspension and commits changes"""
		self.suspended = False
		self.commit()
	
	def get(self, key):
		"""Gets a value from the cache or server"""
		if key not in self._d:
			self.update()
		return self._d[key]
	
	def set(self, key, value):
		"""Sets a value, which will commit changes to the server if needed"""
		if self.suspended:
			self._d[key] = value
		else if key not in self._d or self._d[key] != value:
			if not self.update_all_fields():
				self.commit({key: value})
			else
				self.commit()
	
	def __enter__(self):
		self.suspend()
		return self
	
	def __exit__(self):
		self.resume()
	
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
			data = self.__group.api.request(GROUP_MEMBERS_GET,
				self.__group._Group_d, {'limit': 0})
			self.__count = int(data['meta']['total'])
		return self.__count
	
	def __getitem__(self, i):
		list = self.__list
		offset = self.__offset
		if not list or i < offset or i >= len(list)+offset:
			group = self.__group
			data = group.api.request(GROUP_MEMBERS_GET, self.__group._Group_d,
				{'offset': i})
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
		args = self.get_state()
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
	
	def get_state(self):
		base = super(Category, self).get_state()
		gp = self._d.get('group_permissions')
		if gp:
			for x in gp:
				base["permissions[{0}]".format(x['group_name'])] =
					x['permission_type']
		return base
	
	def set(self, key, value):
		args = self.get_state()
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
			self.get('group_permissions').append({
				'group_name': key,
				'permission_type': value})
		self.set('slug', self._d['slug']) # TODO: Dedicated 'upload' function?
	
	@property
	def notification_level(self):
		return int(self.get('notification_level'))
	
	@notification_level.setter
	def notification_level(self, value):
		self.api.request(CATEGORY_SET_NOTIFY, self._d, {
			'notification_level': int(value)})
	
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
		cat = Category(self, {
			'name': name,
			'color': 'AB9364',
			'text_color': 'FFFFFF',
			'parent_category_id': None,
			'allow_badges': True})
		print self.request(CATEGORY_ADD, cat._d, cat.get_state())
		return cat



