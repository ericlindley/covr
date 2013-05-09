#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

# Copyright 2007 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

################### Import Dependencies #####################

import cgi  #necessary?

import json
import urlparse
import urllib
import datetime
import webapp2
import jinja2
import os
import logging
import copy

from google.appengine.ext import db
from google.appengine.api import users, urlfetch


################## Create Environmental Variables ############
# This specifies the jinja environment to create templates.
jinja_environment = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.dirname(__file__)))

################### Set Up Database #####################
# For the Gif object
class Vid(db.Model):
	"""Models an individual video entry with the following properties."""
	# URL of video
	url = db.LinkProperty()
	# date of upload
	date = db.DateTimeProperty(auto_now_add=True)
	# user who uploaded the image
	author = db.StringProperty(multiline=False)
	# How popular or important is the gif....
	rank = db.IntegerProperty()
	# What tags are associated with this Vid
	tags = db.StringListProperty()

# Tag Schema-for the original song.
class Tag(db.Model):
	"""Models an individual Tag entry with the following properties."""
	# the name represents the word by which people want to tag a gif.
	name = db.StringProperty()
	# How popular or important is the tag....
	rank = db.IntegerProperty()
	# What Vids are described by this tag:
	vids = db.StringListProperty()

# Then, the mapping from the tags to the Video, and visa-versa
class Tagmap(db.Model):
	"""Models an individual Tagmap entry which maps a single tags to a single
	Gif. However, there can be many entries that can ultimately map many tags
	to a single gif, and visa-versa"""
	vid_id = db.ReferenceProperty(Vid)
	tag_id = db.ReferenceProperty(Tag)
	tag_name = db.StringProperty()

class Validate(db.Model):
	"""This class is used solely for validation purposes and stores no data"""
	string = db.StringProperty()
	url = db.LinkProperty()


############## Define Environmental Functions ##############
# This takes a list of tags as a string
# with caps, spaces and such, and makes it uniform
def clean_tags(tag_string):
	raw_tag_list = tag_string.split(",")
	tag_list = []
	for tag in raw_tag_list:
		tag_list.append(' '.join(tag.lower().strip().split()))
	return [e for e in list(set(tag_list)) if e]

def split_tags(tag_list):
	tags = copy.copy(tag_list)
	new_tags = [tag.split() for tag in tags]
	new_list = tags
	for tag in new_tags:
		new_list += tag
	return list(set(new_list))

def no_dupes(seq):
    seen = set()
    seen_add = seen.add
    return [ x for x in seq if x not in seen and not seen_add(x)]

# Helper function to take a youtube or vimeo link and turn it into
# the proper embed link
def make_embed_url(url):
	try:
		url_data = urlparse.urlparse(url)
		vid_host = url_data.hostname
		if vid_host == 'www.youtube.com' or vid_host == 'youtube.com':
			query = urlparse.parse_qs(url_data.query)
			try:
				vid_id = query["v"][0]
			except:
				return [1]
			embed_url = "http://www.youtube.com/embed/" + vid_id
		elif vid_host == 'vimeo.com':
			vid_id = url_data.path[1:]
			embed_url = "http://player.vimeo.com/video/" + vid_id
		elif vid_host == "youtu.be":
			vid_id = url_data.path[1:]
			embed_url = "http://www.youtube.com/embed/" + vid_id
			vid_host = "www.youtube.com"
		else:
			return [2]
		return embed_url, vid_id, vid_host
	except:
		return [0]

# Helper function to instantiate tag and tagmap, given a new
# video for the database.
def create_tagmap(vid, tags):
	existing_tags = [tag.name for tag in Tag.all()]
	all_tags = tags
	for single_tag in all_tags:
		tagmap = Tagmap()
		tagmap.vid_id = vid.key()
		tagmap.tag_name = single_tag
		if single_tag not in existing_tags:
			tag = Tag()
			tag.name = single_tag
			tag.rank = 0
			tag.put()
			tagmap.tag_id = tag.key()
		else:
			existing_tag_object = Tag.all().filter("name =", single_tag).fetch(1)
			tagmap.tag_id = existing_tag_object[0].key()
		tagmap.put()


