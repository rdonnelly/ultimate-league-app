import datetime
import feedparser
import httplib2
import sys

from django.conf import settings
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render_to_response
from django.template import RequestContext

from apiclient.discovery import build
from flickrapi import FlickrError
from oauth2client.client import SignedJwtAssertionCredentials
from syncr.app.flickr import FlickrSyncr
from syncr.flickr.models import Photo

from ultimate.index.models import *
from pybb.models import Topic


def index(request):
	announcements = Topic.objects.filter(forum__name__exact='Announcements').order_by('-created')[:5]

	updates = list()

	photoset = list()
	counter = 0
	photos = Photo.objects.order_by('-upload_date', 'owner')[:30]
	for photo in photos:
		photo.url = photo.get_thumbnail_url

		photoset.append(photo)

		try:
			nextOwner = photos[counter+1].owner
		except IndexError:
			nextOwner = False

		if photo.owner != nextOwner:
			updates.append({'type': 'photo', 'photoset': photoset, 'owner': photo.owner, 'owner_nsid': photo.owner_nsid, 'count': len(photoset), 'datetime': photo.upload_date})
			photoset = list()
		counter += 1

	updates.sort(key=lambda x: x['datetime'], reverse=True)

	# get calendar

	client_email = '454801765098-2591ju5q6p30ivqd7uq1b1d02sbchhv7@developer.gserviceaccount.com'
	with open(getattr(settings, 'PROJECT_ROOT', None) + '/../Ann Arbor Ultimate-7f4f4372cd1f.p12') as f:
		private_key = f.read()

	credentials = SignedJwtAssertionCredentials(client_email, private_key,
		'https://www.googleapis.com/auth/calendar.readonly')

	http = httplib2.Http()
	http = credentials.authorize(http)

	service = build(serviceName='calendar', version='v3', http=http)

	limit = (datetime.datetime.utcnow() - datetime.timedelta(weeks=4)).isoformat('T') + 'Z'

	eventsRaw = service.events().list(calendarId='pm3odo50mikpffck6bnrhrqj3c@group.calendar.google.com', orderBy='startTime', singleEvents=True, timeMin=limit).execute()
	events = list()
	for event in eventsRaw['items']:
		events.append({
			'summary': event['summary'],
			# 'start': event['startTime']['datetime']
			# 'end':
		})

	return render_to_response('index/index.html',
		{
			'announcements': announcements,
			'events': events,
			'updates': updates,
			'photos': photos
		},
		context_instance=RequestContext(request))


def update_feed(request):
	flickrSearchTerms = getattr(settings, 'FLICKR_SEARCH', 'ultimatefrisbee')
	flickrSyncr = FlickrSyncr(getattr(settings, 'FLICKR_KEY', None), getattr(settings, 'FLICKR_SECRET', None))
	flickrSearchFeed = feedparser.parse('http://api.flickr.com/services/feeds/photos_public.gne?tags=' + flickrSearchTerms + '&format=atom')

	for photo in flickrSearchFeed.entries:
		photoID = photo.id.rsplit('/', 1)[1]

		try:
			flickrSyncr.syncPhoto(photoID)
		except FlickrError:
			print('flickr parse error')



	messages.success(request, 'The social feed was updated successfully (maybe).')
	return HttpResponseRedirect(reverse('home'))

	return render_to_response(
		'index/content.html',
		{'content': 'update'},
		context_instance=RequestContext(request))

def content(request, url):
	try:
		content = get_object_or_404(StaticContent, url=url)
	except StaticContent.DoesNotExist:
		content = ''
	return render_to_response('index/content.html',
		{'content': content},
		context_instance=RequestContext(request))