################### Define Handlers ######################
# This is the primary handler for the page, on '/'
class MainHandler(webapp2.RequestHandler):
	def get(self):
		############# Login Requirements ################
		# Uses google login functionality to get the user.
		current_user = users.get_current_user()
		# Make sure someone is logged in and an admin to
		# see this page.
		if (current_user and 
			(current_user.email() == 'eric.lindley@gmail.com')) != True:
			self.redirect(users.create_login_url(self.request.uri))

		############## Get Search Terms ################
		orig_search = clean_tags(self.request.get('orig_search'))
		cover_search = clean_tags(self.request.get('cover_search'))
		from_add = clean_tags(self.request.get('m'))
		if from_add:
			from_add = from_add[0]
		### VALIDATE TERMS - LIMIT LENGTH
		## SECURITY / EFFICIENCY / ERRORHANDLING / TIMEOUT ETC CONSIDERATIONS

		################ Query Database ##################
		query = "Vid.all().order('-rank')"

		if orig_search or cover_search:
			search = [tag + "_o" for tag in orig_search] + [
						tag + "_c" for tag in cover_search]
			if search:
				for term in search:
					query += ".filter('tags =', '" + term + "')"
					vids = eval(query + ".fetch(6)")
			if vids:
				message = """Here are some songs for you,
							</h2><h2>based on your rad query!"""
			else:
				message = """So.... we couldn't find anything based on your search, 
							</h2><h2>but here are some consolation songs:"""
				vids = Vid.all().order("-rank").fetch(6)
		
		else:
			message = """Enter search terms to find Httt vids!
							</h2><h2>Here are our most popular:"""
			vids = Vid.all().order("-rank").fetch(6)

		if from_add == 'add':
			message = "Your cover has been added. Thanks for contributing!"

		elif from_add == 'urlfail':
			message = """Something went wrong, and your video was not added.
						</h2><h2>Please include http:// or https// in your URL.
						</h2><h2>Thanks!"""

		elif from_add == 'tagfail':
			message = """Something went wrong, and your video was not added.
						</h2><h2>Make your tags not insane&mdash;Thanks!"""

		elif from_add == 'hostfail':
			message = """Something went wrong, and your video was not added.
						</h2><h2>Use Youtube or Vimeo!! Thanks!"""

		elif from_add == 'activefail':
			message = """Something went wrong, and your video was not added.
						</h2><h2>Make sure your video is still active. Thanks!"""

		elif from_add == 'catchfail':
			message = """Something went wrong, and your video was not added.
						</h2><h2>Catchall!
						</h2><h2>Thanks!"""

		############ Clean Up Tags #######################
		tag_string_list = []
		for vid in vids:
			tag_string = ""
			for tag in reversed(sorted(vid.tags, key=len)):
				if tag[:-2] not in tag_string:
					tag_string += tag[:-2] + " "
			tag_string_list.append(tag_string)

		############ To Pass to HTML Template #############
		template_values = {
			'vids': vids,
			'message': message,
			'query': query,
			'tags': tag_string_list
		}

		############# Instantiate Template ######################
		template = jinja_environment.get_template('index.html')
		self.response.out.write(template.render(template_values))

class AddHandler(webapp2.RequestHandler):
	def post(self):
		## SECURITY / EFFICIENCY / ERRORHANDLING / TIMEOUT ETC CONSIDERATIONS
		url = self.request.get('url')

		try:
			vid_check = urlfetch.Fetch(url).status_code
		except:
			vid_check = 600
		if vid_check < 400:
			vid = Vid()
			vid_url = make_embed_url(url)[0]
			if vid_url == 0:
				##logging.info('mystery 1')
				self.redirect('/?m=catchfail')
			elif vid_url == 1:
				## youtube but invalid after
				self.redirect('/?m=activefail')
			elif vid_url == 2:
				## Wrong Host (.com included or not, even)
				self.redirect('/?m=hostfail')
			else:
				vid.url = vid_url
				orig_tags = split_tags(clean_tags(self.request.get('orig_tags')))
				cover_tags = split_tags(clean_tags(self.request.get('cover_tags')))
				all_tags = [tag+"_o" for tag in orig_tags] + [tag+"_c" for tag in cover_tags]
				
				try:
					existing_vid = Vid.all().filter('url =', vid.url).fetch(1)[0]

					if existing_vid:
						vid = existing_vid
						old_tags = vid.tags
						new_tags = ([tag for tag in all_tags if tag not in old_tags])
						vid.tags += new_tags
						vid.put()
						# if there are any new tags, make a new tagmap for them.
						if new_tags:
							create_tagmap(vid, new_tags)

					else:
						vid.tags = all_tags
						vid.rank = 0
						vid.author = users.get_current_user().nickname()
						vid.put()
						if all_tags:
							create_tagmap(vid, all_tags)
				except:
					vid.tags = all_tags
					vid.rank = 0
					vid.author = users.get_current_user().nickname()
					vid.put()
					if all_tags:
						create_tagmap(vid, all_tags)
				
				self.redirect('/?m=add')
		elif vid_check >= 500:
			## String entered rather than url
			self.redirect('/?m=urlfail')
		else:
			vid_url = make_embed_url(url)[0]
			if vid_url == 0:
				## Not sure about this one
				##logging.info('mystery 2')
				self.redirect('/?m=catchfail')
			elif vid_url == 1 or vid_url == 2 or type(vid_url) != type((3,4)):
				## youtube server, but video code is inactive or taken down or bogus
				self.redirect('/?m=activefail')
			else:
				## Not sure about this one
				##logging.info('mystery 3')
				self.redirect('/?m=catchfail')

		##  eventually just make an ajax call that returns "success" or not.
		## potential problem: what if users try to upload the same video mul-
		## tiple times. keep them from that!  but what if there are multiple 
		## spellings for a word? then users may see that a video is already up
		## loaded, but doesn't have the spelling they're looking for?
		## maybe suggest that video, and suggest that it's tags need changing?

class TagHandler(webapp2.RequestHandler):
	"""Takes an ajax request to update an existing video with new tags and responds
		with success or failure."""
	def post(self):
		## SECURITY / EFFICIENCY / ERRORHANDLING / TIMEOUT ETC CONSIDERATIONS
		# Get POSTed variables
		url = self.request.get('url')
		orig_tags = split_tags(clean_tags(self.request.get('orig_tags')))
		cover_tags = split_tags(clean_tags(self.request.get('cover_tags')))

		# add _o and _c from tags and concatenate them as a list
		all_tags = [tag+"_o" for tag in orig_tags] + [tag+"_c" for tag in cover_tags]

		# Index the video being updated and filter out the existing tags
		# from the ones being uploaded.
		vid = Vid.all().filter('url =', url).fetch(1)[0]
		old_tags = vid.tags
		new_tags = ([tag for tag in all_tags if tag not in old_tags])
		vid.tags += new_tags
		vid.put()
		# if there are any new tags, make a new tagmap for them.
		if new_tags:
			create_tagmap(vid, new_tags)

		self.response.write("Success!")

class HintHandler(webapp2.RequestHandler):
	def post(self):
		## SECURITY / EFFICIENCY / ERRORHANDLING / TIMEOUT ETC CONSIDERATIONS

		ajax_request = self.request.get('partial_query').split(',')[-1]
		if ajax_request:
			partial_query=clean_tags(ajax_request)[0]
			tag_obj_list = Tag.all().filter('name >', partial_query).filter(
							'name <', partial_query + "\uFFFD").order('name').order('-rank').fetch(4)
			suggestion_list = list(set([tag_obj.name[:-2] for tag_obj in tag_obj_list]))
			response = json.dumps(suggestion_list, separators=(',',':'))
			self.response.write(response)
		self.response.write("")

class ScrollHandler(webapp2.RequestHandler):
	def post(self):
		## SECURITY / EFFICIENCY / ERRORHANDLING / TIMEOUT ETC CONSIDERATIONS
		## IN DICTIONARY FORM, SO CAN FILTER OUT EMPTY BITS?
		query = self.request.get('query')
		offset = int(self.request.get('offset'))

		new_vids = eval(query + '.fetch(limit = 6, offset = offset)')
		vid_data = {}

		for i, vid in enumerate(new_vids):
			tag_string = ""
			for tag in reversed(sorted(vid.tags, key=len)):
				if tag[:-2] not in tag_string:
					tag_string += tag[:-2] + " "

			vid_data[i] = [vid.url, tag_string]

		response = json.dumps(vid_data, separators=(',',':'))
		self.response.write(response)

class UpvoteHandler(webapp2.RequestHandler):
	def post(self):
		## SECURITY / EFFICIENCY / ERRORHANDLING / TIMEOUT ETC CONSIDERATIONS
		## IN DICTIONARY FORM, SO CAN FILTER OUT EMPTY BITS?
		url = self.request.get('url')
		quantity = self.request.get('quantity')

		vid = Vid.all().filter('url =', url).fetch(1)[0]
		vid.rank += int(quantity)
		vid.put()
		
		self.response.write("Success!")


## use filtering algorithm that depends on users to find videos and interact with them
## as the basis of their worth and the worth of the keywords used to find them.

app = webapp2.WSGIApplication([
								('/', MainHandler),
								('/add', AddHandler),
								('/hint', HintHandler),
								('/scroll', ScrollHandler),
								('/tag', TagHandler),
								('/upvote', UpvoteHandler),
													], debug=True)
